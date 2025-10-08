"""Scraper de la collection « Clearance » de Best Buy Canada.

The script downloads the public Best Buy Canada clearance collection (or any
collection URL you provide), inspects the embedded Next.js `__NEXT_DATA__`
payload, and extracts products containing both regular and sale prices. Results
are exported to the JSON format consumed by the static site
(`data/best-buy/liquidations.json`).
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterable, List, Optional

import bs4
import requests

DEFAULT_URL = "https://www.bestbuy.ca/en-ca/collection/clearance-products/113065"
DEFAULT_OUTPUT = Path("data/best-buy/liquidations.json")


@dataclass
class Product:
    title: str
    image: str
    price: Decimal
    sale_price: Decimal
    url: str
    store: str = "Best Buy"
    city: str = "En ligne"

    def to_json(self) -> dict:
        return {
            "title": self.title,
            "image": self.image,
            "price": float(self.price),
            "salePrice": float(self.sale_price),
            "store": self.store,
            "city": self.city,
            "url": self.url,
        }


class ExtractionError(RuntimeError):
    """Raised when we cannot extract the JSON payload or products."""


def fetch_html(url: str) -> str:
    logging.info("Fetching %s", url)
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/122.0 Safari/537.36"
        )
    }
    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()
    return response.text


def load_next_data(html: str) -> dict:
    soup = bs4.BeautifulSoup(html, "html.parser")
    script_tag = soup.find("script", id="__NEXT_DATA__", type="application/json")
    if script_tag is None or not script_tag.string:
        raise ExtractionError("Impossible de localiser __NEXT_DATA__ dans la page.")
    try:
        return json.loads(script_tag.string)
    except json.JSONDecodeError as exc:  # pragma: no cover - defensive
        raise ExtractionError("JSON __NEXT_DATA__ invalide") from exc


def walk_dicts(payload: object) -> Iterable[dict]:
    stack = [payload]
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            yield current
            stack.extend(current.values())
        elif isinstance(current, list):
            stack.extend(current)


def parse_price(value: object) -> Optional[Decimal]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    if isinstance(value, str):
        cleaned = value.strip().replace("$", "").replace(",", "")
        if not cleaned:
            return None
        try:
            return Decimal(cleaned)
        except InvalidOperation:  # pragma: no cover - defensive
            return None
    return None


PRICE_KEYS_PRIORITY = (
    "regularPrice",
    "price",
    "fullPrice",
    "salePrice",
    "currentPrice",
)

IMAGE_KEYS_PRIORITY = (
    "thumbnailImage",
    "image",
    "imageUrl",
    "thumbnailUrl",
)

URL_KEYS_PRIORITY = (
    "productUrl",
    "url",
    "link",
    "seoText",
)


def select_first(data: dict, keys: Iterable[str]) -> Optional[object]:
    for key in keys:
        if key in data and data[key]:
            return data[key]
    return None


def build_product(candidate: dict, store: str, city: str) -> Optional[Product]:
    title = candidate.get("name") or candidate.get("title")
    if not title:
        return None

    price = select_first(candidate, PRICE_KEYS_PRIORITY)
    sale_price = candidate.get("salePrice") or select_first(candidate, ("current", "sale"))

    if isinstance(candidate.get("prices"), dict):
        prices = candidate["prices"]
        price = price or select_first(prices, ("regular", "base", "was", "original"))
        sale_price = sale_price or select_first(prices, ("current", "sale", "price", "value"))

    price_decimal = parse_price(price)
    sale_price_decimal = parse_price(sale_price)

    if price_decimal is None and sale_price_decimal is not None:
        price_decimal = sale_price_decimal
    if sale_price_decimal is None and price_decimal is not None:
        sale_price_decimal = price_decimal

    if price_decimal is None or sale_price_decimal is None:
        return None

    image = select_first(candidate, IMAGE_KEYS_PRIORITY)
    if isinstance(candidate.get("images"), list) and not image:
        for img in candidate["images"]:
            if isinstance(img, dict):
                image_candidate = select_first(img, IMAGE_KEYS_PRIORITY)
                if image_candidate:
                    image = image_candidate
                    break
            elif isinstance(img, str) and img:
                image = img
                break

    if not isinstance(image, str) or not image:
        image = ""

    url = select_first(candidate, URL_KEYS_PRIORITY)
    if not isinstance(url, str) or not url:
        url = ""
    if url.startswith("/"):
        url = f"https://www.bestbuy.ca{url}"

    return Product(
        title=title.strip(),
        image=image.strip(),
        price=price_decimal,
        sale_price=sale_price_decimal,
        url=url.strip(),
        store=store,
        city=city,
    )


def extract_products(data: dict, store: str, city: str) -> List[Product]:
    seen = set()
    products: List[Product] = []
    for candidate in walk_dicts(data):
        if not isinstance(candidate, dict):
            continue
        if "name" not in candidate and "title" not in candidate:
            continue
        product = build_product(candidate, store=store, city=city)
        if not product:
            continue
        key = (product.title, product.url)
        if key in seen:
            continue
        seen.add(key)
        products.append(product)
    return products


def sort_products(products: List[Product]) -> List[Product]:
    return sorted(
        products,
        key=lambda product: (product.price - product.sale_price, product.sale_price),
        reverse=True,
    )


def save_products(products: List[Product], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as fp:
        json.dump([product.to_json() for product in products], fp, ensure_ascii=False, indent=2)
    logging.info("Saved %d products to %s", len(products), output_path)


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scraper des produits en liquidation Best Buy")
    parser.add_argument("--url", default=DEFAULT_URL, help="URL de la collection Best Buy à analyser")
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT),
        help="Chemin du fichier JSON de sortie (défaut: data/best-buy/liquidations.json)",
    )
    parser.add_argument("--store", default="Best Buy", help="Nom du magasin à inscrire dans le JSON")
    parser.add_argument("--city", default="En ligne", help="Ville à inscrire dans le JSON")
    parser.add_argument("--dry-run", action="store_true", help="Affiche les produits sans écrire le fichier")
    parser.add_argument("--verbose", action="store_true", help="Active les logs détaillés")
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="[%(levelname)s] %(message)s")
    try:
        html = fetch_html(args.url)
        next_data = load_next_data(html)
        products = extract_products(next_data, store=args.store, city=args.city)
    except (requests.HTTPError, requests.RequestException, ExtractionError) as exc:
        logging.error("Échec de l'extraction: %s", exc)
        return 1

    if not products:
        logging.warning("Aucun produit trouvé — la structure de la page a peut-être changé.")
    else:
        products = sort_products(products)

    if args.dry_run:
        for product in products:
            discount = product.price - product.sale_price
            logging.info("%s — %.2f$ -> %.2f$ (rabais %.2f$)", product.title, product.price, product.sale_price, discount)
        return 0

    save_products(products, Path(args.output))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
