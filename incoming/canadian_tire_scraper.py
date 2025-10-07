"""Scraper Canadian Tire clearance listings using the bundled ``stores.json`` file."""

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
from bs4 import BeautifulSoup

BASE_DOMAIN = "https://www.canadiantire.ca"
STORE_DETAILS_PATH = "/{language}/store-details/{province}/{slug}.html"
DEFAULT_LANGUAGE = "fr"
DEFAULT_TIMEOUT = 20
DEFAULT_MAX_RETRIES = 6
DEFAULT_DELAY_RANGE: Tuple[float, float] = (1.0, 3.0)
DEFAULT_OUTPUT_DIR = Path("data/canadian-tire")
DEFAULT_AGGREGATED_FILENAME = "liquidations_canadian_tire_qc.json"
STORES_JSON = Path("data/canadian-tire/stores.json")

USER_AGENTS: Tuple[str, ...] = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
)


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------


def slugify(value: str) -> str:
    """Return a lowercase ASCII slug (borrowed from :mod:`walmart_common`)."""

    import re
    import unicodedata

    normalized = unicodedata.normalize("NFKD", value)
    ascii_only = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    ascii_only = ascii_only.lower()
    ascii_only = re.sub(r"[^a-z0-9]+", "-", ascii_only).strip("-")
    return ascii_only or "store"


@dataclass(slots=True)
class Store:
    """Metadata extracted from ``stores.json``."""

    store_id: str
    label: str
    city: str
    province: str
    slug: str
    nickname: Optional[str] = None
    address: str = ""

    def normalized_city(self) -> str:
        base = (self.nickname or self.city or "").strip()
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
        return base or self.city

    @property
    def output_stem(self) -> str:
        base = self.normalized_city() or self.slug
        return slugify(base)

    def url(self, language: str = DEFAULT_LANGUAGE) -> str:
        province_slug = slugify(self.province or "qc")
        return urljoin(
            BASE_DOMAIN,
            STORE_DETAILS_PATH.format(language=language, province=province_slug, slug=self.slug),
        )


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
            "store": "Canadian Tire",
            "city": store.normalized_city(),
            "url": self.url,
        }
        if self.sku:
            payload["sku"] = self.sku
        return payload


# ---------------------------------------------------------------------------
# Loading & filtering stores
# ---------------------------------------------------------------------------


def load_stores(path: Path = STORES_JSON) -> List[Store]:
    if not path.exists():
        raise FileNotFoundError(f"Fichier stores.json introuvable: {path}")

    with path.open("r", encoding="utf-8") as handle:
        raw: Sequence[Dict[str, Any]] = json.load(handle)

    stores: List[Store] = []
    for entry in raw:
        store_id = str(entry.get("store_id") or entry.get("id") or "").strip()
        slug = str(entry.get("slug") or "").strip()
        province = str(entry.get("province") or "QC").strip()
        city = str(entry.get("city") or entry.get("nickname") or "").strip()
        label = str(entry.get("label") or city).strip()
        nickname = entry.get("nickname")
        address = str(entry.get("address") or "").strip()
        if not store_id or not slug:
            continue
        stores.append(
            Store(
                store_id=store_id,
                slug=slug,
                province=province,
                city=city,
                label=label,
                nickname=str(nickname).strip() if nickname else None,
                address=address,
            )
        )
    return stores


def normalize_token(value: str) -> Set[str]:
    token = slugify(value)
    variants = {token}
    variants.add(token.replace("-", ""))
    variants.add(token.replace(" ", ""))
    return {item for item in variants if item}


def store_matches_filters(store: Store, filters: Set[str]) -> bool:
    if not filters:
        return True

    candidates: Set[str] = {
        store.store_id.lower(),
        slugify(store.slug),
        slugify(store.city),
        slugify(store.normalized_city()),
    }
    if store.nickname:
        candidates.add(slugify(store.nickname))
    for candidate in list(candidates):
        candidates.add(candidate.replace("-", ""))
    return any(candidate in filters for candidate in candidates)


# ---------------------------------------------------------------------------
# Networking helpers
# ---------------------------------------------------------------------------


def build_headers() -> Dict[str, str]:
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
        "Cache-Control": "no-cache",
    }


def fetch_with_retries(
    url: str,
    *,
    max_retries: int = DEFAULT_MAX_RETRIES,
    timeout: int = DEFAULT_TIMEOUT,
    delay_range: Tuple[float, float] = DEFAULT_DELAY_RANGE,
) -> str:
    last_error: Optional[Exception] = None
    for attempt in range(1, max_retries + 1):
        try:
            response = requests.get(url, headers=build_headers(), timeout=timeout)
            if response.status_code == 200:
                return response.text
            last_error = RuntimeError(f"Status HTTP {response.status_code}")
        except Exception as exc:  # noqa: BLE001 - logging purpose
            last_error = exc
        sleep_for = random.uniform(*delay_range)
        print(f"⚠️  Nouvelle tentative ({attempt}/{max_retries}) dans {sleep_for:.1f}s pour {url}")
        time.sleep(sleep_for)
    raise RuntimeError(f"Impossible de charger {url}") from last_error


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------


