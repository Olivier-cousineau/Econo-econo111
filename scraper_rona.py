from __future__ import annotations

import json
from pathlib import Path
from typing import List, Dict

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError, sync_playwright

BASE_URL = "https://www.rona.ca/fr/promotions/liquidation?catalogId=10051&storeId=10151&langId=-2"
OUTPUT_PATH = Path("rona-st-jerome.json")
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/116.0.0.0 Safari/537.36"
)


def scrape_products(url: str = BASE_URL) -> List[Dict[str, str]]:
    """Collect liquidation products from the configured URL."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"])
        context = browser.new_context(locale="fr-CA", user_agent=USER_AGENT)
        page = context.new_page()
        page.goto(url, wait_until="networkidle")

        try:
            page.wait_for_selector(".product-tile__wrapper", timeout=15_000)
        except PlaywrightTimeoutError:
            # If nothing loads we still want to capture the current state.
            items = []
        else:
            items = page.query_selector_all(".product-tile__wrapper")

        products: List[Dict[str, str]] = []
        for item in items:
            title = item.query_selector(".product-tile__title")
            price = item.query_selector(".product-tile__price")
            link = item.query_selector(".product-tile__title a")
            if not (title and price and link):
                continue

            href = link.get_attribute("href") or ""
            products.append(
                {
                    "name": title.inner_text().strip(),
                    "price": price.inner_text().strip(),
                    "url": f"https://www.rona.ca{href}",
                }
            )

        browser.close()
        return products


def write_products(products: List[Dict[str, str]], destination: Path = OUTPUT_PATH) -> None:
    destination.write_text(json.dumps(products, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    products = scrape_products()
    write_products(products)


if __name__ == "__main__":
    main()
