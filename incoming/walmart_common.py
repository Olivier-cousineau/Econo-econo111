"""Shared utilities for Walmart liquidation scrapers."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urljoin

BASE_URL = "https://www.walmart.ca/fr/store/{store_id}/liquidation"
WALMART_BASE_URL = "https://www.walmart.ca"


def slugify(value: str) -> str:
    """Return an ASCII slug from a city name (e.g. "Saint-Jérôme" -> "saint-jerome")."""

    normalized = unicodedata.normalize("NFKD", value)
    ascii_only = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    ascii_only = ascii_only.lower()
    ascii_only = re.sub(r"[^a-z0-9]+", "-", ascii_only).strip("-")
    return ascii_only or "store"


@dataclass(slots=True)
class Store:
    """Metadata describing a Walmart store."""

    id_store: str
    ville: str
    adresse: str = ""
    slug: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.slug:
            self.slug = slugify(self.ville)

    @property
    def url(self) -> str:
        return BASE_URL.format(store_id=self.id_store)


@dataclass(slots=True)
class Deal:
    """Normalized representation of a liquidation product."""

    title: str
    price: float
    sale_price: float
    url: str
    image: Optional[str] = None

    def to_payload(self, store: Store) -> Dict[str, Any]:
        return {
            "title": self.title,
            "image": self.image or "",
            "price": round(self.price, 2),
            "salePrice": round(self.sale_price, 2),
            "store": "Walmart",
            "city": store.ville,
            "url": self.url,
        }


def parse_price(text: Optional[str]) -> Optional[float]:
    """Convert a price string to a float."""

    if not text:
        return None
    clean = (
        text.replace("\u00a0", " ")
        .replace("$", "")
        .replace("CAD", "")
        .replace("cda", "")
        .strip()
    )
    clean = clean.replace(" ", "")
    match = re.search(r"[0-9]+(?:[.,][0-9]{1,2})?", clean)
    if not match:
        return None
    value = match.group(0).replace(",", ".")
    try:
        return float(value)
    except ValueError:
        return None


def deduplicate_deals(deals: Iterable[Deal]) -> List[Deal]:
    """Remove duplicate deals based on their URL."""

    seen: set[str] = set()
    unique: List[Deal] = []
    for deal in deals:
        key = deal.url
        if key in seen:
            continue
        seen.add(key)
        unique.append(deal)
    return unique


def extract_from_state(raw_state: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Discover product dictionaries within ``raw_state`` recursively."""

    candidates: List[Dict[str, Any]] = []

    def walk(obj: Any) -> None:
        if isinstance(obj, dict):
            if {"name", "price", "productId"}.issubset(obj.keys()):
                candidates.append(obj)
            for value in obj.values():
                walk(value)
        elif isinstance(obj, list):
            for item in obj:
                walk(item)

    walk(raw_state)
    return candidates


def build_deal_from_dict(data: Dict[str, Any]) -> Optional[Deal]:
    """Transform a raw JSON dictionary into a :class:`Deal`."""

    title = data.get("name") or data.get("title")
    if not title:
        return None
    url = data.get("productUrl") or data.get("url") or data.get("canonicalUrl")
    if not url:
        return None

    regular_price = data.get("price") or data.get("listPrice") or data.get("regularPrice")
    current_price = data.get("salePrice") or data.get("price") or data.get("offerPrice")

    if isinstance(regular_price, dict):
        regular_price = (
            regular_price.get("price")
            or regular_price.get("amount")
            or regular_price.get("value")
        )
    if isinstance(current_price, dict):
        current_price = (
            current_price.get("price")
            or current_price.get("amount")
            or current_price.get("value")
        )

    price = parse_price(str(regular_price)) if regular_price is not None else None
    sale_price = parse_price(str(current_price)) if current_price is not None else None

    if price is None and sale_price is None:
        return None
    if price is None:
        price = sale_price
    if sale_price is None:
        sale_price = price

    image = None
    images = data.get("image") or data.get("images") or []
    if isinstance(images, list) and images:
        image = images[0]
    elif isinstance(images, dict):
        image = images.get("main") or images.get("large") or images.get("thumbnail")
    elif isinstance(images, str):
        image = images

    normalized_url = urljoin(WALMART_BASE_URL, url)

    return Deal(title=title.strip(), price=price, sale_price=sale_price, url=normalized_url, image=image)

