"""Scrape RONA St-Jérôme liquidation listings to JSON.

The scraper normally relies on Playwright to render the dynamic listing
page, but in restricted environments (like CI or development sandboxes)
downloading the browser binaries may fail.  To keep the tool usable we
allow passing in a pre-rendered HTML snapshot via ``--html`` and provide a
more helpful error message when Playwright cannot launch a browser.
"""

from __future__ import annotations

import json
from argparse import ArgumentParser, Namespace
from pathlib import Path
from typing import Any, Dict, List

from bs4 import BeautifulSoup
from playwright.sync_api import (
    Error as PlaywrightError,
    TimeoutError as PlaywrightTimeoutError,
    sync_playwright,
)

LISTING_URL = (
    "https://www.rona.ca/fr/promotions/liquidation?catalogId=10051&storeId=10151&langId=-2"
)
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


def render_listing_page() -> str:
    """Return the fully rendered HTML for the liquidation listing page."""

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(extra_http_headers=HEADERS)
        page = context.new_page()
        try:
            page.goto(LISTING_URL, wait_until="domcontentloaded", timeout=30_000)
            try:
                page.wait_for_load_state("networkidle", timeout=10_000)
            except PlaywrightTimeoutError:
                # If network idle never triggers, ensure the DOM is ready before scraping.
                page.wait_for_load_state("domcontentloaded", timeout=10_000)
            try:
                page.wait_for_selector(".product-tile__wrapper", timeout=20_000)
            except PlaywrightTimeoutError:
                # Give the page a moment longer before collecting the HTML snapshot.
                page.wait_for_timeout(2_000)
            html = page.content()
        finally:
            context.close()
            browser.close()
    return html


def extract_products(soup: BeautifulSoup) -> List[Dict[str, Any]]:
    """Return product metadata extracted from the listing HTML."""

    products: List[Dict[str, Any]] = []
    for item in soup.select(".product-tile__wrapper"):
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


def main() -> None:
    args = parse_args()

    if args.html:
        html = args.html.read_text(encoding="utf-8")
    else:
        try:
            html = render_listing_page()
        except PlaywrightTimeoutError as exc:  # pragma: no cover - defensive path for CI visibility
            raise SystemExit(
                f"Timed out while loading liquidation listings: {exc}"
            ) from exc
        except PlaywrightError as exc:  # pragma: no cover - exercised only when browser launch fails
            raise SystemExit(
                "Unable to launch Chromium via Playwright. Install the browser "
                "binaries with `playwright install chromium` or provide a pre-"
                "rendered HTML snapshot via --html."
            ) from exc

    soup = BeautifulSoup(html, "html.parser")
    products = extract_products(soup)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as fp:
        json.dump(products, fp, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