def extract_next_data(html: str) -> Dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")
    script_tag = soup.find("script", {"id": "__NEXT_DATA__"})
    if script_tag is None or not script_tag.string:
        raise ValueError("Impossible de repérer le JSON '__NEXT_DATA__'.")
    return json.loads(script_tag.string)


def iter_clearance_candidates(data: Any) -> Iterator[Dict[str, Any]]:
    queue: List[Any] = [data]
    while queue:
        current = queue.pop()
        if isinstance(current, dict):
            if _looks_like_product(current):
                yield current
            for key, value in current.items():
                if isinstance(value, (dict, list)):
                    if "clearance" in key.lower() or "liquidation" in key.lower():
                        queue.append(value)
                    else:
                        queue.append(value)
        elif isinstance(current, list):
            queue.extend(current)


def _looks_like_product(candidate: Dict[str, Any]) -> bool:
    name = candidate.get("name") or candidate.get("title") or candidate.get("productName")
    if not name:
        return False
    if not _extract_url(candidate):
        return False
    price_candidates = [
        candidate.get("salePrice"),
        candidate.get("clearancePrice"),
        candidate.get("price"),
        candidate.get("regularPrice"),
        candidate.get("pricing"),
        candidate.get("prices"),
        candidate.get("priceInfo"),
    ]
    for item in price_candidates:
        if _extract_price(item) is not None:
            return True
    return False


