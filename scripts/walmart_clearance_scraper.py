"""Scrape the Walmart Canada clearance hub and export products grouped by section.

The scraper relies on the unofficial Walmart endpoints exposed to the browser. It
first attempts to resolve the different clearance sections (toys, electronics,
etc.) from the page definition API and then downloads all products for each
section. If direct network access to Walmart is blocked, a local offline sample
can be supplied so that the export format remains deterministic for tests.
"""

from __future__ import annotations

import argparse
import json
import logging
import random
import sys
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Optional, Sequence

import requests

LOGGER = logging.getLogger("walmart.clearance")

# The page that lists all Saint-Jérôme clearance deals on walmart.ca.
DEFAULT_CLEARANCE_PATH = "/fr/cp/clearance/6000204800999"
DEFAULT_OUTPUT = "walmart st jerome.json"
DEFAULT_OFFLINE_SAMPLE = Path("data/samples/walmart_clearance_sample.json")

DEFAULT_HEADERS: Dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/119.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "fr-CA,fr;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://www.walmart.ca/",
    "Connection": "keep-alive",
}


@dataclass
class Product:
    """Normalized representation for a Walmart clearance product."""

    title: str
    url: str
    section: str
    image: Optional[str] = None
    price: Optional[float] = None
    sale_price: Optional[float] = None
    store: str = "Walmart"
    city: str = "Saint-Jérôme"

    @classmethod
    def from_dict(cls, payload: Dict[str, object], section: str) -> "Product":
        """Build a product from the API payload using best-effort keys."""

        image = _extract_first(
            payload,
            (
                "image",  # legacy structure
                "imageUrl",
                "images.primaryUrl",
                "images.hero",
                "productImage",
            ),
        )
        title = _extract_first(payload, ("title", "name"))
        if not title:
            raise ValueError("Impossible d'identifier le titre du produit.")
        url = _extract_first(payload, ("url", "canonicalUrl", "productUrl"))
        if not url:
            raise ValueError("Impossible d'identifier l'URL du produit.")
        price = _extract_price(payload, "price")
        sale_price = _extract_price(payload, "salePrice", "priceInfo.currentPrice")
        if price is None and sale_price is not None:
            price = sale_price
        return cls(
            title=title,
            url=url,
            section=section,
            image=image,
            price=price,
            sale_price=sale_price,
        )


def _extract_first(payload: Dict[str, object], keys: Sequence[str]) -> Optional[str]:
    for key in keys:
        if "." in key:
            value = payload
            try:
                for part in key.split("."):
                    if not isinstance(value, dict):
                        raise KeyError(part)
                    value = value[part]  # type: ignore[index]
            except KeyError:
                continue
            if isinstance(value, str):
                return value
        else:
            value = payload.get(key)
            if isinstance(value, str):
                return value
    return None


def _extract_price(payload: Dict[str, object], *keys: str) -> Optional[float]:
    for key in keys:
        if not key:
            continue
        target: object = payload
        try:
            for part in key.split("."):
                if isinstance(target, dict) and part in target:
                    target = target[part]
                else:
                    raise KeyError(part)
        except KeyError:
            continue
        if isinstance(target, (int, float)):
            return float(target)
        if isinstance(target, str):
            try:
                return float(target.replace("$", "").replace(",", "."))
            except ValueError:
                continue
        if isinstance(target, dict):
            amount = target.get("amount") or target.get("price")
            if isinstance(amount, (int, float)):
                return float(amount)
    return None


