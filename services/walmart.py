from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests

from config.settings import Settings

SKU_PATTERN = re.compile(r"/([A-Za-z0-9]+)(?:\?|$)")


def extract_walmart_sku(url: Optional[str]) -> Optional[str]:
    if not isinstance(url, str):
        return None
    match = SKU_PATTERN.search(url)
    if not match:
        return None
    return match.group(1)


def detect_penny_deals(settings: Settings) -> Tuple[List[Dict[str, object]], List[str]]:
    source_file = settings.walmart_source_file
    store_id = settings.walmart_store_id

    try:
        raw_content = source_file.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise
    except OSError as exc:  # pragma: no cover - filesystem errors are hard to reproduce
        raise RuntimeError(f"Impossible de lire {source_file.name} : {exc}") from exc

    try:
        products = json.loads(raw_content)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Le fichier {source_file.name} contient un JSON invalide") from exc

    if not isinstance(products, list):
        raise ValueError(
            f"Le fichier {source_file.name} ne contient pas une liste de produits"
        )

    penny_deals: List[Dict[str, object]] = []
    errors: List[str] = []

    for product in products:
        if not isinstance(product, dict):
            continue

        product_link = product.get("product_link")
        sku = extract_walmart_sku(product_link)
        if not sku:
            errors.append(
                f"Impossible d'extraire le SKU depuis le lien produit : {product_link!r}"
            )
            continue

        api_url = f"{settings.walmart_api_base}/{sku}?storeId={store_id}"
        try:
            response = requests.get(
                api_url,
                headers=settings.walmart_headers,
                timeout=settings.walmart_request_timeout,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            errors.append(f"Échec de la requête pour le SKU {sku} : {exc}")
            continue

        try:
            payload = response.json()
        except ValueError:
            errors.append(
                f"Réponse JSON invalide reçue pour le SKU {sku} (HTTP {response.status_code})"
            )
            continue

        price_info = payload.get("priceInfo") if isinstance(payload, dict) else None
        current_price = price_info.get("currentPrice") if isinstance(price_info, dict) else None
        price = current_price.get("price") if isinstance(current_price, dict) else None

        if price is None:
            penny_entry = dict(product)
            penny_entry["sku"] = sku
            penny_entry["penny_price"] = "0.01$"
            penny_deals.append(penny_entry)

    return penny_deals, errors


def resolve_dataset_path(settings: Settings, relative_path: str) -> Path:
    """Return an absolute dataset path within the configured data directory."""

    normalized = relative_path.lstrip("/\\")
    candidate = (settings.data_dir / normalized).resolve()
    data_root = settings.data_dir.resolve()
    try:
        candidate.relative_to(data_root)
    except ValueError:
        raise ValueError("Chemin de données invalide.")
    if candidate.suffix.lower() != ".json" or not candidate.is_file():
        raise FileNotFoundError(normalized)
    return candidate
