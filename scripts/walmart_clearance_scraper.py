"""Utility to scrape Walmart Canada clearance deals for a given store.

The script intentionally focuses on simplicity so it can be executed daily by the
GitHub Actions workflow.  It queries Walmart Canada's public GraphQL endpoint
and extracts the cheapest clearance items for the specified store.  The
resulting dataset mirrors the structure expected by the project:

[
    {
        "title": "Product name",
        "url": "https://www.walmart.ca/...",
        "section": "electronics",
        "image": "https://i5.walmartimages.com/...",
        "price": 24.97,
        "sale_price": 5.0,
        "store": "Walmart",
        "city": "Saint-Jérôme"
    }
]

Example usage::

    python scripts/walmart_clearance_scraper.py \
        --store-id 1076 --city "Saint-Jérôme" --output "walmart st jerome.json"
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, MutableMapping, Optional, Sequence

import requests
import uuid

LOGGER = logging.getLogger(__name__)


GRAPHQL_ENDPOINT = "https://www.walmart.ca/api/graphql"
GRAPHQL_OPERATION = "search"
DEFAULT_FACETS = "clearance:true"
DEFAULT_SECTIONS = {
    "toys": 30,
    "electronics": 30,
    "kitchen": 30,
    "home": 30,
}
DEFAULT_HEADERS = {
    "accept": "application/json, text/plain, */*",
    "accept-language": "fr-CA,fr;q=0.9,en-CA;q=0.8,en;q=0.7",
    "content-type": "application/json",
    "origin": "https://www.walmart.ca",
    "referer": "https://www.walmart.ca/fr/clearance",
    "user-agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "x-apollo-operation-name": GRAPHQL_OPERATION,
    "x-apollo-operation-type": "query",
    "x-requested-with": "XMLHttpRequest",
}
SECTION_KEYWORDS = {
    "toys": (
        "toy",
        "jouet",
        "kid",
        "child",
        "game",
        "lego",
        "baby",
    ),
    "electronics": (
        "elect",
        "tech",
        "informatique",
        "computer",
        "laptop",
        "phone",
        "audio",
        "video",
        "gaming",
    ),
    "kitchen": (
        "kitchen",
        "cuisine",
        "cook",
        "appliance",
        "culinary",
        "dining",
        "cuisson",
    ),
    "home": (
        "home",
        "maison",
        "decor",
        "furniture",
        "outdoor",
        "garden",
        "patio",
        "bath",
        "bed",
        "storage",
        "tool",
        "improvement",
    ),
}


@dataclass
class ProductRecord:
    """Representation of a product tailored for JSON serialisation."""

    title: str
    url: str
    section: str
    image: str
    price: float
    sale_price: float
    store: str
    city: str

    def as_dict(self) -> Dict[str, object]:
        return {
            "title": self.title,
            "url": self.url,
            "section": self.section,
            "image": self.image,
            "price": self.price,
            "sale_price": self.sale_price,
            "store": self.store,
            "city": self.city,
        }


class WalmartClearanceScraper:
    """Thin wrapper around Walmart Canada's GraphQL search endpoint."""

    def __init__(
        self,
        store_id: int,
        *,
        city: str,
        session: Optional[requests.Session] = None,
        sections: Optional[MutableMapping[str, int]] = None,
        language: str = "fr-CA",
        facets: str = DEFAULT_FACETS,
        page_size: int = 24,
        max_pages: Optional[int] = None,
        timeout: float = 30.0,
    ) -> None:
        self.store_id = store_id
        self.city = city
        self.language = language
        self.facets = facets
        self.page_size = page_size
        self.max_pages = max_pages
        self.timeout = timeout
        self.sections = sections or DEFAULT_SECTIONS.copy()
        self.session = session or requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)
        # Allow overriding the default Accept-Language header.
        if language:
            self.session.headers["accept-language"] = (
                f"{language},en-CA;q=0.8,en;q=0.7"
            )
        self.session.headers["wm_store_id"] = str(self.store_id)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def scrape(self) -> List[ProductRecord]:
        """Return a list of clearance products for the configured store."""

        LOGGER.info(
            "Fetching Walmart clearance deals for store %s", self.store_id
        )
        collected: Dict[str, List[ProductRecord]] = {
            name: [] for name in self.sections
        }
        seen_skus: set[str] = set()
        page = 1

        while True:
            if self.max_pages is not None and page > self.max_pages:
                LOGGER.debug("Reached the user-defined page limit (%s)", self.max_pages)
                break

            payload = self._build_payload(page)
            LOGGER.debug("Requesting page %s with payload %s", page, payload)
            response = self.session.post(
                GRAPHQL_ENDPOINT,
                json=payload,
                timeout=self.timeout,
                headers={
                    "wm_qos.correlation_id": str(uuid.uuid4()),
                    "wm_store_id": str(self.store_id),
                },
            )
            if response.status_code != requests.codes.ok:
                LOGGER.error("=== Walmart GraphQL ERROR ===")
                LOGGER.error("Status: %s", response.status_code)
                LOGGER.error(response.text[:1000])
                response.raise_for_status()
            response.raise_for_status()

            try:
                data = response.json()
            except ValueError:
                LOGGER.error("Failed to decode Walmart response: %s", response.text[:1000])
                raise
            if "errors" in data:
                raise RuntimeError(f"GraphQL returned errors: {data['errors']}")

            search_results = data.get("data", {}).get("search")
            if not search_results:
                LOGGER.warning("No search results returned for page %s", page)
                break

            total_count = search_results.get("totalCount") or 0
            results = search_results.get("results") or []
            LOGGER.debug(
                "Received %s results (total available: %s)",
                len(results),
                total_count,
            )

            for entry in results:
                product = self._extract_product(entry)
                if not product:
                    continue

                sku = self._extract_sku(product)
                if sku in seen_skus:
                    continue
                seen_skus.add(sku)

                record = self._build_record(product)
                if record is None:
                    continue

                section = self._classify_section(product, record.title)
                if section not in collected:
                    LOGGER.debug(
                        "Discarding product %s because section '%s' is not tracked",
                        sku,
                        section,
                    )
                    continue

                if len(collected[section]) >= self.sections[section]:
                    continue

                collected[section].append(record)

            if all(len(collected[name]) >= limit for name, limit in self.sections.items()):
                LOGGER.info("Collected the requested number of products for each section")
                break

            processed = page * self.page_size
            if total_count and processed >= total_count:
                LOGGER.info(
                    "Processed all available results (%s >= %s)", processed, total_count
                )
                break

            if not results:
                LOGGER.info("No more results returned; stopping pagination")
                break

            page += 1

        # Sort items within each section by discount, highest first, then by sale price.
        output: List[ProductRecord] = []
        for section in self.sections:
            records = collected.get(section, [])
            records.sort(
                key=lambda item: (
                    (item.price or 0) - (item.sale_price or 0),
                    -(item.sale_price or 0),
                ),
                reverse=True,
            )
            output.extend(records)

        LOGGER.info("Total products selected: %s", len(output))
        return output

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _build_payload(self, page: int) -> Dict[str, object]:
        variables = {
            "query": "clearance",
            "page": page,
            "count": self.page_size,
            "storeId": str(self.store_id),
            "facets": self.facets,
            "returnFacets": False,
            "sort": "PRICE_LOW_TO_HIGH",
        }
        return {
            "operationName": GRAPHQL_OPERATION,
            "variables": variables,
            "query": (
                "query search($query: String!, $page: Int, $count: Int, $storeId: String, "
                "$facets: String, $returnFacets: Boolean, $sort: String) { "
                "search(query: $query, page: $page, count: $count, storeId: $storeId, "
                "facets: $facets, returnFacets: $returnFacets, sort: $sort) { "
                "totalCount results { ... on ProductResult { product { sku name shortDescription "
                "price { price salePrice } images { url } productUrl category { path name } "
                "department { name } } } } } }"
            ),
        }

    def _extract_product(self, entry: object) -> Optional[Dict[str, object]]:
        if not isinstance(entry, dict):
            return None

        for key in ("product", "item", "data", "productResult"):
            candidate = entry.get(key)
            if isinstance(candidate, dict):
                return candidate
        if "items" in entry and isinstance(entry["items"], list):
            for candidate in entry["items"]:
                product = self._extract_product(candidate)
                if product:
                    return product
        return entry if entry.get("name") else None

    @staticmethod
    def _extract_sku(product: Dict[str, object]) -> str:
        for key in ("sku", "usItemId", "id", "itemId", "productId"):
            value = product.get(key)
            if value:
                return str(value)
        return product.get("productUrl", "unknown")

    def _build_record(self, product: Dict[str, object]) -> Optional[ProductRecord]:
        title = self._extract_title(product)
        if not title:
            return None

        image = self._extract_image(product)
        if not image:
            return None

        price_info = product.get("price") or {}
        price = self._parse_price(price_info.get("price"))
        sale_price = self._parse_price(
            price_info.get("salePrice")
            or price_info.get("offerPrice")
            or price_info.get("currentPrice")
        )

        if price is None or sale_price is None:
            return None
        if sale_price >= price:
            return None

        url = product.get("productUrl") or product.get("canonicalUrl")
        if not url:
            return None
        if url.startswith("/"):
            url = f"https://www.walmart.ca{url}"

        return ProductRecord(
            title=title,
            url=url,
            section="home",  # Placeholder; actual value determined later.
            image=image,
            price=price,
            sale_price=sale_price,
            store="Walmart",
            city=self.city,
        )

    def _classify_section(self, product: Dict[str, object], fallback: str) -> str:
        candidates: List[str] = []
        category = product.get("category")
        if isinstance(category, dict):
            for key in ("path", "name"):
                value = category.get(key)
                if value:
                    candidates.append(str(value))
        category_path = product.get("categoryPath")
        if isinstance(category_path, str):
            candidates.append(category_path)
        department = product.get("department")
        if isinstance(department, dict) and department.get("name"):
            candidates.append(str(department["name"]))
        candidates.append(fallback)

        for text in candidates:
            normalised = self._normalise(text)
            for section, keywords in SECTION_KEYWORDS.items():
                if any(keyword in normalised for keyword in keywords):
                    return section
        return "home"

    @staticmethod
    def _normalise(text: str) -> str:
        decomposed = unicodedata.normalize("NFKD", text)
        cleaned = "".join(
            char for char in decomposed if not unicodedata.combining(char)
        )
        return cleaned.lower()

    @staticmethod
    def _extract_title(product: Dict[str, object]) -> Optional[str]:
        title_candidates: Sequence[str] = (
            product.get("name"),
            product.get("displayName"),
            product.get("shortDescription"),
        )
        for candidate in title_candidates:
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
        description = product.get("description")
        if isinstance(description, dict):
            for key in ("name", "short", "long"):
                value = description.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
        return None

    @staticmethod
    def _extract_image(product: Dict[str, object]) -> Optional[str]:
        images = product.get("images")
        if isinstance(images, list):
            for entry in images:
                if isinstance(entry, dict) and entry.get("url"):
                    return str(entry["url"])
        image = product.get("image") or product.get("imageUrl")
        if isinstance(image, str) and image.strip():
            return image.strip()
        return None

    @staticmethod
    def _parse_price(value: object) -> Optional[float]:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            cleaned = (
                value.replace("$", "")
                .replace("€", "")
                .replace(",", "")
                .strip()
            )
            try:
                return float(cleaned)
            except ValueError:
                return None
        return None


