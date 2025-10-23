"""Simple catalogue scraper using requests and BeautifulSoup.

This module scrapes a paginated catalogue where each page lists product cards
containing a title, price and rating. The implementation follows the skeleton
shared in the product brief and keeps a small delay between requests to avoid
hammering the remote server.

Usage:
    python scripts/example_catalog_scraper.py --pages 5 --output products.csv

The default configuration targets ``https://www.example.com`` purely as a
placeholder. Replace ``BASE_URL`` with the catalogue you need to scrape before
running the script against a real endpoint.
"""
from __future__ import annotations

import argparse
import csv
import time
from dataclasses import dataclass
from typing import Iterable, List

import requests
from bs4 import BeautifulSoup


BASE_URL = "https://www.example.com/catalogue?page={page}"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}
DEFAULT_DELAY = 1.0


@dataclass
class Product:
    """Container for the scraped product information."""

    name: str
    price: str
    rating: str

    @classmethod
    def from_card(cls, card: BeautifulSoup) -> "Product":
        """Extract the product data from a catalogue card."""

        def get_text(selector: str) -> str:
            element = card.select_one(selector)
            return element.text.strip() if element else "N/A"

        return cls(
            name=get_text(".product-title"),
            price=get_text(".price"),
            rating=get_text(".rating"),
        )


def get_page_content(url: str, delay: float = DEFAULT_DELAY) -> BeautifulSoup:
    """Retrieve and parse the HTML content of ``url`` with a small delay."""

    time.sleep(max(delay, 0))  # Respect a pause between requests
    response = requests.get(url, headers=HEADERS, timeout=30)
    response.raise_for_status()
    return BeautifulSoup(response.text, "html.parser")


def parse_page(soup: BeautifulSoup) -> List[Product]:
    """Return all products found in the parsed page ``soup``."""

    return [Product.from_card(card) for card in soup.select(".product-card")]


def iter_pages(pages: int) -> Iterable[BeautifulSoup]:
    """Yield the parsed HTML soup for the first ``pages`` catalogue pages."""

    for page in range(1, pages + 1):
        url = BASE_URL.format(page=page)
        print(f"Scraping page {page} -> {url}")
        yield get_page_content(url)


def scrape_catalogue(pages: int) -> List[Product]:
    """Scrape ``pages`` catalogue pages and return the collected products."""

    products: List[Product] = []
    for soup in iter_pages(pages):
        products.extend(parse_page(soup))
    return products


def write_products_csv(products: Iterable[Product], output_path: str) -> None:
    """Write ``products`` to ``output_path`` as a CSV file."""

    with open(output_path, "w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=["name", "price", "rating"])
        writer.writeheader()
        writer.writerows(
            {"name": product.name, "price": product.price, "rating": product.rating}
            for product in products
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scrape a paginated catalogue")
    parser.add_argument(
        "--pages",
        type=int,
        default=5,
        help="Number of catalogue pages to scrape (default: 5)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="products.csv",
        help="Destination CSV file (default: products.csv)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    products = scrape_catalogue(max(args.pages, 0))
    write_products_csv(products, args.output)
    print(f"Scraping terminé. Résultats sauvegardés dans {args.output}")


if __name__ == "__main__":
    main()
