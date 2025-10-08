"""Scraper for Best Buy Canada in-store clearance offers."""

from __future__ import annotations

import argparse
import json
import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence, Set, Tuple
from urllib.parse import urljoin

import requests

BASE_DOMAIN = "https://www.bestbuy.ca"
CLEARANCE_ENDPOINT = f"{BASE_DOMAIN}/api/offers/v1/page/clearance"
DEFAULT_LANGUAGE = "fr"
LANGUAGE_ALIASES: Dict[str, str] = {
    "fr": "fr-CA",
    "en": "en-CA",
}
DEFAULT_TIMEOUT = 20
DEFAULT_MAX_RETRIES = 6
DEFAULT_DELAY_RANGE: Tuple[float, float] = (1.0, 2.5)
DEFAULT_PAGE_SIZE = 100
DEFAULT_OUTPUT_DIR = Path("data/best-buy")
DEFAULT_AGGREGATED_FILENAME = "liquidations.json"
STORES_JSON = Path("data/best-buy/stores.json")

USER_AGENTS: Tuple[str, ...] = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
)


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def slugify(value: str) -> str:
    import re
    import unicodedata

    normalized = unicodedata.normalize("NFKD", value)
    ascii_only = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    ascii_only = ascii_only.lower()
    ascii_only = re.sub(r"[^a-z0-9]+", "-", ascii_only).strip("-")
    return ascii_only or "store"


def coerce_price(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        value = value.strip().replace("$", "").replace(",", "")
        if not value:
            return None
        try:
            return float(value)
        except ValueError:
            return None
    return None


def normalize_token(value: str) -> Set[str]:
    token = slugify(value)
    variants = {token}
    variants.add(token.replace("-", ""))
    variants.add(token.replace(" ", ""))
    return {item for item in variants if item}


def build_headers(language: str) -> Dict[str, str]:
    lang_header = LANGUAGE_ALIASES.get(language, language)
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "application/json",
        "Accept-Language": f"{lang_header},fr;q=0.9,en;q=0.8",
        "Cache-Control": "no-cache",
    }


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class Store:
    label: str
    slug: str
    city: str
    address: str
    store_number: str

    def normalized_city(self) -> str:
        base = (self.city or "").strip()
        replacements = {
            "St.": "Saint",
            "Ste.": "Sainte",
            "St ": "Saint ",
            "Ste ": "Sainte ",
            "St-": "Saint-",
            "Ste-": "Sainte-",
        }
        for needle, replacement in replacements.items():
            base = base.replace(needle, replacement)
        return base or self.label

    def output_stem(self) -> str:
        candidates = [self.label, self.city, self.slug]
        for candidate in candidates:
            if not candidate:
                continue
            slug = slugify(candidate)
            if slug:
                return slug
        return slugify(self.store_number or "store")

    def matches_filters(self, filters: Set[str]) -> bool:
        if not filters:
            return True
        tokens: Set[str] = set()
        for candidate in (self.label, self.slug, self.city, self.normalized_city(), self.store_number):
            if candidate:
                tokens.update(normalize_token(str(candidate)))
        return any(token in filters for token in tokens)


@dataclass(slots=True)
class Deal:
    title: str
    price: float
    sale_price: float
    url: str
    image: Optional[str]
    sku: Optional[str]

    def to_payload(self, store: Store) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "title": self.title,
            "image": self.image or "",
            "price": round(self.price, 2),
            "salePrice": round(self.sale_price, 2),
            "store": "Best Buy",
            "city": store.normalized_city(),
            "url": self.url,
        }
        if self.sku:
            payload["sku"] = self.sku
        return payload


# ---------------------------------------------------------------------------
# Store loading & filtering
# ---------------------------------------------------------------------------


def load_stores(path: Path = STORES_JSON) -> List[Store]:
    if not path.exists():
        raise FileNotFoundError(f"Stores manifest not found: {path}")

    with path.open("r", encoding="utf-8") as handle:
        raw: Sequence[Dict[str, Any]] = json.load(handle)

    stores: List[Store] = []
    for entry in raw:
        label = str(entry.get("label") or "").strip()
        slug = str(entry.get("slug") or "").strip()
        city = str(entry.get("city") or "").strip()
        address = str(entry.get("address") or "").strip()
        store_number = str(entry.get("storeNumber") or entry.get("store_number") or "").strip()
        if not store_number:
            continue
        stores.append(Store(label=label, slug=slug, city=city, address=address, store_number=store_number))
    return stores


