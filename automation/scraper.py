#!/usr/bin/env python3
"""Canadian Tire liquidation scraper and site ingester.

This script demonstrates how one could aggregate clearance/"liquidation" items
from multiple Canadian Tire branches in Québec, persist them into a local
SQLite database, and then forward the items to an external HTTP endpoint (your
website).  The real Canadian Tire APIs are not publicly documented and may
change at any time, so this script aims to stay resilient by handling partial
failures and by allowing extensive configuration.

The scraper expects a JSON configuration file (see ``config.example.json``)
that defines the stores to visit, optional department/category filters, and the
HTTP endpoint used to inject the data into your website.

Run ``python scraper.py --help`` to see all available options.
"""
from __future__ import annotations

import argparse
import dataclasses
import functools
import json
import logging
import os
import sqlite3
import time
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Iterable, List, Optional

import pytz
import requests
from bs4 import BeautifulSoup

LOGGER = logging.getLogger(__name__)
DEFAULT_DB_PATH = Path(__file__).resolve().parent / "liquidations.sqlite"
DEFAULT_CONFIG = Path(__file__).resolve().parent / "config.json"
DEFAULT_TIMEZONE = "America/Toronto"  # Covers Québec (EST/EDT).
STORE_DIRECTORY_PATH = (
    Path(__file__).resolve().parent / "canadian_tire_stores_qc.json"
)
CANADIAN_TIRE_CLEARANCE_ENDPOINT = (
    "https://www.canadiantire.ca/services/specialoffers/v1/deals"
)


@dataclasses.dataclass
class StoreConfig:
    """Represents a Canadian Tire store to visit."""

    store_id: Optional[str] = None
    slug: Optional[str] = None
    nickname: Optional[str] = None
    city: Optional[str] = None
    province: Optional[str] = None
    postal_code: Optional[str] = None


@dataclasses.dataclass
class DepartmentConfig:
    """Department filter used to narrow down the search results."""

    department_id: Optional[str] = None
    query: Optional[str] = None


@dataclasses.dataclass
class SiteEndpointConfig:
    """Settings used to push liquidation items to the website."""

    url: str
    api_key: Optional[str] = None
    timeout: int = 15


@dataclasses.dataclass
class ScraperConfig:
    stores: List[StoreConfig]
    departments: List[DepartmentConfig]
    site_endpoint: Optional[SiteEndpointConfig]
    timezone: str = DEFAULT_TIMEZONE
    request_delay: float = 1.0

    @staticmethod
    def from_dict(data: dict) -> "ScraperConfig":
        stores = [
            enrich_store_metadata(StoreConfig(**item))
            for item in data.get("stores", [])
        ]
        departments = [
            DepartmentConfig(**item) for item in data.get("departments", [])
        ]
        site_endpoint = None
        if endpoint_data := data.get("site_endpoint"):
            site_endpoint = SiteEndpointConfig(**endpoint_data)
        timezone = data.get("timezone", DEFAULT_TIMEZONE)
        request_delay = float(data.get("request_delay", 1.0))
        return ScraperConfig(
            stores=stores,
            departments=departments,
            site_endpoint=site_endpoint,
            timezone=timezone,
            request_delay=request_delay,
        )


def load_config(path: Path) -> ScraperConfig:
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    return ScraperConfig.from_dict(data)


def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(ch for ch in text if ord(ch) < 0x0300)
    text = text.lower()
    result = []
    for ch in text:
        if ch.isalnum():
            result.append(ch)
        elif ch in {" ", "-", "/", "_", "(", ")"}:
            if result and result[-1] != "-":
                result.append("-")
        else:
            if result and result[-1] != "-":
                result.append("-")
    slug = "".join(result).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug


@functools.lru_cache()
def load_store_directory() -> List[dict]:
    if not STORE_DIRECTORY_PATH.exists():
        LOGGER.debug("Répertoire des magasins introuvable: %s", STORE_DIRECTORY_PATH)
        return []
    try:
        with STORE_DIRECTORY_PATH.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        LOGGER.warning("Impossible de lire %s: %s", STORE_DIRECTORY_PATH, exc)
        return []
    if not isinstance(data, list):
        LOGGER.warning("Format inattendu pour le répertoire des magasins")
        return []
    return data


def find_store_entry(store: StoreConfig) -> Optional[dict]:
    directory = load_store_directory()
    if not directory:
        return None

    # Priority: explicit store_id, slug, nickname/city slug
    if store.store_id:
        for entry in directory:
            if str(entry.get("store_id")) == str(store.store_id):
                return entry

    if store.slug:
        for entry in directory:
            if entry.get("slug") == store.slug:
                return entry

    slug_candidates = []
    if store.nickname:
        slug_candidates.append(slugify(store.nickname))
    if store.city:
        slug_candidates.append(slugify(store.city))
    for candidate in slug_candidates:
        for entry in directory:
            if entry.get("slug") == candidate:
                return entry
    return None


