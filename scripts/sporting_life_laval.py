"""Scrape Sporting Life Laval liquidation items and refresh the dataset."""

from __future__ import annotations

import json
import math
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, List, Optional

import requests
from bs4 import BeautifulSoup


BASE_URL = "https://www.sportinglife.ca"
GRID_ENDPOINT = (
    "https://www.sportinglife.ca/on/demandware.store/"
    "Sites-SportingLife-Site/fr_CA/Search-UpdateGrid"
)
PAGE_SIZE = 48
CITY_SLUG = "laval"
STORE_NAME = "Sporting Life"
OUTPUT_PATH = Path("data/sporting-life/laval.json")
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
REQUEST_TIMEOUT = 30

PRICE_RE = re.compile(r"([0-9]+(?:[\.,][0-9]{1,2})?)")


@dataclass
class Product:
    title: str
    brand: Optional[str]
    url: str
    image: Optional[str]
    price: Optional[float]
    sale_price: Optional[float]
    price_display: Optional[str]
    sale_price_display: Optional[str]
    sku: Optional[str]
    stock: Optional[str]

    def to_payload(self) -> dict:
        return {
            "title": self.title,
            "brand": self.brand or "",
            "url": self.url,
            "image": self.image or "",
            "price": self.price,
            "salePrice": self.sale_price,
            "priceDisplay": self.price_display,
            "salePriceDisplay": self.sale_price_display,
            "store": STORE_NAME,
            "city": CITY_SLUG,
            "sku": self.sku or "",
            "stock": self.stock or "",
        }


def _format_price_display(amount: Optional[float]) -> Optional[str]:
    if amount is None:
        return None
    value = f"{amount:,.2f} $"
    # Convert to French-style decimal separators
    value = value.replace(",", " ")
    integer, _, decimal = value.partition(".")
    integer = integer.replace(" ", " ")  # narrow no-break space for thousands
    return f"{integer},{decimal}" if decimal else integer


def _parse_price(text: str) -> Optional[float]:
    if not text:
        return None
    match = PRICE_RE.search(text)
    if not match:
        return None
    raw = match.group(1).replace(" ", "").replace(",", ".")
    try:
        return float(raw)
    except ValueError:
        return None


def _iter_html_chunks(payload: dict) -> Iterable[str]:
    keys = [
        ("productSearchResult", "productTiles"),
        ("productSearchResult", "productTileHtml"),
        ("productTiles",),
        ("productTileHtml",),
        ("renderedProducts",),
        ("results",),
    ]
    for path in keys:
        node = payload
        for key in path:
            if isinstance(node, dict) and key in node:
                node = node[key]
            else:
                node = None
                break
        if not node:
            continue
        if isinstance(node, list):
            for item in node:
                if isinstance(item, str) and "<" in item:
                    yield item
        elif isinstance(node, str) and "<" in node:
            yield node
    # Fallback: inspect string values
    for value in payload.values():
        if isinstance(value, str) and "<" in value:
            yield value
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, str) and "<" in item:
                    yield item


def _extract_from_data_attrs(element) -> dict:
    data: dict = {}
    for attr in ("data-product", "data-product-data", "data-analytics", "data-product-analytics"):
        raw = element.get(attr)
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            data.update(payload)
    return data


def _select_text(element, selectors: List[str]) -> Optional[str]:
    for selector in selectors:
        node = element.select_one(selector)
        if node and node.get_text(strip=True):
            return node.get_text(strip=True)
    return None


def _select_attr(element, selectors: List[str], attr: str) -> Optional[str]:
    for selector in selectors:
        node = element.select_one(selector)
        if node and node.get(attr):
            return node[attr]
    return None


