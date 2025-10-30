"""Scrape RONA St-Jérôme liquidation listings to JSON.

The scraper normally relies on Playwright to render the dynamic, paginated
listing experience.  In restricted environments (like CI or development
sandboxes) downloading the browser binaries may fail.  To keep the tool
usable we allow passing in a pre-rendered HTML snapshot via ``--html`` and
provide a more helpful error message when Playwright cannot launch a
browser.
"""

from __future__ import annotations

import json
import sys
from argparse import ArgumentParser, Namespace
from pathlib import Path
from typing import Any, Dict, List, Sequence
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from playwright.sync_api import (
    Error as PlaywrightError,
    TimeoutError as PlaywrightTimeoutError,
    sync_playwright,
)

LISTING_URL = "https://www.rona.ca/fr/promotions/liquidation"
NEXT_BUTTON_SELECTOR = (
    ".pagination__next, "
    "button[aria-label*='Suivant' i], a[aria-label*='Suivant' i], "
    "button[aria-label*='Next' i], a[aria-label*='Next' i]"
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


def _wait_for_listing_content(page) -> None:
    """Block until the liquidation grid is populated or timing out."""

    try:
        page.wait_for_load_state("networkidle", timeout=10_000)
    except PlaywrightTimeoutError:
        page.wait_for_load_state("domcontentloaded", timeout=10_000)
    try:
        page.wait_for_selector(
            ".product-list__item, .product-tile__wrapper",
            timeout=20_000,
        )
    except PlaywrightTimeoutError:
        # Give the page a brief grace period before collecting the HTML snapshot.
        page.wait_for_timeout(2_000)


def _click_cookie_consent(page) -> None:
    """Accept the cookie banner when it appears."""

    try:
        page.click("button#onetrust-accept-btn-handler", timeout=5_000)
        print("[INFO] Accepted cookie consent banner.")
    except Exception:
        print("[INFO] Cookie consent not shown or already accepted.")


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


def _has_next_page(locator) -> bool:
    """Return True if the Playwright locator points to an enabled element."""

    if locator.count() == 0:
        return False
    element = locator.first
    try:
        if element.is_disabled():
            return False
    except Exception:
        pass
    class_attr = element.get_attribute("class") or ""
    aria_disabled = element.get_attribute("aria-disabled")
    disabled_attr = element.get_attribute("disabled")
    if "disabled" in class_attr.split():
        return False
    if aria_disabled and aria_disabled.lower() == "true":
        return False
    if disabled_attr is not None:
        return False
    return True


def render_listing_pages() -> List[str]:
    """Return HTML snapshots for every pagination page in the liquidation listing."""

    html_pages: List[str] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(extra_http_headers=HEADERS)
        page = context.new_page()

        try:
            page.goto(LISTING_URL, wait_until="domcontentloaded", timeout=30_000)
            _click_cookie_consent(page)

            page_number = 1
            seen_signatures: set[int] = set()
            while True:
                print(f"[INFO] Processing page {page_number}...")
                _wait_for_listing_content(page)
                _scroll_to_bottom(page)
                html = page.content()
                snapshot_index = len(html_pages) + 1
                debug_html_path = Path(f"debug_page_{snapshot_index}.html")
                debug_html_path.write_text(html, encoding="utf-8")

                screenshot_path = Path(f"screenshot_page_{snapshot_index}.png")
                page.screenshot(path=str(screenshot_path))
                print(
                    "[DEBUG] Saved HTML snapshot to",
                    debug_html_path,
                    "and screenshot to",
                    screenshot_path,
                )
                signature = hash(html)
                if signature in seen_signatures:
                    print("[INFO] Duplicate page detected; stopping pagination.")
                    break
                seen_signatures.add(signature)
                html_pages.append(html)

                next_locator = page.locator(NEXT_BUTTON_SELECTOR)
                if not _has_next_page(next_locator):
                    break

                next_locator.first.click()
                page.wait_for_timeout(1_000)
                try:
                    page.wait_for_load_state("networkidle", timeout=10_000)
                except PlaywrightTimeoutError:
                    page.wait_for_load_state("domcontentloaded", timeout=10_000)
                page_number += 1
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
    wrappers = soup.select(".product-list__item")
    if not wrappers:
        wrappers = soup.select(".product-tile__wrapper")
    print(f"[DEBUG] Found {len(wrappers)} product wrappers.")
    price_selectors = [
        ".price__amount",
        ".product-pricing__price",
        ".product__price",
        ".product-tile__price",
    ]

    for item in wrappers:
        title_node = item.select_one(".product__name")
        link_node = item.select_one(".product__name a, .product-tile__title a")
        if link_node is None:
            link_node = item.select_one("a[href]")
        if title_node is None and link_node is not None:
            title_node = link_node

        price_node = None
        for selector in price_selectors:
            price_node = item.select_one(selector)
            if price_node:
                break

        if not (title_node and price_node and link_node and link_node.has_attr("href")):
            continue

        name = title_node.get_text(strip=True)
        price = price_node.get_text(strip=True)
        href = link_node["href"]
        url = urljoin(LISTING_URL, href)
        products.append({"name": name, "price": price, "url": url})
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
