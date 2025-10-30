"""Scrape RONA St-Jérôme liquidation listings to JSON using Playwright."""

from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, List, Sequence, Set
from urllib.parse import urljoin

from playwright.sync_api import (
    Browser,
    BrowserContext,
    Page,
    TimeoutError as PlaywrightTimeoutError,
    sync_playwright,
)

BASE_URL = "https://www.rona.ca"
LISTING_URL_TEMPLATE = (
    "https://www.rona.ca/fr/promotions/liquidation?catalogId={catalog_id}&storeId={store_id}&langId=-2"
)
OUTPUT_PATH = Path("rona-st-jerome.json")
PRODUCT_TILE_SELECTOR = ".product-tile__wrapper"
PRODUCT_TITLE_SELECTOR = ".product-tile__title"
PRODUCT_PRICE_SELECTOR = ".product-tile__price"
PRODUCT_LINK_SELECTOR = ".product-tile__title a"
NEXT_PAGE_SELECTORS: Sequence[str] = (
    "a[aria-label='Next']",
    "a[aria-label='Next page']",
    "button[aria-label='Next']",
    "a.pagination__control--next",
    "button.pagination__control--next",
)
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
MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 5


@dataclass
class Product:
    name: str
    price: str
    url: str


def build_listing_url() -> str:
    """Build the liquidation listing URL for the configured store."""

    store_id = os.getenv("RONA_STORE_ID", "10151").strip() or "10151"
    catalog_id = os.getenv("RONA_CATALOG_ID", "10051").strip() or "10051"
    return LISTING_URL_TEMPLATE.format(store_id=store_id, catalog_id=catalog_id)


def configure_browser(playwright) -> tuple[Browser, BrowserContext, Page]:
    """Create the Playwright browser/page with hardened defaults."""

    browser = playwright.chromium.launch(headless=True)
    context = browser.new_context(
        user_agent=USER_AGENT,
        locale="fr-CA",
        extra_http_headers=EXTRA_HEADERS,
    )
    context.add_init_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
    )
    page = context.new_page()
    page.set_default_timeout(15_000)
    return browser, context, page


def extract_products(page: Page) -> List[Product]:
    """Return product metadata extracted from the rendered listing page."""

    products: List[Product] = []
    for item in page.query_selector_all(PRODUCT_TILE_SELECTOR):
        title_el = item.query_selector(PRODUCT_TITLE_SELECTOR)
        price_el = item.query_selector(PRODUCT_PRICE_SELECTOR)
        link_el = item.query_selector(PRODUCT_LINK_SELECTOR)
        if not (title_el and price_el and link_el):
            continue
        href = link_el.get_attribute("href")
        if not href:
            continue
        name = title_el.inner_text().strip()
        price = price_el.inner_text().strip()
        products.append(Product(name=name, price=price, url=urljoin(BASE_URL, href)))
    return products


def goto_listing(page: Page, url: str) -> None:
    """Navigate to a listing page and wait for products to be present."""

    page.goto(url, wait_until="networkidle", timeout=30_000)
    page.wait_for_selector(PRODUCT_TILE_SELECTOR, state="visible")


def advance_to_next_page(page: Page) -> bool:
    """Attempt to move to the next pagination page, returning success."""

    for selector in NEXT_PAGE_SELECTORS:
        control = page.query_selector(selector)
        if not control:
            continue
        classes = (control.get_attribute("class") or "").lower()
        if "disabled" in classes:
            continue
        if (control.get_attribute("aria-disabled") or "").lower() in {"true", "disabled"}:
            continue
        href = control.get_attribute("href")
        if href:
            goto_listing(page, urljoin(BASE_URL, href))
            return True
        try:
            control.click()
            page.wait_for_load_state("networkidle")
            page.wait_for_selector(PRODUCT_TILE_SELECTOR, state="visible")
            return True
        except PlaywrightTimeoutError:
            return False
    return False


def scrape_all_pages(page: Page, listing_url: str, max_pages: int = 20) -> List[Product]:
    """Collect products from the listing and all subsequent pagination pages."""

    goto_listing(page, listing_url)

    collected: List[Product] = []
    seen_urls: Set[str] = set()

    for _ in range(max_pages):
        page_products = extract_products(page)
        for product in page_products:
            if product.url in seen_urls:
                continue
            seen_urls.add(product.url)
            collected.append(product)
        if not advance_to_next_page(page):
            break

    return collected


def fetch_products() -> List[Product]:
    """Load the liquidation pages with Playwright and extract product data."""

    listing_url = build_listing_url()
    last_exception: Exception | None = None

    for attempt in range(1, MAX_RETRIES + 1):
        with sync_playwright() as playwright:
            browser: Browser | None = None
            context: BrowserContext | None = None
            page: Page | None = None
            try:
                browser, context, page = configure_browser(playwright)
                products = scrape_all_pages(page, listing_url)
                if products:
                    return products
            except PlaywrightTimeoutError as exc:
                last_exception = exc
                wait_seconds = RETRY_BACKOFF_SECONDS * attempt
                print(
                    f"Attempt {attempt}/{MAX_RETRIES} timed out, retrying in {wait_seconds}s…",
                    file=sys.stderr,
                )
                time.sleep(wait_seconds)
            finally:
                if page is not None:
                    page.close()
                if context is not None:
                    context.close()
                if browser is not None:
                    browser.close()

    raise RuntimeError("Failed to retrieve liquidation listings") from last_exception


def save_products(products: Iterable[Product]) -> None:
    """Persist the product collection to the JSON output file."""

    payload = [asdict(product) for product in products]
    OUTPUT_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main() -> None:
    products = fetch_products()
    save_products(products)
    print(f"Saved {len(products)} liquidation products to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