# ---------------------------------------------------------------------------
# Networking helpers
# ---------------------------------------------------------------------------


def fetch_json(
    params: Dict[str, Any],
    *,
    max_retries: int,
    timeout: int,
    delay_range: Tuple[float, float],
    language: str,
) -> Dict[str, Any]:
    last_error: Optional[Exception] = None
    for attempt in range(1, max_retries + 1):
        try:
            response = requests.get(
                CLEARANCE_ENDPOINT,
                params=params,
                headers=build_headers(language),
                timeout=timeout,
            )
            if response.status_code == 404:
                return {}
            response.raise_for_status()
            return response.json()
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            if attempt >= max_retries:
                break
            delay = random.uniform(*delay_range)
            time.sleep(delay)
    if last_error:
        raise last_error
    return {}


def iter_products(
    store: Store,
    *,
    language: str,
    max_retries: int,
    timeout: int,
    delay_range: Tuple[float, float],
    page_size: int,
) -> Iterator[Dict[str, Any]]:
    lang_code = LANGUAGE_ALIASES.get(language, language)
    page = 1
    total_pages: Optional[int] = None

    while total_pages is None or page <= total_pages:
        params = {
            "storeId": store.store_number,
            "page": page,
            "pageSize": page_size,
            "lang": lang_code,
            "include": "facets,attributes,availability,offers",
        }
        payload = fetch_json(
            params,
            max_retries=max_retries,
            timeout=timeout,
            delay_range=delay_range,
            language=language,
        )
        results = payload.get("results") if isinstance(payload, dict) else None
        if not results:
            break
        products = results.get("products") or []
        if not products:
            break
        for product in products:
            if isinstance(product, dict):
                yield product
        pagination = results.get("pagination") if isinstance(results, dict) else None
        if pagination:
            total_pages = int(pagination.get("totalPages") or pagination.get("total_pages") or page)
        else:
            total_pages = page
        page += 1


def parse_product(product: Dict[str, Any], language: str) -> Optional[Deal]:
    title = product.get("name") or product.get("title") or product.get("shortName")
    if not title:
        return None

    prices = product.get("prices") if isinstance(product.get("prices"), dict) else {}
    sale_price = coerce_price(product.get("salePrice"))
    if not sale_price and isinstance(prices, dict):
        sale_price = coerce_price(
            prices.get("current")
            or prices.get("sale")
            or prices.get("value")
            or prices.get("price")
        )
    regular_price = coerce_price(product.get("regularPrice"))
    if not regular_price and isinstance(prices, dict):
        regular_price = coerce_price(
            prices.get("regular")
            or prices.get("was")
            or prices.get("base")
            or prices.get("original")
        )
    if not regular_price:
        regular_price = sale_price
    if not sale_price or not regular_price:
        return None

    image = None
    for key in ("thumbnailImage", "image", "imageUrl", "primaryImage"):
        candidate = product.get(key)
        if isinstance(candidate, str) and candidate:
            image = candidate
            break
    if not image and isinstance(product.get("images"), dict):
        images = product["images"]
        for key in ("main", "primary", "thumbnail"):
            candidate = images.get(key)
            if isinstance(candidate, str) and candidate:
                image = candidate
                break
        if not image and isinstance(images.get("gallery"), list):
            for entry in images["gallery"]:
                if isinstance(entry, str) and entry:
                    image = entry
                    break
                if isinstance(entry, dict):
                    candidate = entry.get("href") or entry.get("url")
                    if isinstance(candidate, str) and candidate:
                        image = candidate
                        break
            if not image and isinstance(images.get("thumbnails"), list):
                for entry in images["thumbnails"]:
                    if isinstance(entry, str) and entry:
                        image = entry
                        break

    url = product.get("productUrl") or product.get("url") or product.get("link")
    if isinstance(url, str) and url:
        url = urljoin(BASE_DOMAIN, url)
    else:
        return None

    sku = None
    for key in ("sku", "skuId", "skuNumber", "code", "id"):
        candidate = product.get(key)
        if isinstance(candidate, (str, int)):
            sku = str(candidate)
            break

    return Deal(
        title=str(title).strip(),
        price=float(regular_price),
        sale_price=float(sale_price),
        url=url,
        image=image,
        sku=sku,
    )


