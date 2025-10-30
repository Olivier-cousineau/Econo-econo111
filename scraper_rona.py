"""Scrape RONA St-Jérôme liquidation listings to JSON."""

from __future__ import annotations

import json
from typing import Any, Dict, List

from bs4 import BeautifulSoup
from playwright.sync_api import TimeoutError, sync_playwright

LISTING_URL = (
    "https://www.rona.ca/fr/promotions/liquidation?catalogId=10051&storeId=10151&langId=-2"
)
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
)
HEADERS = {
    "User-Agent": USER_AGENT,
}


def render_listing_page() -> str:
    """Return the fully rendered HTML for the liquidation listing page."""

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=USER_AGENT,
            extra_http_headers=HEADERS,
        )
        page = context.new_page()
        try:
            page.goto(
                LISTING_URL,
                wait_until="domcontentloaded",
                timeout=60_000,
            )
            page.wait_for_selector(".product-tile__wrapper", timeout=45_000)
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
    try:
        html = render_listing_page()
    except TimeoutError as exc:  # pragma: no cover - defensive path for CI visibility
        raise SystemExit(f"Timed out while loading liquidation listings: {exc}") from exc

    soup = BeautifulSoup(html, "html.parser")
    products = extract_products(soup)
    with open("rona-st-jerome.json", "w", encoding="utf-8") as fp:
        json.dump(products, fp, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