def _extract_price(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        text = text.replace("\u00a0", " ").replace("$", "").replace("CAD", "").replace(",", ".")
        text = text.replace(" ", "")
        try:
            return float(text)
        except ValueError:
            digits = "".join(ch for ch in text if ch.isdigit())
            if digits:
                try:
                    return float(digits) / (100 if len(digits) > 2 else 1)
                except ValueError:
                    return None
            return None
    if isinstance(value, dict):
        keys = (
            "value",
            "amount",
            "price",
            "sale",
            "regular",
            "salePrice",
            "regularPrice",
            "current",
            "min",
            "max",
            "list",
            "offer",
        )
        for key in keys:
            if key in value:
                extracted = _extract_price(value[key])
                if extracted is not None:
                    return extracted
    if isinstance(value, Iterable) and not isinstance(value, (str, bytes, dict)):
        for item in value:
            extracted = _extract_price(item)
            if extracted is not None:
                return extracted
    return None


def _extract_url(candidate: Dict[str, Any]) -> Optional[str]:
    url_keys = (
        "url",
        "productUrl",
        "canonicalUrl",
        "href",
        "link",
        "ctaUrl",
        "ctaLink",
        "pdpUrl",
    )
    for key in url_keys:
        value = candidate.get(key)
        if isinstance(value, str) and value.strip():
            return urljoin(BASE_DOMAIN, value.strip())
    action = candidate.get("cta")
    if isinstance(action, dict):
        for key in ("href", "url", "link"):
            value = action.get(key)
            if isinstance(value, str) and value.strip():
                return urljoin(BASE_DOMAIN, value.strip())
    return None


def _extract_image(candidate: Dict[str, Any]) -> Optional[str]:
    image_keys = ("image", "imageUrl", "primaryImage", "media", "images")
    for key in image_keys:
        value = candidate.get(key)
        url = _extract_image_from_value(value)
        if url:
            return urljoin(BASE_DOMAIN, url) if url.startswith("/") else url
    return None


def _extract_image_from_value(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, dict):
        for key in ("url", "href", "src", "main", "large", "thumbnail"):
            sub_value = value.get(key)
            if isinstance(sub_value, str) and sub_value.strip():
                return sub_value.strip()
        sizes = value.get("sizes")
        if isinstance(sizes, dict):
            for sub in sizes.values():
                url = _extract_image_from_value(sub)
                if url:
                    return url
    if isinstance(value, list):
        for item in value:
            url = _extract_image_from_value(item)
            if url:
                return url
    return None


def build_deal(candidate: Dict[str, Any]) -> Optional[Deal]:
    title = candidate.get("name") or candidate.get("title") or candidate.get("productName")
    if not title:
        return None
    url = _extract_url(candidate)
    if not url:
        return None
    regular_price = _extract_price(
        candidate.get("regularPrice")
        or candidate.get("price")
        or candidate.get("pricing")
        or candidate.get("prices")
    )
    sale_price = _extract_price(
        candidate.get("salePrice")
        or candidate.get("clearancePrice")
        or candidate.get("promoPrice")
        or candidate.get("pricing")
        or candidate.get("prices")
    )
    if sale_price is None and regular_price is None:
        return None
    if regular_price is None:
        regular_price = sale_price
    if sale_price is None:
        sale_price = regular_price
    image = _extract_image(candidate)
    sku = candidate.get("sku") or candidate.get("skuNumber") or candidate.get("partNumber")
    if isinstance(sku, dict):
        sku = sku.get("value") or sku.get("code")
    if isinstance(sku, (int, float)):
        sku = str(sku)
    if isinstance(sku, str):
        sku = sku.strip() or None
    return Deal(
        title=str(title).strip(),
        url=url,
        price=float(regular_price),
        sale_price=float(sale_price),
        image=image,
        sku=sku,
    )


def deduplicate(deals: Iterable[Deal]) -> List[Deal]:
    seen: Set[str] = set()
    unique: List[Deal] = []
    for deal in deals:
        key = deal.sku or deal.url
        if key in seen:
            continue
        seen.add(key)
        unique.append(deal)
    return unique


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def ensure_output_dir(path: Optional[Path]) -> Path:
    target = path or DEFAULT_OUTPUT_DIR
    target.mkdir(parents=True, exist_ok=True)
    return target


def write_json(path: Path, payload: List[Dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def scrape_store(
    store: Store,
    *,
    language: str = DEFAULT_LANGUAGE,
    max_retries: int = DEFAULT_MAX_RETRIES,
    timeout: int = DEFAULT_TIMEOUT,
    delay_range: Tuple[float, float] = DEFAULT_DELAY_RANGE,
) -> List[Deal]:
    page_url = store.url(language)
    html = fetch_with_retries(
        page_url,
        max_retries=max_retries,
        timeout=timeout,
        delay_range=delay_range,
    )
    next_data = extract_next_data(html)
    candidates = [build_deal(item) for item in iter_clearance_candidates(next_data)]
    deals = [deal for deal in candidates if deal]
    deals = deduplicate(deals)
    deals.sort(key=lambda deal: (deal.sale_price, deal.title))
    print(f"✔ {store.normalized_city()}: {len(deals)} produits")
    return deals


def run(
    *,
    store_filters: Optional[Sequence[str]] = None,
    language: str = DEFAULT_LANGUAGE,
    output_dir: Optional[Path] = None,
    aggregated_path: Optional[Path] = None,
    max_retries: int = DEFAULT_MAX_RETRIES,
    timeout: int = DEFAULT_TIMEOUT,
    delay_range: Tuple[float, float] = DEFAULT_DELAY_RANGE,
) -> None:
    stores = load_stores()
    if not stores:
        raise ValueError("La liste des magasins Canadian Tire est vide.")

    normalized_filters: Set[str] = set()
    if store_filters:
        for item in store_filters:
            normalized_filters.update(normalize_token(item))

    if normalized_filters:
        stores = [store for store in stores if store_matches_filters(store, normalized_filters)]
        if not stores:
            raise ValueError("Aucun magasin ne correspond aux filtres fournis.")

    per_store_dir = ensure_output_dir(output_dir)
    aggregated_target = aggregated_path or Path(DEFAULT_AGGREGATED_FILENAME)

    aggregated_payload: List[Dict[str, Any]] = []
    for store in stores:
        try:
            deals = scrape_store(
                store,
                language=language,
                max_retries=max_retries,
                timeout=timeout,
                delay_range=delay_range,
            )
        except Exception as exc:  # noqa: BLE001 - logging context
            print(f"❌ {store.normalized_city()}: {exc}")
            continue

        payload = [deal.to_payload(store) for deal in deals]
        target_path = per_store_dir / f"{store.output_stem}.json"
        write_json(target_path, payload)
        aggregated_payload.extend(payload)

    if aggregated_payload:
        aggregated_payload.sort(key=lambda item: (item["city"], item["title"]))
        write_json(aggregated_target, aggregated_payload)
        print(f"📦 Agrégation sauvegardée dans {aggregated_target}")
    else:
        print("⚠️  Aucun produit n'a été collecté.")


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extraction des articles en liquidation Canadian Tire",
    )
    parser.add_argument(
        "--store",
        action="append",
        dest="stores",
        default=[],
        help="Filtre les magasins (ID, ville, slug ou surnom).",
    )
    parser.add_argument(
        "--language",
        choices=("fr", "en"),
        default=DEFAULT_LANGUAGE,
        help="Langue de la page magasin à interroger (fr ou en).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Dossier cible pour les JSON individuels (défaut: data/canadian-tire).",
    )
    parser.add_argument(
        "--aggregated-path",
        type=Path,
        default=None,
        help=(
            "Chemin du fichier d'agrégation global (défaut: "
            f"{DEFAULT_AGGREGATED_FILENAME})."
        ),
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=DEFAULT_MAX_RETRIES,
        help="Nombre maximal de tentatives par page (défaut: 6).",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT,
        help="Délai (secondes) pour chaque requête HTTP (défaut: 20).",
    )
    parser.add_argument(
        "--delay",
        nargs=2,
        type=float,
        metavar=("MIN", "MAX"),
        default=None,
        help="Intervalle (s) aléatoire entre les tentatives (défaut: 1.0 3.0).",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> None:
    args = parse_args(argv)
    delay_range = tuple(args.delay) if args.delay else DEFAULT_DELAY_RANGE
    run(
        store_filters=args.stores,
        language=args.language,
        output_dir=args.output_dir,
        aggregated_path=args.aggregated_path,
        max_retries=args.max_retries,
        timeout=args.timeout,
        delay_range=(float(delay_range[0]), float(delay_range[1])),
    )


if __name__ == "__main__":
    main()
