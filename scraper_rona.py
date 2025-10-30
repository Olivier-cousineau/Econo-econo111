"""Scrape RONA St-Jérôme liquidation listings to JSON.

The scraper normally relies on Playwright to render the dynamic, paginated
listing experience.  In restricted environments (like CI or development
sandboxes) downloading the browser binaries may fail.  To keep the tool
usable we allow passing in a pre-rendered HTML snapshot via ``--html`` and
provide a more helpful error message when Playwright cannot launch a
browser.
"""

from __future__ import annotations

import heapq
import json
import re
import sys
from argparse import ArgumentParser, Namespace
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Tuple
from urllib.parse import ParseResult, parse_qs, urljoin, urlparse

from bs4 import BeautifulSoup
from playwright.sync_api import (
    Error as PlaywrightError,
    TimeoutError as PlaywrightTimeoutError,
    sync_playwright,
)

LISTING_URL = "https://www.rona.ca/fr/promotions/liquidation"
PAGINATION_PARAM_KEYS: Sequence[str] = (
    "page",
    "pageNumber",
    "pageNum",
    "pageIndex",
    "p",
)
PAGE_NUMBER_PATTERN = re.compile(
    r"(?:page|pageNumber|pageNum|pageIndex|p)[^0-9]{0,3}(\d+)",
    re.IGNORECASE,
)
ROOT_DIR = Path(__file__).resolve().parent
DEFAULT_SNAPSHOT = ROOT_DIR / "data" / "samples" / "rona-st-jerome-sample.html"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
    )
}


