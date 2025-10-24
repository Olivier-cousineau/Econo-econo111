"""Utility helpers to extract product information from Canadian Tire product pages.

This module relies solely on the standard library plus ``requests`` which is already
part of the backend dependencies. The scraper focuses on the structured data (JSON-LD)
that Canadian Tire exposes in their product pages. This approach is more resilient
than brittle CSS selectors and avoids adding heavy parsing dependencies.

Example usage::

    python scraper_canadiantire.py https://www.canadiantire.ca/en/pdp/example.html

The script prints a JSON payload with common product attributes (title, SKU, price,
availability, brand, etc.).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, asdict
from typing import Any, Dict, Iterable, Optional

import requests

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
)

JSON_LD_PATTERN = re.compile(
    r"<script[^>]+type=\"application/ld\+json\"[^>]*>(?P<payload>.*?)</script>",
    re.DOTALL,
)


@dataclass
class Product:
    """Lightweight container representing a Canadian Tire product."""

    name: Optional[str] = None
    sku: Optional[str] = None
    description: Optional[str] = None
    price: Optional[float] = None
    currency: Optional[str] = None
    availability: Optional[str] = None
    url: Optional[str] = None
    brand: Optional[str] = None
    image: Optional[str] = None

    @classmethod
    def from_ld(cls, payload: Dict[str, Any]) -> "Product":
        """Build a :class:`Product` instance from JSON-LD attributes."""

        offers = payload.get("offers")
        if isinstance(offers, dict):
            price = _safe_float(offers.get("price"))
            currency = _safe_str(offers.get("priceCurrency"))
            availability = _safe_str(offers.get("availability"))
        else:
            price = currency = availability = None

        brand = payload.get("brand")
        if isinstance(brand, dict):
            brand_name = _safe_str(brand.get("name"))
        else:
            brand_name = _safe_str(brand)

        return cls(
            name=_safe_str(payload.get("name")),
            sku=_safe_str(payload.get("sku")),
            description=_safe_str(payload.get("description")),
            price=price,
            currency=currency,
            availability=availability,
            url=_safe_str(payload.get("url")),
            brand=brand_name,
            image=_safe_str(_coalesce_images(payload.get("image"))),
        )


def _safe_str(value: Any) -> Optional[str]:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _safe_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _coalesce_images(value: Any) -> Optional[str]:
    if isinstance(value, str):
        return value
    if isinstance(value, Iterable):
        for element in value:
            if isinstance(element, str) and element.strip():
                return element.strip()
    return None


def fetch_html(url: str, *, timeout: int = 15) -> str:
    """Return the raw HTML for ``url`` raising an informative error on failure."""

    headers = {"User-Agent": USER_AGENT, "Accept-Language": "en-CA,en;q=0.9"}
    response = requests.get(url, headers=headers, timeout=timeout)
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:  # pragma: no cover - diagnostic path
        raise RuntimeError(f"Failed to retrieve {url}: {exc}") from exc
    return response.text


def extract_json_ld(html: str) -> Iterable[Dict[str, Any]]:
    """Yield JSON-LD dictionaries found in ``html``.

    Canadian Tire embeds multiple JSON-LD blobs. The product description is often
    either a dictionary with ``@type == 'Product'`` or an array containing such an
    entry. This generator normalises both cases.
    """

    for match in JSON_LD_PATTERN.finditer(html):
        raw_payload = match.group("payload").strip()
        if not raw_payload:
            continue
        try:
            data = json.loads(raw_payload)
        except json.JSONDecodeError:
            continue

        if isinstance(data, dict):
            yield data
        elif isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    yield item


def extract_product(url: str) -> Product:
    """Fetch ``url`` and return the first JSON-LD product payload encountered."""

    html = fetch_html(url)
    for payload in extract_json_ld(html):
        if payload.get("@type") == "Product":
            return Product.from_ld(payload)
    raise RuntimeError("No product JSON-LD data found on the page.")


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", help="Canadian Tire product URL to scrape")
    args = parser.parse_args(list(argv) if argv is not None else None)

    try:
        product = extract_product(args.url)
    except Exception as exc:  # pragma: no cover - CLI entry point
        parser.error(str(exc))
        return 1

    print(json.dumps(asdict(product), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    sys.exit(main())
