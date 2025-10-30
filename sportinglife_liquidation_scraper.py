"""Scrape Sporting Life liquidation listings and refresh local datasets.

The script fetches the public liquidation listing, follows the pagination
controls, and extracts key fields for every product. The collected data is
stored in a CSV export as well as in the JSON dataset consumed by the web
application.

Usage
-----

    python sportinglife_liquidation_scraper.py

Optional arguments allow overriding the output locations or disabling the
polite delay between paginated requests. Run ``python
sportinglife_liquidation_scraper.py --help`` for the full list of options.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List

import requests
from bs4 import BeautifulSoup
from bs4.element import Tag

BASE_URL = "https://www.sportinglife.ca/fr-CA/liquidation/"
DEFAULT_CSV_PATH = Path("sportinglife_liquidation_laval.csv")
DEFAULT_JSON_PATH = Path("data/sporting-life/laval.json")
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
HEADERS = {"User-Agent": USER_AGENT}


@dataclass
class Product:
    """Representation of a liquidation product entry."""

    title: str
    url: str
    price_display: str
    sale_price_display: str
    stock: str
    brand: str = ""
    image: str = ""
    sku: str = ""
    price: float | None = None
    sale_price: float | None = None

    def as_csv_row(self) -> List[str]:
        return [self.title, self.sale_price_display, self.stock, self.url]

    def as_json_row(self) -> dict[str, object]:
        price_value = self.price if self.price is not None else self.sale_price
        return {
            "title": self.title,
            "brand": self.brand,
            "url": self.url,
            "image": self.image,
            "price": price_value,
            "salePrice": self.sale_price,
            "priceDisplay": self.price_display or None,
            "salePriceDisplay": self.sale_price_display or None,
            "store": "Sporting Life",
            "city": "laval",
            "sku": self.sku,
            "stock": self.stock,
        }


def fetch_page(url: str) -> BeautifulSoup:
    response = requests.get(url, headers=HEADERS, timeout=30)
    response.raise_for_status()
    return BeautifulSoup(response.text, "html.parser")


def _select_text(parent: Tag, selectors: Iterable[str]) -> str:
    for selector in selectors:
        element = parent.select_one(selector)
        if element and element.text:
            return element.text.strip()
    return ""


def _extract_href(parent: Tag, selectors: Iterable[str]) -> str:
    for selector in selectors:
        element = parent.select_one(selector)
        if element and element.has_attr("href"):
            return element["href"]
    return ""


def _extract_image(parent: Tag) -> str:
    image = parent.select_one("img")
    if not isinstance(image, Tag):
        return ""
    for attribute in ("data-src", "data-original", "src", "data-lazy"):
        value = image.get(attribute)
        if value:
            return value
    return ""


def _parse_price_value(raw: str) -> float | None:
    if not raw:
        return None
    cleaned = (
        raw.replace("$", "")
        .replace("CAD", "")
        .replace("CA", "")
        .replace("\xa0", " ")
        .replace("\u202f", " ")
        .strip()
    )
    # Keep only digits, commas, periods and spaces to handle French formatting.
    cleaned = re.sub(r"[^0-9,\.\s-]", "", cleaned)
    cleaned = cleaned.replace(" ", "")
    cleaned = cleaned.replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        match = re.search(r"-?\d+(?:\.\d+)?", cleaned)
        if match:
            try:
                return float(match.group(0))
            except ValueError:
                return None
    return None


def parse_product(tile: Tag) -> Product:
    title = _select_text(
        tile,
        (
            "div.product-title a",
            "div.product-name a",
            "a.name-link",
        ),
    )
    brand = _select_text(tile, ("div.product-brand", "div.brand-name"))
    price_display = _select_text(
        tile,
        (
            "span.price-standard",
            "span.was",
            "span.value.original-price",
        ),
    )
    sale_price_display = _select_text(
        tile,
        (
            "span.sales",
            "span.price-sales",
            "span.value",
        ),
    )
    stock = _select_text(
        tile,
        (
            "div.product-inventory",
            "div.inventory-level",
            "div.stock-message",
        ),
    )
    href = _extract_href(
        tile,
        (
            "div.product-title a",
            "div.product-name a",
            "a.name-link",
        ),
    )
    image_url = _extract_image(tile)
    sku = tile.get("data-itemid") or tile.get("data-productid") or tile.get("data-product-id") or ""

    absolute_url = href
    if href and href.startswith("/"):
        absolute_url = f"https://www.sportinglife.ca{href}"
    elif href and href.startswith("http"):
        absolute_url = href

    return Product(
        title=title,
        brand=brand,
        price_display=price_display,
        sale_price_display=sale_price_display,
        stock=stock,
        url=absolute_url,
        image=image_url,
        sku=sku,
        price=_parse_price_value(price_display),
        sale_price=_parse_price_value(sale_price_display),
    )


def parse_products(soup: BeautifulSoup) -> List[Product]:
    tiles = soup.select("div.product-tile")
    products: List[Product] = []
    for tile in tiles:
        product = parse_product(tile)
        if product.title and product.url:
            products.append(product)
    return products


def has_next_page(soup: BeautifulSoup) -> bool:
    next_btn = soup.select_one("li.pagination-next:not(.disabled) a")
    return next_btn is not None


def collect_all_pages(delay: float) -> List[Product]:
    products: List[Product] = []
    page_num = 1
    while True:
        url = f"{BASE_URL}?page={page_num}"
        print(f"Téléchargement page {page_num}...")
        soup = fetch_page(url)
        page_products = parse_products(soup)
        if not page_products:
            break
        products.extend(page_products)
        if not has_next_page(soup):
            break
        page_num += 1
        if delay:
            time.sleep(delay)
    return products


def write_csv(products: Iterable[Product], output_file: Path) -> None:
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with output_file.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["name", "sale_price", "stock", "url"])
        for product in products:
            writer.writerow(product.as_csv_row())


def write_json(products: Iterable[Product], output_file: Path) -> None:
    payload = [product.as_json_row() for product in products]
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with output_file.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-csv",
        type=Path,
        default=DEFAULT_CSV_PATH,
        help=f"Chemin du fichier CSV de sortie (défaut: {DEFAULT_CSV_PATH})",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=DEFAULT_JSON_PATH,
        help=f"Chemin du fichier JSON de sortie (défaut: {DEFAULT_JSON_PATH})",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=2.0,
        help="Temps d'attente (en secondes) entre les requêtes de pagination.",
    )
    return parser


def main() -> int:
    parser = build_argument_parser()
    args = parser.parse_args()

    products = collect_all_pages(delay=max(args.delay, 0.0))
    if not products:
        print("Aucun produit n'a été trouvé sur la page de liquidation.")
        return 1

    write_csv(products, args.output_csv)
    write_json(products, args.output_json)
    print(
        f"{len(products)} produits enregistrés dans {args.output_csv} et {args.output_json}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