def _parse_product_tile(element) -> Optional[Product]:
    data = _extract_from_data_attrs(element)

    title = data.get("name") or data.get("productName")
    if not title:
        title = _select_text(element, [
            "[class*='product-name'] a",
            "[class*='product-title'] a",
            "a.product-tile__name",
            "a[href]",
        ])
    if not title:
        return None

    brand = (
        data.get("brand")
        or data.get("brandName")
        or _select_text(element, ["[class*='brand']", "[data-brand]"])
    )

    relative_url = data.get("url") or data.get("productUrl")
    if not relative_url:
        relative_url = _select_attr(element, [
            "[class*='product-name'] a",
            "a.product-tile__name",
            "a[href]",
        ], "href")
    if not relative_url:
        return None
    if relative_url.startswith("/"):
        url = f"{BASE_URL}{relative_url}"
    elif relative_url.startswith("http"):
        url = relative_url
    else:
        url = f"{BASE_URL}/{relative_url.lstrip('./')}"

    image = (
        data.get("image")
        or data.get("imageUrl")
        or _select_attr(element, ["img", "source"], "src")
        or _select_attr(element, ["img", "source"], "data-src")
    )
    sku = (
        data.get("sku")
        or data.get("id")
        or data.get("productID")
        or element.get("data-sku")
        or element.get("data-itemid")
        or element.get("data-pid")
    )
    stock = data.get("stock") or data.get("availabilityMessage")

    # Price parsing
    price_display = data.get("priceDisplay") or data.get("listPrice")
    sale_display = data.get("salePriceDisplay") or data.get("salePrice")
    price = _parse_price(str(data.get("price"))) if data.get("price") is not None else None
    sale_price = _parse_price(str(data.get("salePrice"))) if data.get("salePrice") is not None else None

    if not price_display:
        price_display = _select_text(element, [
            "[class*='price'] [class*='list']",
            "[class*='price'] [class*='standard']",
            "[class*='price'] [class*='original']",
            "[class*='price']",
        ])
    if not sale_display:
        sale_display = _select_text(element, [
            "[class*='price'] [class*='sales']",
            "[class*='price'] [class*='sale']",
            "[class*='price'] [class*='current']",
        ])

    if price is None and price_display:
        price = _parse_price(price_display)
    if sale_price is None and sale_display:
        sale_price = _parse_price(sale_display)

    if price is None and sale_price is not None:
        price = sale_price
    if sale_price is None and price is not None and sale_display:
        sale_price = price

    if price_display is None and price is not None:
        price_display = _format_price_display(price)
    if sale_display is None and sale_price is not None:
        sale_display = _format_price_display(sale_price)

    return Product(
        title=title,
        brand=brand,
        url=url,
        image=image,
        price=price,
        sale_price=sale_price if sale_price != price else None,
        price_display=price_display,
        sale_price_display=sale_display if sale_display != price_display else None,
        sku=sku,
        stock=stock,
    )


def _parse_products_from_html(html: str) -> List[Product]:
    soup = BeautifulSoup(html, "html.parser")
    products: List[Product] = []
    seen_urls: set[str] = set()
    for element in soup.select("[data-product], [data-product-analytics], [data-pid]"):
        product = _parse_product_tile(element)
        if not product:
            continue
        if product.url in seen_urls:
            continue
        seen_urls.add(product.url)
        products.append(product)
    return products


def _parse_item_list(html: str) -> List[Product]:
    soup = BeautifulSoup(html, "html.parser")
    products: List[Product] = []
    seen_urls: set[str] = set()
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            data = json.loads(script.string or "")
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and data.get("@type") == "ItemList":
            for entry in data.get("itemListElement", []):
                item = entry.get("item") if isinstance(entry, dict) else None
                if not isinstance(item, dict):
                    continue
                name = item.get("name")
                if not name:
                    continue
                url = item.get("url")
                if not url:
                    continue
                if url.startswith("/"):
                    url = f"{BASE_URL}{url}"
                if url in seen_urls:
                    continue
                seen_urls.add(url)
                brand = None
                brand_info = item.get("brand")
                if isinstance(brand_info, dict):
                    brand = brand_info.get("name")
                elif isinstance(brand_info, str):
                    brand = brand_info
                image = item.get("image")
                sku = item.get("sku")
                offers = item.get("offers")
                price = sale_price = None
                price_display = sale_display = None
                if isinstance(offers, dict):
                    if "offers" in offers and isinstance(offers["offers"], list):
                        offers_list = offers["offers"]
                    else:
                        offers_list = [offers]
                    for offer in offers_list:
                        if not isinstance(offer, dict):
                            continue
                        offer_price_raw = offer.get("price")
                        if isinstance(offer_price_raw, (int, float)):
                            offer_price = float(offer_price_raw)
                        else:
                            offer_price = _parse_price(str(offer_price_raw))
                        if offer_price is None:
                            continue
                        if sale_price is None or offer_price < sale_price:
                            sale_price = offer_price
                        if price is None or offer_price > price:
                            price = offer_price
                if price_display is None and price is not None:
                    price_display = _format_price_display(price)
                if sale_display is None and sale_price is not None:
                    sale_display = _format_price_display(sale_price)
                products.append(
                    Product(
                        title=name,
                        brand=brand,
                        url=url,
                        image=image,
                        price=price,
                        sale_price=sale_price if sale_price != price else None,
                        price_display=price_display,
                        sale_price_display=sale_display if sale_display != price_display else None,
                        sku=sku,
                        stock=None,
                    )
                )
    return products