def enrich_store_metadata(store: StoreConfig) -> StoreConfig:
    entry = find_store_entry(store)
    if not entry:
        return store

    if not store.store_id and entry.get("store_id"):
        store.store_id = str(entry["store_id"])
    if not store.slug and entry.get("slug"):
        store.slug = entry["slug"]
    if not store.nickname and entry.get("nickname"):
        store.nickname = entry["nickname"]
    if not store.city and entry.get("city"):
        store.city = entry["city"]
    if not store.province and entry.get("province"):
        store.province = entry["province"]
    if not store.postal_code and entry.get("postal_code"):
        store.postal_code = entry["postal_code"]
    return store


def ensure_schema(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS liquidation_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sku TEXT NOT NULL,
            store_id TEXT NOT NULL,
            name TEXT,
            price_regular REAL,
            price_clearance REAL,
            discount_percent REAL,
            product_url TEXT,
            image_url TEXT,
            scraped_at TEXT NOT NULL,
            UNIQUE (sku, store_id)
        )
        """
    )
    conn.commit()
    return conn


def fetch_liquidations(
    store: StoreConfig, departments: Iterable[DepartmentConfig]
) -> List[dict]:
    """Fetch clearance items for a store.

    This function performs an HTTP GET request against the undocumented
    ``/services/specialoffers/v1/deals`` endpoint which powers the Canadian Tire
    "circulaires" / deals sections.  If the endpoint changes, the fallback HTML
    scraping routine (``_parse_from_html``) still returns best-effort results.
    """

    if not store.store_id:
        LOGGER.warning(
            "Succursale ignorée: aucun identifiant store_id fourni (%s)",
            store.nickname or store.slug or store.city or "inconnu",
        )
        return []

    params = {
        "storeId": store.store_id,
        "lang": "fr",
        "page": 1,
        "pageSize": 200,
    }

    all_items: List[dict] = []
    for department in list(departments) or [DepartmentConfig()]:
        if department.department_id:
            params["department"] = department.department_id
        if department.query:
            params["keyword"] = department.query

        LOGGER.info(
            "Fetching liquidation deals for store %s (department=%s, query=%s)",
            store.store_id,
            department.department_id,
            department.query,
        )

        try:
            response = requests.get(
                CANADIAN_TIRE_CLEARANCE_ENDPOINT,
                params=params,
                timeout=20,
                headers={
                    "User-Agent": "Mozilla/5.0 (compatible; econodeal-scraper/1.0)",
                    "Accept": "application/json, text/html;q=0.9",
                },
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            LOGGER.error("Erreur réseau pour la succursale %s: %s", store.store_id, exc)
            continue

        content_type = response.headers.get("Content-Type", "")
        if "json" in content_type:
            items = _parse_from_json(response.json())
        else:
            items = _parse_from_html(response.text)

        LOGGER.info("%d items trouvés pour le magasin %s", len(items), store.store_id)
        all_items.extend(items)
        time.sleep(0.1)  # Small delay between department calls

    return all_items


def _parse_from_json(payload: dict) -> List[dict]:
    items: List[dict] = []
    deals = payload.get("deals") or payload.get("items") or []
    for entry in deals:
        sku = str(entry.get("sku") or entry.get("id") or "")
        if not sku:
            continue
        items.append(
            {
                "sku": sku,
                "name": entry.get("title") or entry.get("name"),
                "price_regular": _to_float(entry.get("regularPrice")),
                "price_clearance": _to_float(entry.get("salePrice")),
                "discount_percent": _to_float(entry.get("discountPercent")),
                "product_url": entry.get("productUrl") or entry.get("url"),
                "image_url": entry.get("imageUrl") or entry.get("image"),
            }
        )
    return items


def _parse_from_html(html: str) -> List[dict]:
    """Fallback parser when JSON is not available."""

    soup = BeautifulSoup(html, "html.parser")
    items: List[dict] = []
    for card in soup.select("[data-product-sku]"):
        sku = card.get("data-product-sku")
        if not sku:
            continue
        name = card.get("data-product-name") or card.select_one(".product__name")
        price_regular = card.get("data-regular-price") or card.get(
            "data-product-was-price"
        )
        price_clearance = card.get("data-sale-price") or card.get(
            "data-product-price"
        )
        image = card.select_one("img")
        link = card.select_one("a[href]")
        items.append(
            {
                "sku": sku,
                "name": getattr(name, "text", name) if name else None,
                "price_regular": _to_float(price_regular),
                "price_clearance": _to_float(price_clearance),
                "discount_percent": None,
                "product_url": link["href"] if link else None,
                "image_url": image["src"] if image else None,
            }
        )
    return items


def _to_float(value) -> Optional[float]:
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace("$", "").replace(",", "."))
    except ValueError:
        return None


def save_items(conn: sqlite3.Connection, store: StoreConfig, items: Iterable[dict]) -> int:
    cursor = conn.cursor()
    now = datetime.utcnow().isoformat()
    saved = 0
    for item in items:
        cursor.execute(
            """
            INSERT INTO liquidation_items (
                sku, store_id, name, price_regular, price_clearance,
                discount_percent, product_url, image_url, scraped_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(sku, store_id) DO UPDATE SET
                name=excluded.name,
                price_regular=excluded.price_regular,
                price_clearance=excluded.price_clearance,
                discount_percent=excluded.discount_percent,
                product_url=excluded.product_url,
                image_url=excluded.image_url,
                scraped_at=excluded.scraped_at
            """,
            (
                item.get("sku"),
                store.store_id,
                item.get("name"),
                item.get("price_regular"),
                item.get("price_clearance"),
                item.get("discount_percent"),
                item.get("product_url"),
                item.get("image_url"),
                now,
            ),
        )
        saved += 1
    conn.commit()
    LOGGER.info("%d items sauvegardés dans la base", saved)
    return saved


def push_to_site(
    endpoint: SiteEndpointConfig, store: StoreConfig, items: Iterable[dict], dry_run: bool
) -> None:
    payload = {
        "store_id": store.store_id,
        "store_nickname": store.nickname,
        "items": list(items),
    }
    headers = {"Content-Type": "application/json"}
    if endpoint.api_key:
        headers["Authorization"] = f"Bearer {endpoint.api_key}"

    if dry_run:
        LOGGER.info("[DRY-RUN] Post vers %s avec %d items", endpoint.url, len(payload["items"]))
        return

    try:
        response = requests.post(
            endpoint.url,
            json=payload,
            timeout=endpoint.timeout,
            headers=headers,
        )
        response.raise_for_status()
        LOGGER.info(
            "Injection réussie pour le magasin %s (%d items)",
            store.store_id,
            len(payload["items"]),
        )
    except requests.RequestException as exc:
        LOGGER.error("Impossible d'injecter les données pour %s: %s", store.store_id, exc)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help="Chemin vers le fichier de configuration JSON",
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=DEFAULT_DB_PATH,
        help="Chemin vers la base SQLite",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="N'envoie pas les données vers le site, affiche seulement les résumés",
    )
    parser.add_argument(
        "--log-level",
        default=os.environ.get("LOG_LEVEL", "INFO"),
        help="Niveau de log (DEBUG, INFO, WARNING, ERROR)",
    )
    parser.add_argument(
        "--list-stores",
        action="store_true",
        help=(
            "Affiche les succursales Canadian Tire connues depuis "
            "canadian_tire_stores_qc.json"
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logging.basicConfig(level=getattr(logging, str(args.log_level).upper(), logging.INFO))

    if args.list_stores:
        directory = load_store_directory()
        if not directory:
            print("Aucun répertoire des magasins n'est disponible.")
            return
        print("Magasins Canadian Tire (Québec):")
        for entry in sorted(directory, key=lambda item: item.get("label", "")):
            label = entry.get("label") or "—"
            store_id = entry.get("store_id") or "(store_id inconnu)"
            slug_value = entry.get("slug") or slugify(label)
            print(f"- {label} — store_id={store_id} — slug={slug_value}")
        return

    if not args.config.exists():
        raise SystemExit(
            f"Fichier de configuration introuvable: {args.config}. Copiez "
            "config.example.json et adaptez-le."
        )

    config = load_config(args.config)
    timezone = pytz.timezone(config.timezone or DEFAULT_TIMEZONE)
    now_local = datetime.now(timezone)
    LOGGER.info("Début de l'exécution à %s", now_local.isoformat())

    with ensure_schema(args.database) as conn:
        for store in config.stores:
            items = fetch_liquidations(store, config.departments)
            if not items:
                LOGGER.warning("Aucun produit trouvé pour la succursale %s", store.store_id)
                continue
            save_items(conn, store, items)
            if config.site_endpoint:
                push_to_site(config.site_endpoint, store, items, dry_run=args.dry_run)
            time.sleep(config.request_delay)

    LOGGER.info("Scraper terminé")


if __name__ == "__main__":
    main()
