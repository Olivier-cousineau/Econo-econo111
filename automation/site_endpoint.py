#!/usr/bin/env python3
"""Simple HTTP endpoint to ingest scraper payloads into the static site.

Run this script alongside the static site to receive the JSON payloads emitted
by ``automation/scraper.py``.  Each POST request to ``/api/liquidations`` will
update the corresponding ``data/canadian-tire/<slug>.json`` file as well as the
``stores.json`` registry so that the frontend immediately benefits from the new
prices.

Example usage::

    python site_endpoint.py --host 0.0.0.0 --port 8000 \
        --data-root ../data/canadian-tire --api-key secret-token

When using the scraper, configure ``site_endpoint.url`` to point to the running
server (e.g. ``http://127.0.0.1:8000/api/liquidations``) and provide the same
``api_key`` if authentication is enabled.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import signal
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

LOGGER = logging.getLogger(__name__)
DEFAULT_DATA_ROOT = Path(__file__).resolve().parents[1] / "data" / "canadian-tire"
STORE_DIRECTORY_PATH = Path(__file__).resolve().parent / "canadian_tire_stores_qc.json"


@dataclass
class SiteEndpointConfig:
    """Runtime configuration for the site endpoint."""

    host: str
    port: int
    data_root: Path
    api_key: Optional[str] = None


def slugify(text: Optional[str]) -> str:
    """Return a filesystem-friendly version of *text*."""

    if not text:
        return ""
    import unicodedata

    normalized = unicodedata.normalize("NFKD", text)
    result: List[str] = []
    for char in normalized:
        if ord(char) >= 0x0300:
            continue
        lower_char = char.lower()
        if lower_char.isalnum():
            result.append(lower_char)
        elif lower_char in {" ", "-", "/", "_", "(", ")"}:
            if result and result[-1] != "-":
                result.append("-")
        else:
            if result and result[-1] != "-":
                result.append("-")
    slug = "".join(result).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug


def load_store_directory() -> List[Dict[str, Optional[str]]]:
    """Load the optional reference directory shipped with the repository."""

    if not STORE_DIRECTORY_PATH.exists():
        LOGGER.debug("Aucun répertoire des magasins trouvé à %s", STORE_DIRECTORY_PATH)
        return []
    try:
        with STORE_DIRECTORY_PATH.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        LOGGER.warning("Impossible de lire %s: %s", STORE_DIRECTORY_PATH, exc)
        return []
    if not isinstance(data, list):
        LOGGER.warning("Format inattendu pour %s", STORE_DIRECTORY_PATH)
        return []
    return data


def _match_store_entry(
    directory: Iterable[Dict[str, Optional[str]]],
    store_id: Optional[str],
    slug: Optional[str],
    nickname: Optional[str],
) -> Optional[Dict[str, Optional[str]]]:
    slug_candidates = [value for value in [slug, slugify(nickname)] if value]
    store_id = str(store_id) if store_id not in (None, "") else None

    for entry in directory:
        entry_store_id = entry.get("store_id")
        if entry_store_id and store_id and str(entry_store_id) == store_id:
            return entry
    for candidate in slug_candidates:
        for entry in directory:
            if entry.get("slug") == candidate:
                return entry
    return None


def normalise_store_metadata(
    directory: List[Dict[str, Optional[str]]],
    payload: Dict[str, object],
) -> Tuple[str, str, str, str, str]:
    """Derive slug, label, city and nickname for the incoming store."""

    store_id = payload.get("store_id")
    nickname = payload.get("store_nickname")
    if isinstance(store_id, (int, float)):
        store_id = str(int(store_id))
    elif store_id is not None:
        store_id = str(store_id)

    slug_hint = slugify(payload.get("store_slug") if isinstance(payload.get("store_slug"), str) else None)
    entry = _match_store_entry(directory, store_id, slug_hint, nickname if isinstance(nickname, str) else None)

    city = ""
    label = "Canadian Tire"
    nickname_str = nickname if isinstance(nickname, str) else ""
    slug_value = slug_hint

    if entry:
        city = entry.get("city") or city
        nickname_str = entry.get("nickname") or nickname_str
        slug_value = entry.get("slug") or slug_value
        entry_label = entry.get("label")
        if entry_label:
            label = entry_label
    if not city and nickname_str:
        city = nickname_str
    if not slug_value:
        slug_value = slugify(city) or slugify(store_id) or "magasin"
    if not nickname_str:
        nickname_str = city or slug_value.replace("-", " ").title()
    if label == "Canadian Tire" and city:
        label = f"Canadian Tire {city}"

    return slug_value, label, city or nickname_str, nickname_str, store_id or ""


def transform_item(city: str, raw: Dict[str, object]) -> Optional[Dict[str, object]]:
    """Convert scraper payload entries to the static JSON format."""

    name = raw.get("name") or raw.get("title")
    product_url = raw.get("product_url") or raw.get("url")
    image_url = raw.get("image_url") or raw.get("image")
    if not (isinstance(name, str) and isinstance(product_url, str)):
        return None

    price_regular = raw.get("price_regular")
    price_clearance = raw.get("price_clearance")
    discount_price = raw.get("salePrice") if "salePrice" in raw else raw.get("price_clearance")

    def _to_float(value):
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str) and value.strip():
            try:
                return float(value.replace("$", "").replace(",", "."))
            except ValueError:
                return None
        return None

    regular = _to_float(price_regular)
    sale = _to_float(price_clearance) if price_clearance is not None else _to_float(discount_price)
    if regular is None and sale is not None:
        regular = sale

    return {
        "title": name,
        "url": product_url,
        "image": image_url,
        "price": regular,
        "salePrice": sale,
        "store": "Canadian Tire",
        "city": city,
        "sku": raw.get("sku"),
    }


class LiquidationRequestHandler(BaseHTTPRequestHandler):
    server: "LiquidationHTTPServer"  # type: ignore[assignment]

    def do_GET(self) -> None:  # noqa: N802 (BaseHTTPRequestHandler API)
        if self.path.rstrip("/") == "/health":
            self._send_json(HTTPStatus.OK, {"status": "ok"})
        else:
            self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:  # noqa: N802 (BaseHTTPRequestHandler API)
        if self.path.rstrip("/") != "/api/liquidations":
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        if self.server.config.api_key:
            auth_header = self.headers.get("Authorization", "")
            if not auth_header.startswith("Bearer ") or auth_header.split(" ", 1)[1] != self.server.config.api_key:
                self.send_error(HTTPStatus.UNAUTHORIZED, "Jeton d'API manquant ou invalide")
                return

        content_length = int(self.headers.get("Content-Length", "0"))
        try:
            raw_body = self.rfile.read(content_length)
        except Exception as exc:  # pragma: no cover - defensive
            LOGGER.error("Lecture du corps de requête impossible: %s", exc)
            self.send_error(HTTPStatus.BAD_REQUEST, "Impossible de lire la requête")
            return

        try:
            payload = json.loads(raw_body)
        except json.JSONDecodeError:
            self.send_error(HTTPStatus.BAD_REQUEST, "JSON invalide")
            return

        if not isinstance(payload, dict):
            self.send_error(HTTPStatus.BAD_REQUEST, "Format de payload inattendu")
            return

        items = payload.get("items")
        if not isinstance(items, list):
            self.send_error(HTTPStatus.BAD_REQUEST, "Le champ 'items' est requis et doit être une liste")
            return

        slug, label, city, nickname, store_id = normalise_store_metadata(
            self.server.store_directory, payload
        )
        data_root = self.server.config.data_root
        data_root.mkdir(parents=True, exist_ok=True)

        transformed: List[Dict[str, object]] = []
        skipped = 0
        for entry in items:
            if not isinstance(entry, dict):
                skipped += 1
                continue
            transformed_entry = transform_item(city, entry)
            if transformed_entry:
                transformed.append(transformed_entry)
            else:
                skipped += 1

        file_path = data_root / f"{slug}.json"
        with file_path.open("w", encoding="utf-8") as fh:
            json.dump(transformed, fh, ensure_ascii=False, indent=2)
        LOGGER.info("%d items écrits dans %s (ignorés: %d)", len(transformed), file_path, skipped)

        self._update_store_registry(slug, label, city, nickname, store_id)
        self._send_json(
            HTTPStatus.OK,
            {
                "status": "ok",
                "items_received": len(items),
                "items_saved": len(transformed),
                "skipped": skipped,
                "file": str(file_path),
            },
        )

    def log_message(self, format: str, *args) -> None:  # noqa: A003 (BaseHTTPRequestHandler API)
        LOGGER.info("%s - %s", self.address_string(), format % args)

    def _send_json(self, status: HTTPStatus, payload: Dict[str, object]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _update_store_registry(
        self,
        slug: str,
        label: str,
        city: str,
        nickname: str,
        store_id: str,
    ) -> None:
        registry_path = self.server.config.data_root / "stores.json"
        if registry_path.exists():
            try:
                with registry_path.open("r", encoding="utf-8") as fh:
                    data = json.load(fh)
            except (OSError, json.JSONDecodeError):
                data = []
        else:
            data = []

        if not isinstance(data, list):
            data = []

        entry = None
        for item in data:
            if isinstance(item, dict) and item.get("slug") == slug:
                entry = item
                break

        if entry is None:
            entry = {}
            data.append(entry)

        entry.update(
            {
                "store_id": store_id or None,
                "label": label,
                "city": city,
                "nickname": nickname,
                "slug": slug,
                "province": "QC",
            }
        )

        with registry_path.open("w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
        LOGGER.debug("Registre des magasins mis à jour (%s)", registry_path)


class LiquidationHTTPServer(ThreadingHTTPServer):
    def __init__(self, config: SiteEndpointConfig):
        super().__init__((config.host, config.port), LiquidationRequestHandler)
        self.config = config
        self.store_directory = load_store_directory()


def parse_args() -> SiteEndpointConfig:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1", help="Adresse IP d'écoute (par défaut: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="Port d'écoute (par défaut: 8000)")
    parser.add_argument(
        "--data-root",
        type=Path,
        default=DEFAULT_DATA_ROOT,
        help="Répertoire où écrire les fichiers JSON (par défaut: data/canadian-tire)",
    )
    parser.add_argument(
        "--api-key",
        help="Active l'authentification Bearer. Le scraper doit envoyer le même jeton via Authorization.",
    )
    parser.add_argument(
        "--log-level",
        default=os.environ.get("LOG_LEVEL", "INFO"),
        help="Niveau de log (DEBUG, INFO, WARNING, ERROR)",
    )
    args = parser.parse_args()

    logging.basicConfig(level=getattr(logging, str(args.log_level).upper(), logging.INFO))
    data_root = args.data_root.resolve()
    return SiteEndpointConfig(host=args.host, port=args.port, data_root=data_root, api_key=args.api_key)


def run_server(config: SiteEndpointConfig) -> None:
    server = LiquidationHTTPServer(config)

    def _graceful_shutdown(signum, frame):  # noqa: ANN001 - signature imposed by signal
        LOGGER.info("Signal %s reçu, arrêt du serveur...", signum)
        server.shutdown()

    signal.signal(signal.SIGINT, _graceful_shutdown)
    signal.signal(signal.SIGTERM, _graceful_shutdown)

    LOGGER.info("Serveur d'ingestion prêt sur http://%s:%d", config.host, config.port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:  # pragma: no cover - handled via signal but kept for safety
        LOGGER.info("Interruption clavier, arrêt en cours...")
    finally:
        server.server_close()
        LOGGER.info("Serveur arrêté")


def main() -> None:
    config = parse_args()
    run_server(config)


if __name__ == "__main__":
    main()