def parse_args() -> Namespace:
    """Return parsed CLI arguments."""

    parser = ArgumentParser(description=__doc__)
    parser.add_argument(
        "--html",
        type=Path,
        help=(
            "Read the listing HTML from a local file instead of fetching it "
            "with Playwright.  Useful for offline development."
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("rona-st-jerome.json"),
        help="Path to write the resulting JSON data (default: rona-st-jerome.json).",
    )
    return parser.parse_args()


def _extract_page_number(parsed: ParseResult) -> int | None:
    """Return the page number encoded within a pagination URL."""

    query = parse_qs(parsed.query)
    for key in PAGINATION_PARAM_KEYS:
        values = query.get(key)
        if not values:
            continue
        for value in values:
            try:
                return int(value)
            except (TypeError, ValueError):
                continue

    candidates = [parsed.path, parsed.fragment]
    for candidate in candidates:
        if not candidate:
            continue
        match = PAGE_NUMBER_PATTERN.search(candidate)
        if match:
            try:
                return int(match.group(1))
            except (TypeError, ValueError):
                return None
    return None


def _wait_for_listing_content(page) -> None:
    """Block until the liquidation grid is populated or timing out."""

    try:
        page.wait_for_load_state("networkidle", timeout=10_000)
    except PlaywrightTimeoutError:
        page.wait_for_load_state("domcontentloaded", timeout=10_000)
    try:
        page.wait_for_selector(".product-tile__wrapper", timeout=20_000)
    except PlaywrightTimeoutError:
        # Give the page a brief grace period before collecting the HTML snapshot.
        page.wait_for_timeout(2_000)


def _scroll_to_bottom(page, pause_time: int = 1_000, max_scrolls: int = 20) -> None:
    """Scroll down the page repeatedly to trigger lazy-loaded content."""

    previous_height = 0
    for i in range(max_scrolls):
        print(f"[INFO] Scrolling... ({i + 1}/{max_scrolls})")
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(pause_time)
        current_height = page.evaluate("document.body.scrollHeight")
        if current_height == previous_height:
            print("[INFO] Reached bottom of page.")
            break
        previous_height = current_height


def _iter_pagination_targets(soup: BeautifulSoup, base: ParseResult) -> Iterable[Tuple[str, int]]:
    """Yield absolute pagination URLs and their page numbers."""

    seen: set[str] = set()
    for link in soup.select("a[href]"):
        href = link.get("href")
        if not href or href.startswith("#"):
            continue
        absolute = urljoin(LISTING_URL, href)
        if absolute in seen:
            continue
        parsed = urlparse(absolute)
        if parsed.path != base.path:
            continue
        page_number = _extract_page_number(parsed)
        if page_number is None:
            continue
        seen.add(absolute)
        yield absolute, page_number


def render_listing_pages() -> List[str]:
    """Return HTML snapshots for every pagination page in the liquidation listing."""

    html_pages: List[str] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(extra_http_headers=HEADERS)
        page = context.new_page()
        visited: set[str] = set()
        queued: set[str] = set()
        queue: List[Tuple[int, str]] = []
        base = urlparse(LISTING_URL)

        def queue_url(url: str, page_number: int | None) -> None:
            if url in visited or url in queued:
                return
            priority = page_number if page_number is not None else len(queue) + 2
            heapq.heappush(queue, (priority, url))
            queued.add(url)

        queue_url(LISTING_URL, 1)

        cookie_consent_checked = False

        try:
            while queue:
                _, target_url = heapq.heappop(queue)
                queued.discard(target_url)
                page.goto(target_url, wait_until="domcontentloaded", timeout=30_000)
                if not cookie_consent_checked:
                    try:
                        page.click("button#onetrust-accept-btn-handler", timeout=5_000)
                        print("[INFO] Accepted cookie consent banner.")
                    except Exception:
                        print("[INFO] Cookie consent not shown or already accepted.")
                    finally:
                        cookie_consent_checked = True
                _wait_for_listing_content(page)
                _scroll_to_bottom(page)
                html = page.content()
                snapshot_index = len(html_pages) + 1
                debug_html_path = Path(f"debug_page_{snapshot_index}.html")
                debug_html_path.write_text(html, encoding="utf-8")
                # Persist debug artifacts so the rendered DOM and visual state can be
                # inspected when troubleshooting scraping issues.
                screenshot_path = Path(f"screenshot_page_{snapshot_index}.png")
                page.screenshot(path=str(screenshot_path))
                print(
                    "[DEBUG] Saved HTML snapshot to",
                    debug_html_path,
                    "and screenshot to",
                    screenshot_path,
                )
                html_pages.append(html)
                visited.add(target_url)

                soup = BeautifulSoup(html, "html.parser")
                for candidate_url, page_number in _iter_pagination_targets(soup, base):
                    queue_url(candidate_url, page_number)
        finally:
            context.close()
            browser.close()
    return html_pages


def _load_snapshot(snapshot_path: Path) -> List[str]:
    """Return HTML content read from the provided snapshot."""

    if not snapshot_path.is_file():
        raise FileNotFoundError(snapshot_path)
    return [snapshot_path.read_text(encoding="utf-8")]


def _fallback_to_snapshot(error: Exception) -> List[str]:
    """Return HTML snapshots from the default fallback when Playwright fails."""

    if DEFAULT_SNAPSHOT.is_file():
        print(
            "[WARN] Playwright could not render the liquidation listing ("
            f"{error.__class__.__name__}: {error}). "
            "Using cached HTML snapshot instead.",
            file=sys.stderr,
        )
        return _load_snapshot(DEFAULT_SNAPSHOT)

    raise SystemExit(
        "Unable to render liquidation listings via Playwright and no fallback snapshot "
        "was found. Install the browser binaries with `playwright install chromium` or "
        "provide a pre-rendered HTML snapshot via --html."
    ) from error


def extract_products(soup: BeautifulSoup) -> List[Dict[str, Any]]:
    """Return product metadata extracted from the listing HTML."""

    products: List[Dict[str, Any]] = []
    wrappers = soup.select(".product-tile__wrapper")
    print(f"[DEBUG] Found {len(wrappers)} product wrappers.")
    for item in wrappers:
        title = item.select_one(".product-tile__title")
        price = item.select_one(".product-tile__price")
        url = item.select_one(".product-tile__title a")
        if not (title and price and url and url.has_attr("href")):
            continue
        products.append(
            {
                "name": title.get_text(strip=True),
                "price": price.get_text(strip=True),
                "url": f"https://www.rona.ca{url['href']}",
            }
        )
    return products


def deduplicate_products(products: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Return products with duplicate URLs removed, preserving order."""

    deduped: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for product in products:
        url = product.get("url")
        if isinstance(url, str):
            if url in seen:
                continue
            seen.add(url)
        deduped.append(product)
    return deduped


def main() -> None:
    args = parse_args()

    print("[INFO] Starting scraper...")

    if args.html:
        print(f"[INFO] Using HTML snapshot: {args.html}")
        html_pages = _load_snapshot(args.html)
    else:
        try:
            print("[INFO] Rendering listing pages with Playwright...")
            html_pages = render_listing_pages()
        except (PlaywrightTimeoutError, PlaywrightError) as exc:
            print(f"[WARN] Playwright failed: {exc}")
            html_pages = _fallback_to_snapshot(exc)

    print(f"[INFO] Extracting products from {len(html_pages)} pages...")
    products: List[Dict[str, Any]] = []
    for html in html_pages:
        soup = BeautifulSoup(html, "html.parser")
        products.extend(extract_products(soup))
    products = deduplicate_products(products)
    print(f"[INFO] Total unique products: {len(products)}")
    if not products:
        print("[ERROR] No products scraped. DOM structure may have changed.")
        sys.exit(1)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as fp:
        json.dump(products, fp, ensure_ascii=False, indent=2)
    print(f"[INFO] Scraped data saved to: {args.output}")


if __name__ == "__main__":
    main()
