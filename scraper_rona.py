"""Scrape RONA St-Jérôme liquidation listings to JSON using Playwright."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError, sync_playwright

LISTING_URL = (
    "https://www.rona.ca/fr/promotions/liquidation?catalogId=10051&storeId=10151&langId=-2"
)
BASE_URL = "https://www.rona.ca"
OUTPUT_PATH = Path("rona-st-jerome.json")
PRODUCT_TILE_SELECTOR = ".product-tile__wrapper"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/116.0.0.0 Safari/537.36"
)
EXTRA_HEADERS = {
    "Accept-Language": "fr-CA,fr;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
    "Referer": "https://www.rona.ca/",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}


def extract_products(page: Page) -> List[Dict[str, Any]]:
    """Return product metadata extracted from the rendered listing page."""

    products: List[Dict[str, Any]] = []
    for item in page.query_selector_all(PRODUCT_TILE_SELECTOR):
        title_el = item.query_selector(".product-tile__title")
        price_el = item.query_selector(".product-tile__price")
        link_el = item.query_selector(".product-tile__title a")
        if not (title_el and price_el and link_el):
            continue
        href = link_el.get_attribute("href")
        if not href:
            continue
        name = title_el.inner_text().strip()
        price = price_el.inner_text().strip()
        products.append({"name": name, "price": price, "url": f"{BASE_URL}{href}"})
    return products


def fetch_products() -> List[Dict[str, Any]]:
    """Load the liquidation page with Playwright and extract product data."""

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=USER_AGENT,
            locale="fr-CA",
            extra_http_headers=EXTRA_HEADERS,
        )
        page = context.new_page()
        try:
            page.goto(LISTING_URL, wait_until="networkidle", timeout=30_000)
            page.wait_for_selector(PRODUCT_TILE_SELECTOR, timeout=15_000)
            return extract_products(page)
        except PlaywrightTimeoutError as exc:
            raise RuntimeError("Timed out while loading liquidation listings") from exc
        finally:
            context.close()
            browser.close()


def save_products(products: List[Dict[str, Any]]) -> None:
    """Persist the product collection to the JSON output file."""

    OUTPUT_PATH.write_text(
        json.dumps(products, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main() -> None:
    products = fetch_products()
    save_products(products)


if __name__ == "__main__":
    main()
