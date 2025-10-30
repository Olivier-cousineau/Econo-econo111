"""Scrape the RONA St-Jérôme liquidation page using Playwright."""

from __future__ import annotations

import json

from playwright.sync_api import sync_playwright

LIQUIDATION_URL = (
    "https://www.rona.ca/fr/promotions/liquidation?catalogId=10051&storeId=10151&langId=-2"
)
OUTPUT_FILE = "rona-st-jerome.json"


def main() -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(LIQUIDATION_URL)
        page.wait_for_load_state("networkidle")

        products = []
        for item in page.query_selector_all(".product-tile__wrapper"):
            title = item.query_selector(".product-tile__title")
            price = item.query_selector(".product-tile__price")
            link = item.query_selector(".product-tile__title a")

            if not (title and price and link):
                continue

            href = link.get_attribute("href")
            if not href:
                continue

            products.append(
                {
                    "name": title.inner_text().strip(),
                    "price": price.inner_text().strip(),
                    "url": f"https://www.rona.ca{href}",
                }
            )

        with open(OUTPUT_FILE, "w", encoding="utf-8") as json_file:
            json.dump(products, json_file, ensure_ascii=False, indent=2)

        browser.close()


if __name__ == "__main__":
    main()
