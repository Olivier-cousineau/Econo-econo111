import json
import os
from pathlib import Path
import re
from typing import Dict, Iterable, List, Tuple

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

from api.payments import create_checkout_session as create_stripe_checkout
from api.payments import get_publishable_key as resolve_publishable_key
from config.settings import get_settings

settings = get_settings()
BASE_DIR = settings.base_dir

app = Flask(__name__, static_folder=str(BASE_DIR), static_url_path="")
CORS(app)

PLAN_CONFIG = {
    "essential": {
        "amount": 999,
        "default_name": "Essential plan",
        "default_description": "Essential access to the clearance intelligence feed.",
    },
    "advanced": {
        "amount": 1999,
        "default_name": "Advanced plan",
        "default_description": "Unlimited catalog access with real-time alerts.",
    },
    "premium": {
        "amount": 2999,
        "default_name": "Premium plan",
        "default_description": "Full AI optimisation suite for scaling resellers.",
    },
}

SUPPORTED_LOCALES = {"da", "de", "en", "es", "fi", "fr", "it", "ja", "nb", "nl", "pl", "pt", "sv"}


def _normalize_words(value: str) -> List[str]:
    cleaned = re.sub(r"[^\w\s]", " ", value.lower())
    return [part for part in cleaned.split() if part]


def _similarity_score(query: str, target: str) -> float:
    query_words = _normalize_words(query)
    target_words = _normalize_words(target)
    if not query_words or not target_words:
        return 0.0
    query_set = set(query_words)
    target_set = set(target_words)
    common = len(query_set & target_set)
    denominator = max(len(query_set), len(target_set))
    return common / denominator if denominator else 0.0


def _parse_price(value: object) -> Tuple[float | None, str | None]:
    if value is None:
        return None, None
    if isinstance(value, (int, float)):
        numeric = float(value)
        return numeric, f"${numeric:0.2f}"
    if isinstance(value, str):
        cleaned = value.strip()
        if not cleaned:
            return None, None
        numeric_str = re.sub(r"[^0-9.,]", "", cleaned)
        if not numeric_str:
            return None, cleaned
        # Remove thousand separators and normalise decimal point
        numeric_str = numeric_str.replace(",", "")
        try:
            numeric = float(numeric_str)
        except ValueError:
            return None, cleaned
        return numeric, cleaned
    return None, None


@app.route("/")
def root() -> object:
    return send_from_directory(str(BASE_DIR), "index.html")


@app.route("/<path:asset>")
def serve_asset(asset: str) -> object:
    return send_from_directory(str(BASE_DIR), asset)


def _iter_dataset_files() -> Iterable[Path]:
    data_root = settings.data_dir
    if not data_root.exists() or not data_root.is_dir():
        return []
    return sorted(data_root.rglob("*.json"))


def _resolve_dataset_path(relative_path: str) -> Path:
    normalized = (relative_path or "").lstrip("/\\")
    candidate = (settings.data_dir / normalized).resolve()
    data_root = settings.data_dir.resolve()
    try:
        candidate.relative_to(data_root)
    except ValueError as exc:
        raise ValueError("Chemin de données invalide.") from exc
    if candidate.suffix.lower() != ".json" or not candidate.is_file():
        raise FileNotFoundError(normalized or relative_path)
    return candidate


def _load_dataset(relative_path: str) -> Dict[str, object]:
    dataset_path = _resolve_dataset_path(relative_path)

    try:
        raw_content = dataset_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise
    except OSError as exc:
        raise RuntimeError(f"Impossible de lire le jeu de données : {exc}") from exc

    try:
        payload = json.loads(raw_content)
    except json.JSONDecodeError as exc:
        raise ValueError("Le fichier de données contient un JSON invalide.") from exc

    relative = dataset_path.relative_to(settings.data_dir)
    count = None
    if isinstance(payload, (list, dict)):
        try:
            count = len(payload)
        except TypeError:
            count = None

    return {
        "path": relative.as_posix(),
        "count": count,
        "data": payload,
    }


@app.route("/api/stores", methods=["GET"])
def list_store_datasets() -> object:
    datasets = []
    for path in _iter_dataset_files():
        relative = path.relative_to(settings.data_dir)
        parts = relative.parts
        source = parts[0] if len(parts) > 1 else None
        store = path.stem
        size = None
        try:
            size = path.stat().st_size
        except OSError:
            size = None
        datasets.append(
            {
                "path": relative.as_posix(),
                "source": source,
                "store": store,
                "size": size,
            }
        )

    return jsonify({"datasets": datasets, "count": len(datasets)})