def fetch_products(session: requests.Session) -> List[Product]:
    products: List[Product] = []
    seen_urls: set[str] = set()
    start = 0
    total = math.inf

    while start < total:
        params = {"cgid": "last-run-clearance", "start": start, "sz": PAGE_SIZE, "format": "ajax"}
        response = session.get(GRID_ENDPOINT, params=params, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        try:
            payload = response.json()
        except ValueError:
            html_products = _parse_products_from_html(response.text)
            if not html_products:
                html_products = _parse_item_list(response.text)
            if not html_products:
                break
            for product in html_products:
                if product.url in seen_urls:
                    continue
                seen_urls.add(product.url)
                products.append(product)
            start += PAGE_SIZE
            continue

        product_search = payload.get("productSearchResult")
        if isinstance(product_search, dict):
            page_total = (
                product_search.get("total")
                or product_search.get("hitCount")
                or product_search.get("count")
            )
        else:
            page_total = payload.get("total") or payload.get("hitCount") or payload.get("count")
        if isinstance(page_total, int):
            total = page_total
        elif isinstance(page_total, str) and page_total.isdigit():
            total = int(page_total)

        page_products: List[Product] = []
        for html_chunk in _iter_html_chunks(payload):
            page_products.extend(_parse_products_from_html(html_chunk))
        if not page_products:
            # Fallback to JSON-LD parsing if no explicit tiles were found
            html = payload.get("content") if isinstance(payload.get("content"), str) else None
            if html:
                page_products.extend(_parse_products_from_html(html))
            if not page_products:
                for html_chunk in _iter_html_chunks(payload):
                    page_products.extend(_parse_item_list(html_chunk))
        if not page_products:
            break
        for product in page_products:
            if product.url in seen_urls:
                continue
            seen_urls.add(product.url)
            products.append(product)
        start += PAGE_SIZE
        if not page_products:
            break
    if products:
        return products

    # Fallback: fetch the standard category page if AJAX endpoint failed.
    fallback_response = session.get(
        f"{BASE_URL}/fr-CA/c/last-run-clearance",
        params={"sz": PAGE_SIZE},
        timeout=REQUEST_TIMEOUT,
    )
    fallback_response.raise_for_status()
    html_products = _parse_products_from_html(fallback_response.text)
    if not html_products:
        html_products = _parse_item_list(fallback_response.text)
    return html_products


def ensure_output_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def save_products(products: List[Product], path: Path) -> None:
    ensure_output_dir(path)
    payload = [product.to_payload() for product in products]
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    session = requests.Session()
    session.headers.update({
        "User-Agent": USER_AGENT,
        "Accept": "application/json, text/html, */*",
        "Accept-Language": "fr-CA,fr;q=0.9,en;q=0.8",
        "X-Requested-With": "XMLHttpRequest",
    })

    products = fetch_products(session)
    if not products:
        print("Aucun produit récupéré pour la liquidation de Laval", file=sys.stderr)
        return 1

    save_products(products, OUTPUT_PATH)
    print(f"Enregistré {len(products)} produits pour Sporting Life Laval ({datetime.utcnow():%Y-%m-%d %H:%M} UTC)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
