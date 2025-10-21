"""Sporting Life clearance scraper.

This script retrieves product data from the Sporting Life clearance
collection and stores it in ``data/sporting-life/liquidation.json``.

If ``ECONODEAL_API_URL`` is defined, the collected items are also sent to
that endpoint as JSON. Optionally, an ``ECONODEAL_API_TOKEN`` can be
provided to populate an ``Authorization`` header using the ``Bearer``
scheme. This makes the script compatible with a Vercel serverless
function or any other lightweight API the site exposes.
"""
from __future__ import annotations

import datetime as _dt
import json
import logging
import os
import re
from pathlib import Path
from typing import Iterable, List, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

SPORTING_LIFE_URL = os.getenv(
    "SPORTING_LIFE_URL", "https://www.sportinglife.ca/fr-CA/liquidation/"
)
DEFAULT_OUTPUT_PATH = (
    Path(__file__).resolve().parent / "data" / "sporting-life" / "liquidation.json"
)
OUTPUT_PATH = Path(os.getenv("SPORTING_LIFE_OUTPUT", str(DEFAULT_OUTPUT_PATH)))
STORE_NAME = os.getenv("SPORTING_LIFE_STORE", "Sporting Life")
DEFAULT_CITY = os.getenv("SPORTING_LIFE_CITY", "online")
USER_AGENT = os.getenv(
    "SPORTING_LIFE_USER_AGENT",
    (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
    ),
)
REQUEST_TIMEOUT = int(os.getenv("SPORTING_LIFE_TIMEOUT", "30"))

API_URL = os.getenv("ECONODEAL_API_URL")
API_TOKEN = os.getenv("ECONODEAL_API_TOKEN")


def fetch_html(url: str) -> str:
    """Return the HTML payload for *url*, raising an exception on failure."""
    logging.info("Fetching Sporting Life clearance page: %s", url)
    response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    return response.text


def parse_price(text: Optional[str]) -> Optional[float]:
    """Convert a price string to a ``float``.

    The Sporting Life markup uses the Canadian locale with commas as decimal
    separators. This helper normalizes the value into a Python ``float``.
    """
    if not text:
        return None

    normalized = text.replace("\xa0", "").replace(" ", "")
    normalized = normalized.replace(",", ".")
    normalized = re.sub(r"[^0-9.]+", "", normalized)
    if normalized.count(".") > 1:
        whole, decimal = normalized.rsplit(".", 1)
        normalized = f"{whole.replace('.', '')}.{decimal}"
    try:
        return float(normalized)
    except ValueError:
        logging.debug("Unable to parse price from %r", text)
        return None


def extract_text(element) -> Optional[str]:
    if element is None:
        return None
    text = element.get_text(strip=True)
    return text or None


def extract_image_url(product) -> Optional[str]:
    image_tag = product.select_one("img")
    if not image_tag:
        return None
    for attribute in ("data-src", "data-original", "data-srcset", "src"):
        value = image_tag.get(attribute)
        if value:
            # If the image uses ``srcset`` we take the first candidate.
            if attribute.endswith("srcset"):
                value = value.split(",")[0].strip().split(" ")[0]
            return urljoin(SPORTING_LIFE_URL, value)
    return None


def parse_products(html: str) -> List[dict]:
    """Parse Sporting Life product tiles from *html*."""
    soup = BeautifulSoup(html, "html.parser")
    products = []
    tiles = soup.select("div.product-tile")
    logging.info("Found %s product tiles", len(tiles))
    timestamp = _dt.datetime.now(tz=_dt.timezone.utc).isoformat()

    for tile in tiles:
        link = tile.select_one("a.link")
        title = extract_text(link)
        if not title:
            logging.debug("Skipping product without title: %s", tile)
            continue

        href = link.get("href") if link else None
        product_url = urljoin(SPORTING_LIFE_URL, href) if href else None

        brand = extract_text(tile.select_one("div.product-tile__brand")) or extract_text(
            tile.select_one("div.tile-body .brand")
        )
        sale_price = parse_price(extract_text(tile.select_one("span.price-sales")))
        original_price = parse_price(extract_text(tile.select_one("span.price-standard")))
        if original_price is None:
            original_price = sale_price

        image_url = extract_image_url(tile)

        product = {
            "title": title,
            "brand": brand,
            "url": product_url,
            "image": image_url,
            "price": original_price,
            "salePrice": sale_price,
            "store": STORE_NAME,
            "city": DEFAULT_CITY,
            "scrapedAt": timestamp,
        }

        # Remove keys that ended up as ``None`` to keep the JSON light.
        product = {key: value for key, value in product.items() if value is not None}
        products.append(product)

    return products


def write_json(items: Iterable[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = list(items)
    logging.info("Writing %s products to %s", len(data), path)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def post_to_api(items: Iterable[dict]) -> None:
    if not API_URL:
        logging.info("No API endpoint configured; skipping upload.")
        return

    headers = {"Content-Type": "application/json"}
    if API_TOKEN:
        headers["Authorization"] = f"Bearer {API_TOKEN}"

    payload = list(items)
    logging.info("Posting %s products to %s", len(payload), API_URL)
    response = requests.post(API_URL, json=payload, headers=headers, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    logging.info("Upload successful with status %s", response.status_code)


def configure_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


def main() -> None:
    configure_logging()
    html = fetch_html(SPORTING_LIFE_URL)
    products = parse_products(html)
    if not products:
        logging.warning("No products were found on %s", SPORTING_LIFE_URL)
    write_json(products, OUTPUT_PATH)
    post_to_api(products)


if __name__ == "__main__":
    main()