def parse_section_argument(values: Optional[Iterable[str]]) -> Dict[str, int]:
    if not values:
        return DEFAULT_SECTIONS.copy()

    sections: Dict[str, int] = {}
    for raw in values:
        if "=" not in raw:
            raise argparse.ArgumentTypeError(
                f"Invalid section definition '{raw}'. Expected name=count format."
            )
        name, count = raw.split("=", 1)
        name = name.strip().lower()
        try:
            sections[name] = int(count)
        except ValueError as exc:
            raise argparse.ArgumentTypeError(
                f"Invalid section count '{count}' for section '{name}'"
            ) from exc
    return sections


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Scrape Walmart Canada clearance deals for a specific store.",
    )
    parser.add_argument(
        "--store-id",
        type=int,
        default=1076,
        help="Walmart store identifier (defaults to 1076 for Saint-Jérôme).",
    )
    parser.add_argument(
        "--city",
        type=str,
        default="Saint-Jérôme",
        help="City name to include in the output records.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Path to the JSON file that will receive the scraped dataset.",
    )
    parser.add_argument(
        "--section",
        dest="sections",
        action="append",
        help="Section definition in the form name=count. Can be provided multiple times.",
    )
    parser.add_argument(
        "--language",
        type=str,
        default="fr-CA",
        help="Preferred language for the Walmart responses (default: fr-CA).",
    )
    parser.add_argument(
        "--facets",
        type=str,
        default=DEFAULT_FACETS,
        help="Facets to send to the Walmart search endpoint (default: clearance:true).",
    )
    parser.add_argument(
        "--page-size",
        type=int,
        default=24,
        help="Number of items to request per page (default: 24).",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help="Maximum number of result pages to fetch (default: unlimited).",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="HTTP timeout for the Walmart requests (seconds).",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging output.",
    )
    return parser


def configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_argument_parser()
    args = parser.parse_args(argv)

    configure_logging(args.verbose)
    sections = parse_section_argument(args.sections)

    scraper = WalmartClearanceScraper(
        args.store_id,
        city=args.city,
        sections=sections,
        language=args.language,
        facets=args.facets,
        page_size=args.page_size,
        max_pages=args.max_pages,
        timeout=args.timeout,
    )

    try:
        products = scraper.scrape()
    except requests.HTTPError as exc:
        LOGGER.error("HTTP error while fetching data: %s", exc)
        return 2
    except requests.RequestException as exc:
        LOGGER.error("Network error while fetching data: %s", exc)
        return 3
    except Exception as exc:  # pragma: no cover - defensive catch-all
        LOGGER.exception("Unexpected error: %s", exc)
        return 4

    output_path = args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    serialised = [product.as_dict() for product in products]
    output_path.write_text(
        json.dumps(serialised, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    LOGGER.info("Wrote %s records to %s", len(serialised), output_path)
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    sys.exit(main())