class WalmartClearanceScraper:
    """High level helper that orchestrates the clearance scrape."""

    base_url = "https://www.walmart.ca"
    page_definition_endpoint = "/api/nextgen/page/def"
    classified_endpoint = "/api/nextgen/ipt/classified"

    def __init__(
        self,
        *,
        session: Optional[requests.Session] = None,
        timeout: float = 25.0,
        locale: str = "fr",
        max_pages: int = 5,
        throttle_range: Sequence[float] = (0.7, 1.3),
        offline_source: Optional[Path] = None,
    ) -> None:
        self.timeout = timeout
        self.locale = locale
        self.max_pages = max_pages
        self.throttle_range = tuple(throttle_range)
        self.offline_source = offline_source
        self.session = session or requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)

    def scrape(self, path: str) -> List[Product]:
        """Fetch all clearance sections for the given path."""

        try:
            sections = list(self._discover_sections(path))
        except Exception as exc:  # pragma: no cover - network is flaky in CI
            LOGGER.warning("Échec de la découverte des sections (%s).", exc)
            return self._load_offline()

        products: List[Product] = []
        for section in sections:
            name = section["name"]
            categories = section.get("categories") or []
            LOGGER.info("Section %s - %s catégories", name, len(categories))
            try:
                products.extend(self._fetch_section_products(name, categories))
            except Exception as exc:  # pragma: no cover - network is flaky in CI
                LOGGER.warning("Section %s ignorée suite à l'erreur: %s", name, exc)
        if not products:
            LOGGER.warning("Aucun produit collecté en mode ligne. Tentative du mode hors-ligne.")
            return self._load_offline()
        return products

    # Network helpers -------------------------------------------------
    def _request_json(self, endpoint: str, *, params: Optional[Dict[str, object]] = None) -> Dict[str, object]:
        url = f"{self.base_url}{endpoint}"
        response = self.session.get(url, params=params, timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    def _discover_sections(self, path: str) -> Iterator[Dict[str, object]]:
        payload = self._request_json(
            self.page_definition_endpoint,
            params={"path": path, "lang": self.locale},
        )
        modules = payload.get("modules")
        if modules is None:
            modules = payload.get("data", {}).get("modules") if isinstance(payload.get("data"), dict) else None
        if not isinstance(modules, list):
            raise RuntimeError("Structure inattendue pour la page Walmart")
        for module in modules:
            if not isinstance(module, dict):
                continue
            meta = module.get("moduleData") or module.get("data") or {}
            if not isinstance(meta, dict):
                continue
            name = meta.get("title") or meta.get("header", {}).get("title")
            if not name:
                continue
            categories = []
            for field in ("collections", "items", "tabs", "cards"):
                buckets = meta.get(field)
                if not isinstance(buckets, list):
                    continue
                for bucket in buckets:
                    if isinstance(bucket, dict):
                        cat_id = bucket.get("categoryId") or bucket.get("id")
                        if isinstance(cat_id, (int, str)):
                            categories.append(str(cat_id))
            if not categories:
                continue
            yield {"name": str(name), "categories": categories}

    def _fetch_section_products(self, section: str, categories: Sequence[str]) -> List[Product]:
        collected: List[Product] = []
        for category_id in categories:
            for page in range(1, self.max_pages + 1):
                params = {
                    "categoryId": category_id,
                    "page": page,
                    "size": 40,
                    "lang": self.locale,
                    "sort": "best-sellers",
                }
                payload = self._request_json(self.classified_endpoint, params=params)
                items = list(self._extract_products(payload, section))
                if not items:
                    break
                collected.extend(items)
                self._sleep()
        return collected

    def _extract_products(self, payload: Dict[str, object], section: str) -> Iterator[Product]:
        for candidate in _walk(payload):
            if not isinstance(candidate, dict):
                continue
            if "title" in candidate or "name" in candidate:
                try:
                    yield Product.from_dict(candidate, section)
                except ValueError:
                    continue

    def _sleep(self) -> None:
        if not self.throttle_range:
            return
        delay = random.uniform(*self.throttle_range)
        time.sleep(delay)

    # Offline fallback ------------------------------------------------
    def _load_offline(self) -> List[Product]:
        if not self.offline_source:
            raise RuntimeError("Aucune source hors ligne définie pour les tests.")
        offline_path = Path(self.offline_source)
        if not offline_path.is_file():
            raise FileNotFoundError(f"Source hors ligne introuvable: {offline_path}")
        data = json.loads(offline_path.read_text(encoding="utf-8"))
        products: List[Product] = []
        if isinstance(data, list):
            for item in data:
                if not isinstance(item, dict):
                    continue
                section = item.get("section", "clearance")
                try:
                    products.append(
                        Product(
                            title=str(item["title"]),
                            url=str(item["url"]),
                            section=str(section),
                            image=item.get("image"),
                            price=_coerce_float(item.get("price")),
                            sale_price=_coerce_float(item.get("salePrice")),
                            store=str(item.get("store", "Walmart")),
                            city=str(item.get("city", "Saint-Jérôme")),
                        )
                    )
                except KeyError:
                    continue
        return products


def _walk(payload: object) -> Iterator[object]:
    if isinstance(payload, dict):
        for value in payload.values():
            yield value
            yield from _walk(value)
    elif isinstance(payload, list):
        for item in payload:
            yield item
            yield from _walk(item)


def _coerce_float(value: object) -> Optional[float]:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.replace("$", "").replace(",", "."))
        except ValueError:
            return None
    return None


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scrape Walmart clearance sections.")
    parser.add_argument(
        "--path",
        default=DEFAULT_CLEARANCE_PATH,
        help="Chemin Walmart à analyser (par défaut: %(default)s)",
    )
    parser.add_argument(
        "--output",
        default=DEFAULT_OUTPUT,
        help="Fichier JSON de sortie (par défaut: %(default)s)",
    )
    parser.add_argument(
        "--offline-source",
        type=Path,
        default=DEFAULT_OFFLINE_SAMPLE,
        help="Source locale utilisée si l'accès réseau échoue.",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=5,
        help="Nombre maximum de pages à récupérer par section.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="Niveau de verbosité du journal (DEBUG, INFO, WARNING...).",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO))
    scraper = WalmartClearanceScraper(
        max_pages=args.max_pages,
        offline_source=args.offline_source,
    )
    products = scraper.scrape(args.path)
    if not products:
        LOGGER.error("Aucun produit n'a pu être collecté.")
        return 1
    output_path = Path(args.output)
    output_path.write_text(
        json.dumps([asdict(product) for product in products], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    LOGGER.info("%s produits sauvegardés dans %s", len(products), output_path)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
