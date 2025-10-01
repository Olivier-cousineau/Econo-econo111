#!/usr/bin/env python3
"""Scrape Patrick Morin Prévost liquidation items and update the site JSON.

The public liquidation page exposes a VTEX search endpoint that returns the
products in JSON.  This script queries the endpoint, normalises each product to
match ``data/README.md`` and overwrites ``data/patrick-morin/prevost.json`` by
default.  When the ``--run-once`` flag is not supplied the scraper keeps running
and refreshes the dataset every three hours as requested by the client.

Example (single execution)::

    python automation/patrick_morin_prevost.py --run-once

The scheduler mode is ideal for long-running services (``systemd``, ``tmux`` or
containers).  Logs are emitted on STDOUT; adjust ``--log-level`` if you need
more details for debugging.
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import requests

LOGGER = logging.getLogger("patrick_morin_prevost")

DEFAULT_BASE_URL = "https://patrickmorin.com"
DEFAULT_COLLECTION_PATH = "/fr/liquidation"
DEFAULT_OUTPUT = Path("data/patrick-morin/prevost.json")
DEFAULT_INTERVAL_HOURS = 3
DEFAULT_TIMEOUT = 30
DEFAULT_PAGE_SIZE = 24
DEFAULT_STORE_NAME = "Patrick Morin"
DEFAULT_CITY = "Prévost"


class ScraperError(RuntimeError):
    """Raised when the remote endpoint responds with an error."""


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help="Base URL du site Patrick Morin (ex.: https://patrickmorin.com).",
    )
    parser.add_argument(
        "--collection-path",
        default=DEFAULT_COLLECTION_PATH,
        help="Chemin de la page liquidation (ex.: /fr/liquidation).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Fichier JSON de sortie (défaut: data/patrick-morin/prevost.json).",
    )
    parser.add_argument(
        "--store-name",
        default=DEFAULT_STORE_NAME,
        help="Nom du magasin à inscrire dans le JSON (défaut: Patrick Morin).",
    )
    parser.add_argument(
        "--city",
        default=DEFAULT_CITY,
        help="Ville à inscrire dans le JSON (défaut: Prévost).",
    )
    parser.add_argument(
        "--page-size",
        type=int,
        default=DEFAULT_PAGE_SIZE,
        help="Nombre maximum d'items par appel API (défaut: 24).",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT,
        help="Délai maximum (secondes) pour les requêtes HTTP (défaut: 30).",
    )
    parser.add_argument(
        "--interval-hours",
        type=float,
        default=DEFAULT_INTERVAL_HOURS,
        help="Intervalle en heures entre deux rafraîchissements (défaut: 3).",
    )
    parser.add_argument(
        "--run-once",
        action="store_true",
        help="Exécute une seule fois puis quitte (désactive le scheduler).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="N'écrit pas sur disque, affiche uniquement un résumé.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"],
        help="Niveau de log (défaut: INFO).",
    )
    return parser.parse_args(argv)


def build_search_url(base_url: str) -> str:
    base = base_url.rstrip("/")
    return f"{base}/api/catalog_system/pub/products/search/liquidation"


def build_referer(base_url: str, collection_path: str) -> str:
    base = base_url.rstrip("/")
    path = collection_path if collection_path.startswith("/") else f"/{collection_path}"
    return f"{base}{path}"


def _to_float(value: object) -> Optional[float]:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = value.strip().replace("$", "").replace(" ", "")
        cleaned = cleaned.replace(",", ".")
        if not cleaned:
            return None
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None


def fetch_liquidation_batch(
    session: requests.Session,
    url: str,
    start: int,
    page_size: int,
    timeout: int,
    referer: str,
) -> List[dict]:
    params = {
        "fq": "availability:inventory",
        "map": "c",
        "O": "OrderByBestDiscountDESC",
        "_from": start,
        "_to": start + page_size - 1,
    }
    headers = {
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        "Referer": referer,
    }
    LOGGER.debug("Requête %s avec paramètres %s", url, params)
    try:
        response = session.get(url, params=params, headers=headers, timeout=timeout)
    except requests.RequestException as exc:  # pragma: no cover - réseau
        raise ScraperError(f"Requête HTTP échouée: {exc}") from exc

    if response.status_code >= 500:
        raise ScraperError(f"Serveur Patrick Morin indisponible (statut {response.status_code})")
    if response.status_code == 404:
        raise ScraperError("Endpoint de recherche introuvable (404)")
    if response.status_code != 200:
        raise ScraperError(f"Réponse inattendue {response.status_code}: {response.text[:200]}")

    try:
        payload = response.json()
    except json.JSONDecodeError as exc:
        raise ScraperError(f"Réponse JSON invalide: {exc}") from exc

    if not isinstance(payload, list):
        raise ScraperError("Format inattendu: la réponse JSON devrait être une liste")
    return payload


def fetch_all_liquidations(
    session: requests.Session,
    base_url: str,
    collection_path: str,
    page_size: int,
    timeout: int,
) -> List[dict]:
    url = build_search_url(base_url)
    referer = build_referer(base_url, collection_path)
    start = 0
    products: List[dict] = []

    while True:
        batch = fetch_liquidation_batch(
            session, url, start, page_size, timeout, referer
        )
        LOGGER.debug("Lot de %d items reçu (départ %d)", len(batch), start)
        if not batch:
            break
        products.extend(batch)
        if len(batch) < page_size:
            break
        start += page_size
    LOGGER.info("%d produits récupérés depuis Patrick Morin", len(products))
    return products


def _resolve_product_url(base_url: str, product: dict) -> Optional[str]:
    link = product.get("link")
    if isinstance(link, str) and link:
        if link.startswith("http"):
            return link
        base = base_url.rstrip("/")
        if link.startswith("/"):
            return f"{base}{link}"
        return f"{base}/{link}"

    link_text = product.get("linkText")
    if isinstance(link_text, str) and link_text:
        base = base_url.rstrip("/")
        slug = link_text.strip("/")
        return f"{base}/{slug}/p"
    return None


def _resolve_image_url(base_url: str, item: dict) -> Optional[str]:
    images = item.get("images")
    if not isinstance(images, list):
        return None
    for entry in images:
        if not isinstance(entry, dict):
            continue
        url = entry.get("imageUrl") or entry.get("url")
        if not isinstance(url, str) or not url:
            continue
        if url.startswith("//"):
            return "https:" + url
        if url.startswith("http"):
            return url
        base = base_url.rstrip("/")
        if url.startswith("/"):
            return f"{base}{url}"
        return f"{base}/{url}"
    return None


def _choose_best_offer(item: dict) -> Optional[Tuple[Optional[str], float, float]]:
    sellers = item.get("sellers")
    if not isinstance(sellers, list):
        return None

    best: Optional[Tuple[Optional[str], float, float, float]] = None
    for seller in sellers:
        if not isinstance(seller, dict):
            continue
        offer = seller.get("commertialOffer")
        if not isinstance(offer, dict):
            continue
        available_qty = offer.get("AvailableQuantity")
        if isinstance(available_qty, (int, float)) and available_qty <= 0:
            continue
        if offer.get("IsAvailable") is False:
            continue
        sale_price = _to_float(offer.get("Price"))
        list_price = _to_float(offer.get("ListPrice"))
        if sale_price is None and list_price is None:
            continue
        if sale_price is None:
            sale_price = list_price
        if sale_price is None:
            continue
        if list_price is None or list_price <= 0:
            list_price = sale_price
        discount = list_price - sale_price
        seller_id = seller.get("sellerId") if isinstance(seller.get("sellerId"), str) else None
        current = (seller_id, list_price, sale_price, discount)
        if best is None:
            best = current
        else:
            _, best_list, best_sale, best_discount = best
            if discount > best_discount + 0.01:
                best = current
            elif math.isclose(discount, best_discount, abs_tol=0.01) and sale_price < best_sale:
                best = current
            elif math.isclose(discount, best_discount, abs_tol=0.01) and list_price < best_list:
                best = current
    if best is None:
        return None
    seller_id, list_price, sale_price, _ = best
    return seller_id, list_price, sale_price


def normalise_products(
    products: Iterable[dict],
    base_url: str,
    store: str,
    city: str,
) -> List[Dict[str, object]]:
    normalised: List[Dict[str, object]] = []
    for product in products:
        if not isinstance(product, dict):
            continue
        name = product.get("productName") or product.get("productTitle")
        if not isinstance(name, str) or not name.strip():
            continue
        product_url = _resolve_product_url(base_url, product)
        if not product_url:
            LOGGER.debug("Produit %r ignoré (URL manquante)", name)
            continue

        best_candidate: Optional[Tuple[Optional[str], float, float]] = None
        image_url: Optional[str] = None
        items = product.get("items")
        if isinstance(items, list):
            for item in items:
                if not isinstance(item, dict):
                    continue
                offer = _choose_best_offer(item)
                if offer:
                    if not best_candidate:
                        best_candidate = offer
                        image_url = _resolve_image_url(base_url, item)
                    else:
                        _, current_list, current_sale = best_candidate
                        _, new_list, new_sale = offer
                        current_discount = current_list - current_sale
                        new_discount = new_list - new_sale
                        if new_discount > current_discount + 0.01:
                            best_candidate = offer
                            image_url = _resolve_image_url(base_url, item)
                        elif math.isclose(new_discount, current_discount, abs_tol=0.01) and new_sale < current_sale:
                            best_candidate = offer
                            image_url = _resolve_image_url(base_url, item)
        if not best_candidate:
            LOGGER.debug("Produit %r ignoré (aucune offre valide)", name)
            continue
        if not image_url and isinstance(items, list):
            for item in items:
                if not isinstance(item, dict):
                    continue
                image_url = _resolve_image_url(base_url, item)
                if image_url:
                    break
        seller_id, list_price, sale_price = best_candidate
        entry: Dict[str, object] = {
            "title": name.strip(),
            "url": product_url,
            "image": image_url or "",
            "price": float(list_price),
            "salePrice": float(sale_price),
            "store": store,
            "city": city,
        }
        if seller_id:
            entry["sellerId"] = seller_id
        sku = None
        sku_candidates = [product.get("productReference"), product.get("productId")]
        for candidate in sku_candidates:
            if isinstance(candidate, str) and candidate.strip():
                sku = candidate.strip()
                break
        if sku:
            entry["sku"] = sku
        normalised.append(entry)
    LOGGER.info("%d produits normalisés", len(normalised))
    return normalised


def write_json(path: Path, payload: List[Dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    LOGGER.info("Fichier %s mis à jour (%d items)", path, len(payload))


def run_once(args: argparse.Namespace) -> None:
    session = requests.Session()
    products = fetch_all_liquidations(
        session=session,
        base_url=args.base_url,
        collection_path=args.collection_path,
        page_size=max(1, args.page_size),
        timeout=args.timeout,
    )
    items = normalise_products(products, args.base_url, args.store_name, args.city)
    if args.dry_run:
        LOGGER.info("[DRY-RUN] %d items récupérés, aucun fichier écrit", len(items))
        return
    write_json(args.output, items)


def scheduler_loop(args: argparse.Namespace) -> None:
    interval = max(args.interval_hours, 0.1)
    LOGGER.info("Scheduler activé: rafraîchissement toutes les %.2f heures", interval)
    while True:
        start = datetime.now(timezone.utc)
        try:
            run_once(args)
        except ScraperError as exc:
            LOGGER.error("Erreur lors du scraping: %s", exc)
        except Exception as exc:  # pragma: no cover - erreurs inattendues
            LOGGER.exception("Erreur inattendue: %s", exc)
        if args.run-once:
            break
        elapsed = (datetime.now(timezone.utc) - start).total_seconds()
        sleep_seconds = max(0.0, interval * 3600 - elapsed)
        next_run = datetime.now(timezone.utc) + timedelta(seconds=sleep_seconds)
        LOGGER.info("Prochaine exécution prévue vers %s", next_run.astimezone().isoformat())
        if sleep_seconds <= 0:
            continue
        try:
            time.sleep(sleep_seconds)
        except KeyboardInterrupt:
            LOGGER.info("Interruption reçue, arrêt du scheduler")
            break


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, str(args.log_level).upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    LOGGER.debug("Arguments reçus: %s", args)
    if args.run_once:
        try:
            run_once(args)
        except ScraperError as exc:
            LOGGER.error("Scraping échoué: %s", exc)
            return 1
        return 0
    scheduler_loop(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