@app.route("/api/deals", methods=["GET"])
def get_deals_dataset() -> object:
    relative_path = request.args.get("path")
    if not relative_path:
        default_path = getattr(settings, "deals_default_path", None)
        if default_path:
            relative_path = default_path
        else:
            return (
                jsonify({"error": "Le paramètre 'path' est requis pour charger un jeu de données."}),
                400,
            )

    try:
        dataset = _load_dataset(relative_path)
    except FileNotFoundError:
        return jsonify({"error": "Jeu de données introuvable."}), 404
    except ValueError as exc:
        message = str(exc)
        status = 400 if "Chemin de données" in message else 500
        return jsonify({"error": message}), status
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 500

    return jsonify(dataset)


@app.route("/compare", methods=["GET"])
def compare_products() -> object:
    query_name = (request.args.get("name") or "").strip()
    if not query_name:
        return jsonify({"error": "Le paramètre 'name' est requis."}), 400

    outputs_root = settings.base_dir / "outputs" / "canadiantire"
    if not outputs_root.exists() or not outputs_root.is_dir():
        return jsonify({"results": []})

    results: List[Dict[str, object]] = []

    for store_dir in outputs_root.iterdir():
        if not store_dir.is_dir():
            continue
        data_path = store_dir / "data.json"
        if not data_path.is_file():
            continue

        try:
            raw_content = data_path.read_text(encoding="utf-8")
            payload = json.loads(raw_content)
        except (OSError, json.JSONDecodeError):
            continue

        products = []
        store_meta: Dict[str, object] = {}
        if isinstance(payload, dict):
            products = payload.get("products") if isinstance(payload.get("products"), list) else []
            store_meta = payload.get("store", {}) if isinstance(payload.get("store"), dict) else {}
        elif isinstance(payload, list):
            products = payload

        for product in products:
            if not isinstance(product, dict):
                continue
            product_name = (
                product.get("name")
                or product.get("title")
                or product.get("product_title")
                or ""
            )
            if not product_name:
                continue

            score = _similarity_score(query_name, str(product_name))
            if score < 0.65:
                continue

            store_id = str(
                product.get("store_id")
                or store_meta.get("id")
                or store_dir.name.split("-")[0]
            )
            city = (
                product.get("city")
                or store_meta.get("city")
                or ""
            )

            price_candidates = [
                product.get("discount_price"),
                product.get("promo_price"),
                product.get("liquidation_price"),
                product.get("sale_price"),
                product.get("price"),
            ]
            price_value = None
            price_display = None
            for candidate in price_candidates:
                price_value, price_display = _parse_price(candidate)
                if price_value is not None or price_display is not None:
                    break

            if price_value is None and price_display is None:
                continue

            results.append(
                {
                    "store_id": store_id,
                    "city": city,
                    "price": price_display,
                    "discount": product.get("discount") or product.get("discount_text"),
                    "url": product.get("url"),
                    "score": round(score, 3),
                    "_sort_price": price_value if price_value is not None else float("inf"),
                }
            )

    sorted_results = sorted(results, key=lambda item: item.get("_sort_price", float("inf")))
    payload = []
    for item in sorted_results[:10]:
        cleaned = {key: value for key, value in item.items() if key != "_sort_price"}
        payload.append(cleaned)

    return jsonify({"results": payload})


@app.route("/config", methods=["GET"])
def get_publishable_key() -> object:
    publishable_key = resolve_publishable_key(settings)
    if not publishable_key:
        return (
            jsonify({
                "error": (
                    "Missing STRIPE_PUBLISHABLE_KEY, NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY or "
                    "STRIPE_PUBLIC_KEY environment variable."
                )
            }),
            500,
        )
    return jsonify({"publishableKey": publishable_key})


@app.route("/create-checkout-session", methods=["POST"])
def create_checkout_session() -> object:
    payload = request.get_json(silent=True) or {}

    try:
        session_payload = create_stripe_checkout(
            settings=settings,
            plan_config=PLAN_CONFIG,
            payload=payload,
            supported_locales=SUPPORTED_LOCALES,
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:  # pragma: no cover - unexpected error
        return jsonify({"error": str(exc)}), 500

    return jsonify(session_payload)


@app.route("/success", methods=["GET"])
def checkout_success() -> object:
    session_id = request.args.get("session_id")
    message = "Paiement complété avec succès. Merci !"
    if session_id:
        message += f"<br/><small>Session : {session_id}</small>"
    return (
        f"<h1>✅ Paiement confirmé</h1><p>{message}</p><p><a href='/pricing.html'>Retour aux forfaits</a></p>",
        200,
        {"Content-Type": "text/html; charset=utf-8"},
    )


@app.route("/cancel", methods=["GET"])
def checkout_cancelled() -> object:
    return (
        "<h1>Paiement annulé</h1><p>Vous pouvez reprendre votre inscription quand vous voulez.</p>"
        "<p><a href='/pricing.html'>Retour à la page des forfaits</a></p>",
        200,
        {"Content-Type": "text/html; charset=utf-8"},
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=False)
