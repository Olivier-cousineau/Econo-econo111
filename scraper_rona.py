"""Scrape RONA St-Jérôme liquidation listings to JSON."""

from __future__ import annotations

import json
from typing import Any, Dict, List

import requests
from bs4 import BeautifulSoup

LISTING_URL = (
    "https://www.rona.ca/fr/promotions/liquidation?catalogId=10051&storeId=10151&langId=-2"
)
HEADERS = {"User-Agent": "Mozilla/5.0"}


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
    response = requests.get(LISTING_URL, headers=HEADERS, timeout=30)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    products = extract_products(soup)
    with open("rona-st-jerome.json", "w", encoding="utf-8") as fp:
        json.dump(products, fp, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