def scrape_store(
    store: Store,
    *,
    language: str,
    max_retries: int,
    timeout: int,
    delay_range: Tuple[float, float],
    page_size: int,
) -> List[Deal]:
    deals: List[Deal] = []
    seen_skus: Set[str] = set()
    for product in iter_products(
        store,
        language=language,
        max_retries=max_retries,
        timeout=timeout,
        delay_range=delay_range,
        page_size=page_size,
    ):
        deal = parse_product(product, language)
        if not deal:
            continue
        if deal.sku and deal.sku in seen_skus:
            continue
        if deal.sku:
            seen_skus.add(deal.sku)
        deals.append(deal)
    return deals


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Extraction des aubaines en liquidation des magasins Best Buy au Québec.",
    )
    parser.add_argument(
        "--store",
        dest="stores",
        action="append",
        default=[],
        help="Filtre les magasins (ville, identifiant ou slug).",
    )
    parser.add_argument(
        "--language",
        choices=sorted(LANGUAGE_ALIASES),
        default=DEFAULT_LANGUAGE,
        help="Langue des résultats (fr ou en).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Dossier de sortie pour les fichiers JSON individuels.",
    )
    parser.add_argument(
        "--aggregated-path",
        type=Path,
        default=None,
        help="Chemin du fichier d'agrégation global (défaut: data/best-buy/liquidations.json).",
    )
    parser.add_argument(
        "--page-size",
        type=int,
        default=DEFAULT_PAGE_SIZE,
        help="Nombre d'articles par page à demander (défaut: 100).",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=DEFAULT_MAX_RETRIES,
        help="Nombre maximal de tentatives HTTP par requête.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT,
        help="Délai d'attente (secondes) pour les requêtes HTTP.",
    )
    parser.add_argument(
        "--delay",
        nargs=2,
        type=float,
        metavar=("MIN", "MAX"),
        default=None,
        help="Intervalle (secondes) utilisé entre les tentatives.",
    )
    return parser


def ensure_directory(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def save_deals(path: Path, deals: Iterable[Deal], store: Store) -> None:
    ensure_directory(path)
    payload = [deal.to_payload(store) for deal in deals]
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def main(argv: Optional[Sequence[str]] = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    stores = load_stores()
    filters = set()
    for token in args.stores:
        filters.update(normalize_token(token))
    selected = [store for store in stores if store.matches_filters(filters)]
    if not selected:
        parser.error("Aucun magasin ne correspond aux filtres fournis.")

    delay_range = tuple(args.delay) if args.delay else DEFAULT_DELAY_RANGE
    aggregated_path = args.aggregated_path or args.output_dir / DEFAULT_AGGREGATED_FILENAME

    aggregated: List[Dict[str, Any]] = []

    for store in selected:
        print(f"→ Extraction pour {store.label} ({store.store_number})…")
        deals = scrape_store(
            store,
            language=args.language,
            max_retries=args.max_retries,
            timeout=args.timeout,
            delay_range=(float(delay_range[0]), float(delay_range[1])),
            page_size=args.page_size,
        )
        deals.sort(key=lambda deal: (deal.sale_price, deal.price, deal.title))
        output_path = args.output_dir / f"{store.output_stem()}.json"
        save_deals(output_path, deals, store)
        aggregated.extend(deal.to_payload(store) for deal in deals)
        print(f"   {len(deals)} offre(s) sauvegardée(s) dans {output_path}.")

    aggregated.sort(key=lambda entry: (entry.get("city", ""), entry.get("salePrice", 0.0)))
    ensure_directory(aggregated_path)
    with aggregated_path.open("w", encoding="utf-8") as handle:
        json.dump(aggregated, handle, ensure_ascii=False, indent=2)
    print(f"Fichier agrégé mis à jour: {aggregated_path}")


if __name__ == "__main__":
    main()
