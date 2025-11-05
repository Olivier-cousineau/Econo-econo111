"""Automated scraper for Best Buy Canada clearance collections.

This module fetches the clearance catalog exposed via the official collection
endpoint and normalises the payload into the different JSON datasets consumed
by the static site.  It also mirrors the aggregate feed into every city level
dataset to keep the experience consistent across Best Buy branches.

Usage::

    python -m services.bestbuy

The script can be configured through CLI flags or environment variables when
used in a workflow.  It is intentionally resilient to payload changes – it
attempts to discover the relevant fields instead of hard-coding a brittle
schema extracted from the web application.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple
from urllib.parse import urljoin

import requests

from config.settings import get_settings

LOGGER = logging.getLogger(__name__)


BESTBUY_DOMAIN = "https://www.bestbuy.ca"
BESTBUY_COLLECTION_API = f"{BESTBUY_DOMAIN}/api/tprod/v1/collection"
DEFAULT_COLLECTION_ID = "113065"
DEFAULT_QUERY_PATH = (
    "soldandshippedby0enrchstring:Best Buy;"
    "currentoffers0enrchstring:On Clearance|Open Box"
)
DEFAULT_REFERER = (
    "https://www.bestbuy.ca/en-ca/collection/clearance-products/113065"
    "?path=soldandshippedby0enrchstring%253ABest%2BBuy%253Bcurrentoffers0enrchstring%253AOn%2BClearance%257COpen%2BBox"
)
DEFAULT_PAGE_SIZE = 100
DEFAULT_LANGUAGE = "en-CA"
MAX_PAGES = 25

SESSION_HEADERS: Mapping[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-CA,en;q=0.9,fr-CA;q=0.8,fr;q=0.7",
    "Origin": BESTBUY_DOMAIN,
    "Referer": DEFAULT_REFERER,
    "Connection": "keep-alive",
}


@dataclass(frozen=True)
class BestBuyProduct:
    sku: str
    name: str
    url: str
    regular_price: Optional[Decimal]
    sale_price: Optional[Decimal]
    image: Optional[str]
    availability: Optional[str]
    store: Optional[str]

    def to_detailed_dict(self, store_label: Optional[str] = None) -> Dict[str, Any]:
        return {
            "product_name": self.name,
            "sku": self.sku,
            "regular_price": decimal_to_number(self.regular_price),
            "sale_price": decimal_to_number(self.sale_price),
            "image": self.image,
            "product_link": self.url,
            "availability": self.availability,
            "store": store_label or self.store or "Best Buy",
        }

    def to_summary_dict(self, city: str, store_label: Optional[str] = None) -> Dict[str, Any]:
        return {
            "title": self.name,
            "image": self.image,
            "price": decimal_to_number(self.regular_price),
            "salePrice": decimal_to_number(self.sale_price),
            "store": store_label or self.store or "Best Buy",
            "city": city,
            "url": self.url,
        }


def decimal_to_number(value: Optional[Decimal]) -> Optional[float]:
    if value is None:
        return None
    if not value.is_finite():
        return None
    quantised = value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return float(quantised)


def normalise_price(value: Any) -> Optional[Decimal]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        try:
            return Decimal(str(value))
        except InvalidOperation:
            return None
    if isinstance(value, str):
        cleaned = value.strip()
        if not cleaned:
            return None
        cleaned = cleaned.replace(",", "")
        cleaned = re.sub(r"[^0-9.\-]", "", cleaned)
        if not cleaned:
            return None
        try:
            return Decimal(cleaned)
        except InvalidOperation:
            return None
    if isinstance(value, Mapping):
        for key in ("value", "amount", "price", "sale", "current", "low", "high"):
            if key in value:
                candidate = normalise_price(value[key])
                if candidate is not None:
                    return candidate
    return None


def first_non_empty(values: Iterable[Any]) -> Optional[Any]:
    for value in values:
        if value is None:
            continue
        if isinstance(value, str):
            trimmed = value.strip()
            if trimmed:
                return trimmed
            continue
        if isinstance(value, (int, float, Decimal)):
            return value
        if isinstance(value, Mapping):
            nested = first_non_empty(value.values())
            if nested is not None:
                return nested
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            nested = first_non_empty(value)
            if nested is not None:
                return nested
    return None


def ensure_absolute_url(candidate: Optional[str]) -> Optional[str]:
    if not candidate:
        return None
    trimmed = candidate.strip()
    if not trimmed:
        return None
    if trimmed.startswith("//"):
        return "https:" + trimmed
    if trimmed.startswith("http://") or trimmed.startswith("https://"):
        return trimmed
    if trimmed.startswith("/"):
        return urljoin(BESTBUY_DOMAIN, trimmed)
    return urljoin(f"{BESTBUY_DOMAIN}/", trimmed)


def get_nested(item: Mapping[str, Any], *keys: str) -> Optional[Any]:
    current: Any = item
    for key in keys:
        if not isinstance(current, Mapping):
            return None
        current = current.get(key)
        if current is None:
            return None
    return current


def discover_products(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, list):
        if payload and all(isinstance(entry, Mapping) for entry in payload):
            return [dict(entry) for entry in payload]  # copy to detach references
        products: List[Dict[str, Any]] = []
        for item in payload:
            products.extend(discover_products(item))
        return products

    if isinstance(payload, Mapping):
        direct_candidates: Sequence[str] = (
            "products",
            "items",
            "collectionItems",
            "results",
            "skus",
        )
        for key in direct_candidates:
            value = payload.get(key)
            if isinstance(value, list) and value and all(
                isinstance(entry, Mapping) for entry in value
            ):
                return [dict(entry) for entry in value]

        nested_products: List[Dict[str, Any]] = []
        for value in payload.values():
            nested_products.extend(discover_products(value))
        return nested_products

    return []


def parse_product(product: Mapping[str, Any]) -> Optional[BestBuyProduct]:
    sku_candidates = (
        product.get("sku"),
        product.get("skuId"),
        get_nested(product, "productSku", "sku"),
        get_nested(product, "links", "sku"),
    )
    sku_value = first_non_empty(sku_candidates)
    if not sku_value:
        return None
    sku = str(sku_value).strip()
    if not sku:
        return None

    name_candidates = (
        get_nested(product, "names", "title"),
        product.get("name"),
        get_nested(product, "details", "name"),
        product.get("title"),
        product.get("shortDescription"),
        product.get("description"),
    )
    name_value = first_non_empty(name_candidates)
    if not name_value:
        return None
    name = str(name_value).strip()
    if not name:
        return None

    url_candidates = (
        get_nested(product, "links", "product"),
        product.get("productUrl"),
        product.get("url"),
        get_nested(product, "product", "link"),
    )
    url_value = first_non_empty(url_candidates)
    url = ensure_absolute_url(str(url_value)) if url_value else None
    if not url:
        return None

    image_candidates = (
        get_nested(product, "images", "standard"),
        get_nested(product, "images", "standardRes"),
        get_nested(product, "primaryImage", "href"),
        get_nested(product, "primaryMedia", "thumbnail"),
        get_nested(product, "primaryMedia", "image"),
        get_nested(product, "media", "thumbnail"),
        product.get("image"),
        product.get("imageUrl"),
        product.get("thumbnailImage"),
        product.get("thumbnail"),
    )
    image_url = ensure_absolute_url(first_non_empty(image_candidates))

    regular_price_candidates = (
        product.get("regularPrice"),
        get_nested(product, "offers", "prices", "regular"),
        get_nested(product, "offers", "regular"),
        get_nested(product, "prices", "regular"),
        product.get("price"),
        get_nested(product, "pricing", "regular"),
    )
    sale_price_candidates = (
        product.get("salePrice"),
        get_nested(product, "offers", "prices", "sale"),
        get_nested(product, "offers", "prices", "current"),
        get_nested(product, "offers", "sale"),
        get_nested(product, "prices", "current"),
        get_nested(product, "pricing", "sale"),
        product.get("offerPrice"),
        product.get("dealPrice"),
    )

    regular_price = normalise_price(first_non_empty(regular_price_candidates))
    sale_price = normalise_price(first_non_empty(sale_price_candidates))

    if regular_price is None and sale_price is not None:
        regular_price = sale_price
    if sale_price is None and regular_price is not None:
        sale_price = regular_price

    availability_candidates = (
        get_nested(product, "availability", "summary"),
        get_nested(product, "availability", "status"),
        product.get("availability"),
        get_nested(product, "fulfillment", "shipping", "status"),
        get_nested(product, "fulfillment", "pickup", "status"),
    )
    availability_value = first_non_empty(availability_candidates)
    availability = str(availability_value).strip() if availability_value else None

    store_candidates = (
        get_nested(product, "seller", "name"),
        product.get("sellerName"),
        get_nested(product, "brand", "name"),
        product.get("brand"),
        product.get("vendor"),
    )
    store_value = first_non_empty(store_candidates)
    store_label = str(store_value).strip() if store_value else None

    return BestBuyProduct(
        sku=sku,
        name=name,
        url=url,
        regular_price=regular_price,
        sale_price=sale_price,
        image=image_url,
        availability=availability,
        store=store_label,
    )


def fetch_collection(
    session: requests.Session,
    collection_id: str,
    query_path: str,
    *,
    page_size: int = DEFAULT_PAGE_SIZE,
    language: str = DEFAULT_LANGUAGE,
    max_pages: int = MAX_PAGES,
) -> List[BestBuyProduct]:
    collected: Dict[str, BestBuyProduct] = {}

    for page in range(1, max_pages + 1):
        params = {
            "path": query_path,
            "page": page,
            "pageSize": page_size,
            "include": "facets,availability,details,media,offers",
            "language": language,
        }
        url = f"{BESTBUY_COLLECTION_API}/{collection_id}"
        LOGGER.debug("Fetching Best Buy collection page %s", page)
        try:
            response = session.get(url, params=params, timeout=30)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise RuntimeError(f"Best Buy request failed on page {page}: {exc}") from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise RuntimeError("Réponse JSON invalide reçue depuis l'API Best Buy.") from exc

        raw_products = discover_products(payload)
        if not raw_products:
            LOGGER.warning("Aucun produit n'a été extrait pour la page %s", page)
            break

        added_on_page = 0
        for raw_product in raw_products:
            parsed = parse_product(raw_product)
            if not parsed:
                continue
            if parsed.sku in collected:
                continue
            collected[parsed.sku] = parsed
            added_on_page += 1

        LOGGER.info("Page %s · %s nouveaux produits", page, added_on_page)

        if len(raw_products) < page_size:
            break

    products = list(collected.values())
    products.sort(key=lambda p: (
        p.sale_price if p.sale_price is not None else Decimal("Infinity"),
        p.name,
    ))
    return products


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def format_city_label(slug: str, metadata: Mapping[str, str]) -> str:
    slug_lower = slug.lower().replace("_", "-")
    variants = {slug_lower}
    if slug_lower.startswith("st-"):
        variants.add(slug_lower.replace("st-", "saint-", 1))
        variants.add(slug_lower.replace("st-", "ste-", 1))
    if slug_lower.startswith("ste-"):
        variants.add(slug_lower.replace("ste-", "sainte-", 1))
    for variant in list(variants):
        if variant in metadata:
            return metadata[variant]
    words = [word.capitalize() for word in slug_lower.split("-") if word]
    return "-".join(words) if words else slug


def load_store_metadata(root: Path) -> Dict[str, str]:
    stores_dir = root / "data" / "best-buy" / "stores"
    metadata: Dict[str, str] = {}
    if not stores_dir.exists() or not stores_dir.is_dir():
        return metadata
    for path in stores_dir.glob("*.json"):
        try:
            raw = path.read_text(encoding="utf-8")
            payload = json.loads(raw)
        except (OSError, ValueError):
            continue
        if isinstance(payload, Mapping):
            name = payload.get("name")
            if isinstance(name, str) and name.strip():
                metadata[path.stem.lower()] = name.strip()
    return metadata


def mirror_to_city_files(
    products: Sequence[BestBuyProduct],
    root: Path,
    *,
    city_metadata: Mapping[str, str],
) -> None:
    best_buy_dir = root / "data" / "best-buy"
    liquidations_dir = best_buy_dir / "liquidations"

    detailed_payload = [product.to_detailed_dict() for product in products]
    write_json(root / "data" / "bestbuy_liquidation.json", detailed_payload)

    summary_payload = [
        product.to_summary_dict("En ligne", store_label=product.store or "Best Buy")
        for product in products
    ]
    write_json(best_buy_dir / "liquidations.json", summary_payload)

    city_files = [
        path
        for path in best_buy_dir.glob("*.json")
        if path.name not in {"liquidations.json", "README.md"}
    ]
    city_slugs = {path.stem for path in city_files}

    for city_file in city_files:
        city_slug = city_file.stem
        city_label = format_city_label(city_slug, city_metadata)
        city_summary = [
            product.to_summary_dict(city_label, store_label=f"Best Buy {city_label}")
            for product in products
        ]
        write_json(city_file, city_summary)

    liquidation_existing_slugs = {
        path.stem for path in liquidations_dir.glob("*.json") if path.is_file()
    }
    combined_slugs = city_slugs | liquidation_existing_slugs
    if not combined_slugs:
        combined_slugs = {"saint-jerome"}

    for city_slug in sorted(combined_slugs):
        city_label = format_city_label(city_slug, city_metadata)
        city_detailed = [
            product.to_detailed_dict(store_label=f"Best Buy {city_label}")
            for product in products
        ]
        write_json(liquidations_dir / f"{city_slug}.json", city_detailed)


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Collecte les liquidations Best Buy.")
    parser.add_argument(
        "--collection-id",
        default=os.environ.get("BESTBUY_COLLECTION_ID", DEFAULT_COLLECTION_ID),
        help="Identifiant numérique de la collection Best Buy à interroger.",
    )
    parser.add_argument(
        "--query-path",
        default=os.environ.get("BESTBUY_QUERY_PATH", DEFAULT_QUERY_PATH),
        help="Filtre 'path' transmis à l'API (non encodé).",
    )
    parser.add_argument(
        "--page-size",
        type=int,
        default=int(os.environ.get("BESTBUY_PAGE_SIZE", DEFAULT_PAGE_SIZE)),
        help="Nombre d'articles à récupérer par page (défaut: 100).",
    )
    parser.add_argument(
        "--language",
        default=os.environ.get("BESTBUY_LANGUAGE", DEFAULT_LANGUAGE),
        help="Code langue à transmettre à l'API (ex. en-CA, fr-CA).",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=int(os.environ.get("BESTBUY_MAX_PAGES", MAX_PAGES)),
        help="Nombre maximum de pages à parcourir.",
    )
    parser.add_argument(
        "--data-root",
        type=Path,
        default=None,
        help="Chemin du dossier racine contenant le répertoire data/.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Active le niveau de log DEBUG pour faciliter le diagnostic.",
    )
    return parser


def create_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(SESSION_HEADERS)
    return session


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_argument_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)

    settings = get_settings()
    root_path = args.data_root or settings.base_dir
    root_path = root_path.resolve()

    LOGGER.info("Collecte de la collection %s", args.collection_id)
    session = create_session()

    products = fetch_collection(
        session,
        collection_id=args.collection_id,
        query_path=args.query_path,
        page_size=args.page_size,
        language=args.language,
        max_pages=args.max_pages,
    )

    if not products:
        LOGGER.warning("Aucun produit collecté depuis la collection Best Buy.")
        return 0

    LOGGER.info("%s produits retenus après déduplication", len(products))
    city_metadata = load_store_metadata(root_path)
    mirror_to_city_files(products, root_path, city_metadata=city_metadata)
    LOGGER.info("Flux Best Buy mis à jour dans %s", root_path)
    return 0


if __name__ == "__main__":  # pragma: no cover - entrée CLI
    raise SystemExit(main())

