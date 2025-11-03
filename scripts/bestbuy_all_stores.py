"""Scrape liquidation listings for each configured Best Buy Canada store."""

from __future__ import annotations

import json
import os
import random
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import requests
from bs4 import BeautifulSoup

USER_AGENTS: Sequence[str] = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.6261.129 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1",
)

DEFAULT_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "fr-CA,fr;q=0.9,en-CA;q=0.8,en;q=0.7",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}

REQUEST_TIMEOUT = 30
MAX_RETRIES = 4
BACKOFF_FACTOR = 1.8
THROTTLE_SECONDS = (1.25, 3.75)
BASE_URL = "https://www.bestbuy.ca"

PRICE_CLEAN_RE = re.compile(r"[^0-9.,-]+")


@dataclass
class StoreConfig:
    """Runtime configuration for a store to scrape."""

    slug: str
    store_id: Optional[str]
    store_url_path: str
    locale: str
    name: Optional[str] = None
    output_name: Optional[str] = None

    @classmethod
    def from_json(cls, path: Path) -> "StoreConfig":
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)

        slug = payload.get("slug") or path.stem
        store_url_path = payload.get("store_url_path")
        if not store_url_path:
            store_id = payload.get("store_id")
            if not store_id:
                raise ValueError(f"Missing 'store_url_path' and 'store_id' for store file {path}")
            segments: List[str] = []
            if payload.get("store_path_segment"):
                segments.append(str(payload["store_path_segment"]))
            elif payload.get("slug"):
                segments.append(str(payload["slug"]))
            else:
                segments.append(slug)
            segments.append(str(store_id))
            store_url_path = "/".join(part.strip("/") for part in segments)

        locale = (payload.get("locale") or "fr-ca").lower()

        return cls(
            slug=slug,
            store_id=str(payload.get("store_id")) if payload.get("store_id") else None,
            store_url_path=str(store_url_path).strip("/"),
            locale=locale,
            name=payload.get("name"),
            output_name=payload.get("output_name"),
        )

    @property
    def output_filename(self) -> str:
        return f"{self.output_name or self.slug}.json"

    @property
    def display_name(self) -> str:
        return self.name or self.slug.replace("-", " ").title()

    def build_url(self) -> str:
        return f"{BASE_URL}/{self.locale}/store/{self.store_url_path}/liquidation"


def load_store_configs(stores_dir: Path) -> List[StoreConfig]:
    if not stores_dir.exists():
        raise FileNotFoundError(f"Stores directory not found: {stores_dir}")

    configs: List[StoreConfig] = []
    for json_path in sorted(stores_dir.glob("*.json")):
        try:
            configs.append(StoreConfig.from_json(json_path))
        except Exception as exc:  # pragma: no cover - defensive logging only
            print(f"⚠️  Impossible de charger {json_path}: {exc}")
    return configs


def load_proxy_pool() -> List[str]:
    raw = os.getenv("BESTBUY_PROXY_POOL") or os.getenv("BESTBUY_PROXIES")
    if not raw:
        return []
    return [entry.strip() for entry in raw.split(",") if entry.strip()]


def choose_headers() -> Dict[str, str]:
    headers = dict(DEFAULT_HEADERS)
    headers["User-Agent"] = random.choice(USER_AGENTS)
    return headers


def fetch_html(url: str, proxies: Sequence[str]) -> str:
    proxy_iter = list(proxies)
    for attempt in range(1, MAX_RETRIES + 1):
        headers = choose_headers()
        proxy = random.choice(proxy_iter) if proxy_iter else None
        request_kwargs: Dict[str, Any] = {
            "headers": headers,
            "timeout": REQUEST_TIMEOUT,
        }
        if proxy:
            request_kwargs["proxies"] = {"http": proxy, "https": proxy}

        try:
            response = requests.get(url, **request_kwargs)
            if response.status_code == 403:
                raise requests.HTTPError(f"HTTP 403 for {url}")
            response.raise_for_status()
            return response.text
        except requests.RequestException as error:
            wait_time = BACKOFF_FACTOR ** (attempt - 1)
            print(f"❌ Tentative {attempt} échouée sur {url}: {error} | pause {wait_time:.1f}s")
            time.sleep(wait_time)
    raise RuntimeError(f"Impossible de récupérer {url} après {MAX_RETRIES} tentatives")


def parse_price(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, dict):
        for key in ("value", "amount", "price", "current", "regular", "sale", "raw"):
            nested = value.get(key)
            result = parse_price(nested)
            if result is not None:
                return result
        return None
    if isinstance(value, str):
        cleaned = PRICE_CLEAN_RE.sub("", value)
        if not cleaned:
            return None
        if cleaned.count(",") == 1 and cleaned.count(".") == 0:
            cleaned = cleaned.replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None


def find_product_dicts(root: Any) -> List[Dict[str, Any]]:
    products: Dict[str, Dict[str, Any]] = {}

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            keys = set(node)
            if "sku" in keys and ("name" in keys or "title" in keys):
                price_keys = {"salePrice", "regularPrice", "price", "currentPrice", "prices"}
                if price_keys & keys:
                    sku = str(node.get("sku"))
                    if sku and sku not in products:
                        products[sku] = node
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(root)
    return list(products.values())


def extract_image(data: Dict[str, Any]) -> Optional[str]:
    for key in ("thumbnailImage", "image", "primaryImage", "imageUrl", "images"):
        if key not in data:
            continue
        value = data[key]
        if isinstance(value, str):
            return value
        if isinstance(value, dict):
            for candidate in ("href", "url", "thumbnail", "standard", "primary"):
                if value.get(candidate):
                    return str(value[candidate])
        if isinstance(value, list) and value:
            first = value[0]
            if isinstance(first, str):
                return first
            if isinstance(first, dict):
                for candidate in ("href", "url", "thumbnail", "standard", "primary"):
                    if first.get(candidate):
                        return str(first[candidate])
    return None


def extract_product_link(data: Dict[str, Any]) -> Optional[str]:
    for key in ("productUrl", "url", "link", "href"):
        link = data.get(key)
        if isinstance(link, str) and link:
            if link.startswith("http"):
                return link
            return f"{BASE_URL}{link}" if link.startswith("/") else f"{BASE_URL}/{link}"
    return None


def extract_availability(data: Dict[str, Any]) -> Optional[str]:
    for key in ("availability", "shippingMessage", "availabilityMessage", "status"):
        value = data.get(key)
        if isinstance(value, str) and value:
            return value
        if isinstance(value, dict):
            for candidate in ("status", "label", "value", "message"):
                if isinstance(value.get(candidate), str) and value[candidate]:
                    return str(value[candidate])
    return None


def normalize_product(product: Dict[str, Any], store_name: str) -> Dict[str, Any]:
    normalized = {
        "product_name": product.get("name") or product.get("title"),
        "sku": str(product.get("sku")) if product.get("sku") else None,
        "regular_price": parse_price(product.get("regularPrice") or product.get("price")),
        "sale_price": parse_price(
            product.get("salePrice")
            or product.get("currentPrice")
            or product.get("prices", {}).get("current") if isinstance(product.get("prices"), dict) else None
        ),
        "image": extract_image(product),
        "product_link": extract_product_link(product),
        "availability": extract_availability(product),
        "store": store_name,
    }

    if not normalized["sale_price"] and isinstance(product.get("prices"), dict):
        normalized["sale_price"] = parse_price(product["prices"].get("sale"))
        if not normalized["regular_price"]:
            normalized["regular_price"] = parse_price(product["prices"].get("regular"))

    if not normalized["regular_price"] and normalized["sale_price"]:
        maybe_regular = parse_price(product.get("wasPrice") or product.get("regular"))
        if maybe_regular:
            normalized["regular_price"] = maybe_regular

    return {key: value for key, value in normalized.items() if value is not None}


def scrape_store(
    config: StoreConfig, output_dir: Path, proxies: Sequence[str]
) -> Tuple[Path, List[Dict[str, Any]]]:
    url = config.build_url()
    print(f"🔍 {config.display_name} → {url}")

    html = fetch_html(url, proxies)
    soup = BeautifulSoup(html, "html.parser")
    next_data = soup.find("script", id="__NEXT_DATA__")
    if not next_data or not next_data.string:
        raise RuntimeError(f"Aucune donnée JSON trouvée pour {config.display_name}")

    payload = json.loads(next_data.string)
    products_raw = find_product_dicts(payload)
    products: List[Dict[str, Any]] = []
    for raw_product in products_raw:
        normalized = normalize_product(raw_product, config.display_name)
        if normalized.get("product_name") and normalized.get("sku"):
            products.append(normalized)

    products.sort(key=lambda item: item.get("product_name", ""))

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / config.output_filename
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(products, handle, indent=2, ensure_ascii=False)
    print(f"💾 {len(products)} produits sauvegardés dans {output_path}")

    # Respect rate limiting rules between calls
    sleep_seconds = random.uniform(*THROTTLE_SECONDS)
    time.sleep(sleep_seconds)

    return output_path, products


def main() -> None:
    base_dir = Path(__file__).resolve().parent.parent
    stores_dir = base_dir / "data" / "best-buy" / "stores"
    output_dir = base_dir / "data" / "best-buy" / "liquidations"

    configs = load_store_configs(stores_dir)
    if not configs:
        raise SystemExit("Aucun magasin configuré pour le scraping.")

    proxies = load_proxy_pool()
    print(f"🌐 Proxies détectés: {len(proxies)}")

    written_files: List[Path] = []
    combined_products: List[Dict[str, Any]] = []
    for config in configs:
        try:
            output_path, products = scrape_store(config, output_dir, proxies)
            written_files.append(output_path)
            combined_products.extend(products)
        except Exception as error:
            print(f"❌ Échec du magasin {config.display_name}: {error}")

    if not written_files:
        raise SystemExit("Aucun magasin n'a été mis à jour.")

    if combined_products:
        combined_products.sort(
            key=lambda product: (
                product.get("store", ""),
                product.get("product_name", ""),
                product.get("sku", ""),
            )
        )

        aggregate_path = base_dir / "data" / "best-buy" / "liquidations.json"
        with aggregate_path.open("w", encoding="utf-8") as handle:
            json.dump(combined_products, handle, indent=2, ensure_ascii=False)
        print(
            f"📦 {len(combined_products)} produits combinés sauvegardés dans {aggregate_path}"
        )


if __name__ == "__main__":
    main()
