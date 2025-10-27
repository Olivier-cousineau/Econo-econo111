import json
import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import quote

import requests
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
import stripe

BASE_DIR = Path(__file__).resolve().parent
WALMART_STORE_ID = "3131"  # Walmart Blainville
WALMART_SOURCE_FILE = BASE_DIR / "data" / "walmart" / "blainville.json"
PENNY_DEAL_OUTPUT_FILE = BASE_DIR / "logs" / "penny_deals_blainville.json"
WALMART_API_BASE = "https://www.walmart.ca/api/product-page"
WALMART_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
}
SKU_PATTERN = re.compile(r"/([A-Za-z0-9]+)(?:\?|$)")


def _extract_walmart_sku(url: Optional[str]) -> Optional[str]:
    if not isinstance(url, str):
        return None
    match = SKU_PATTERN.search(url)
    if not match:
        return None
    return match.group(1)


def _detect_walmart_penny_deals(
    source_file: Path, store_id: str
) -> Tuple[List[Dict[str, object]], List[str]]:
    try:
        raw_content = source_file.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise
    except OSError as exc:
        raise RuntimeError(f"Impossible de lire {source_file.name} : {exc}") from exc

    try:
        products = json.loads(raw_content)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Le fichier {source_file.name} contient un JSON invalide") from exc

    if not isinstance(products, list):
        raise ValueError(f"Le fichier {source_file.name} ne contient pas une liste de produits")

    penny_deals: List[Dict[str, object]] = []
    errors: List[str] = []

    for product in products:
        if not isinstance(product, dict):
            continue

        product_link = product.get("product_link")
        sku = _extract_walmart_sku(product_link)
        if not sku:
            errors.append(
                f"Impossible d'extraire le SKU depuis le lien produit : {product_link!r}"
            )
            continue

        api_url = f"{WALMART_API_BASE}/{sku}?storeId={store_id}"
        try:
            response = requests.get(api_url, headers=WALMART_HEADERS, timeout=10)
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

        numeric_price: Optional[float]
        if isinstance(price, (int, float)):
            numeric_price = float(price)
        elif isinstance(price, str):
            try:
                numeric_price = float(price)
            except ValueError:
                numeric_price = None
        else:
            numeric_price = None

        if numeric_price is not None and numeric_price <= 0.01:
            penny_entry = dict(product)
            penny_entry["sku"] = sku
            penny_entry["penny_price"] = f"{numeric_price:.2f}$"
            penny_deals.append(penny_entry)
        elif numeric_price is None:
            errors.append(
                "Prix manquant ou invalide pour le SKU "
                f"{sku} dans la réponse de l'API Walmart"
            )

    return penny_deals, errors


def _parse_env_value(raw_value: str) -> str:
    value = raw_value.strip()
    if not value:
        return ""

    if (value.startswith("\"") and value.endswith("\"")) or (
        value.startswith("'") and value.endswith("'")
    ):
        return value[1:-1]

    if "#" in value:
        hash_index = value.index("#")
        if hash_index == 0 or value[hash_index - 1].isspace():
            stripped = value[:hash_index].strip()
            if stripped:
                return stripped

    return value


def _load_env_files() -> None:
    """Populate os.environ from local .env files when available."""

    for filename in (".env.local", ".env"):
        path = BASE_DIR / filename
        if not path.exists() or not path.is_file():
            continue

        try:
            for raw_line in path.read_text(encoding="utf-8").splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue

                key, value = line.split("=", 1)
                key = key.strip()
                if not key or key in os.environ:
                    continue

                os.environ[key] = _parse_env_value(value)
        except OSError:
            continue


_load_env_files()

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


def _ensure_stripe_secret() -> str:
    secret_key = os.environ.get("STRIPE_SECRET_KEY")
    if not secret_key:
        raise RuntimeError(
            "STRIPE_SECRET_KEY is not configured. Export it before starting the server."
        )
    return secret_key


@app.route("/")
def root() -> object:
    return send_from_directory(str(BASE_DIR), "index.html")


@app.route("/<path:asset>")
def serve_asset(asset: str) -> object:
    return send_from_directory(str(BASE_DIR), asset)


@app.route("/admin/penny-deals", methods=["POST"])
def detect_penny_deals() -> object:
    try:
        penny_deals, errors = _detect_walmart_penny_deals(
            WALMART_SOURCE_FILE, WALMART_STORE_ID
        )
    except FileNotFoundError:
        return (
            jsonify(
                {
                    "error": (
                        f"Le fichier source {WALMART_SOURCE_FILE.name} est introuvable."
                    )
                }
            ),
            500,
        )
    except (RuntimeError, ValueError) as exc:
        return jsonify({"error": str(exc)}), 500
    except Exception as exc:  # pragma: no cover - erreurs inattendues
        app.logger.exception("Erreur lors de la détection des penny deals")
        return jsonify({"error": f"Impossible de détecter les penny deals : {exc}"}), 500

    try:
        PENNY_DEAL_OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
        PENNY_DEAL_OUTPUT_FILE.write_text(
            json.dumps(penny_deals, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError as exc:
        return jsonify({"error": f"Impossible d'enregistrer le rapport : {exc}"}), 500

    try:
        relative_output = PENNY_DEAL_OUTPUT_FILE.relative_to(BASE_DIR)
    except ValueError:
        relative_output = PENNY_DEAL_OUTPUT_FILE

    payload = {
        "status": "ok",
        "count": len(penny_deals),
        "outputFile": str(relative_output),
        "downloadUrl": f"/{relative_output.as_posix()}",
        "errors": errors,
    }
    if penny_deals:
        payload["deals"] = penny_deals
    if errors:
        payload["warningCount"] = len(errors)

    return jsonify(payload), 200


PUBLISHABLE_KEY_CANDIDATES = (
    "STRIPE_PUBLISHABLE_KEY",
    "NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY",
    "STRIPE_PUBLIC_KEY",
)

GITHUB_API_BASE_URL = "https://api.github.com"
DEFAULT_WORKFLOW_REF = "main"


def _get_env_value(*keys: str) -> str:
    for key in keys:
        value = os.environ.get(key)
        if isinstance(value, str):
            trimmed = value.strip()
            if trimmed:
                return trimmed
    return ""


def _resolve_workflow_repository() -> str:
    return _get_env_value(
        "ADMIN_WORKFLOW_REPOSITORY", "ADMIN_WORKFLOW_REPO", "GITHUB_REPOSITORY"
    )


def _resolve_workflow_identifier() -> str:
    return _get_env_value(
        "ADMIN_WORKFLOW_ID", "ADMIN_WORKFLOW_FILE", "ADMIN_WORKFLOW_FILENAME"
    )


def _resolve_workflow_token() -> str:
    return _get_env_value("ADMIN_WORKFLOW_TOKEN", "GITHUB_TOKEN")


def _resolve_workflow_ref(payload: Optional[Dict[str, object]] = None) -> str:
    if isinstance(payload, dict):
        ref = payload.get("ref")
        if isinstance(ref, str) and ref.strip():
            return ref.strip()
    env_ref = _get_env_value("ADMIN_WORKFLOW_REF")
    return env_ref or DEFAULT_WORKFLOW_REF


def _normalise_workflow_inputs(
    inputs: Optional[Dict[str, object]]
) -> Optional[Dict[str, str]]:
    if not isinstance(inputs, dict):
        return None

    normalised: Dict[str, str] = {}
    for key, value in inputs.items():
        if not isinstance(key, str) or not key.strip():
            continue
        normalised[key.strip()] = "" if value is None else str(value)
    return normalised or None


def _get_publishable_key() -> Optional[str]:
    """Return the publishable key used by the client side."""

    for env_var in PUBLISHABLE_KEY_CANDIDATES:
        value = os.environ.get(env_var)
        if value:
            return value
    return None


@app.route("/config", methods=["GET"])
def get_publishable_key() -> object:
    publishable_key = _get_publishable_key()
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
    try:
        stripe.api_key = _ensure_stripe_secret()
    except RuntimeError as exc:  # pragma: no cover - configuration error
        return jsonify({"error": str(exc)}), 500

    payload = request.get_json(silent=True) or {}
    plan_key = payload.get("plan")
    config = PLAN_CONFIG.get(plan_key)
    if not config:
        return jsonify({"error": "Unknown pricing plan."}), 400

    locale = (payload.get("locale") or "en").split("-")[0].lower()
    stripe_locale = locale if locale in SUPPORTED_LOCALES else "en"

    product_name = (payload.get("name") or config["default_name"]).strip()
    description = (payload.get("description") or config["default_description"]).strip()

    success_url = os.environ.get(
        "STRIPE_SUCCESS_URL",
        "http://localhost:5000/success?session_id={CHECKOUT_SESSION_ID}",
    )
    cancel_url = os.environ.get("STRIPE_CANCEL_URL", "http://localhost:5000/cancel")

    try:
        session = stripe.checkout.Session.create(
            mode="payment",
            payment_method_types=["card"],
            line_items=[
                {
                    "quantity": 1,
                    "price_data": {
                        "currency": "cad",
                        "unit_amount": config["amount"],
                        "product_data": {
                            "name": product_name,
                            "description": description,
                        },
                    },
                }
            ],
            allow_promotion_codes=True,
            locale=stripe_locale,
            success_url=success_url,
            cancel_url=cancel_url,
            automatic_tax={"enabled": False},
        )
    except stripe.error.StripeError as exc:  # pragma: no cover - network/API error
        return jsonify({"error": exc.user_message or str(exc)}), 400
    except Exception as exc:  # pragma: no cover - unexpected error
        return jsonify({"error": str(exc)}), 500

    return jsonify({"sessionId": session.get("id")})


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


@app.route("/admin/dispatch-workflow", methods=["POST"])
def dispatch_workflow() -> object:
    repository = _resolve_workflow_repository()
    if not repository:
        return (
            jsonify(
                {
                    "error": "ADMIN_WORKFLOW_REPOSITORY (ou ADMIN_WORKFLOW_REPO) n'est pas configurée.",
                }
            ),
            500,
        )

    workflow_identifier = _resolve_workflow_identifier()
    if not workflow_identifier:
        return (
            jsonify(
                {
                    "error": "ADMIN_WORKFLOW_FILE (ou ADMIN_WORKFLOW_ID) n'est pas configuré.",
                }
            ),
            500,
        )

    token = _resolve_workflow_token()
    if not token:
        return (
            jsonify(
                {
                    "error": "ADMIN_WORKFLOW_TOKEN (ou GITHUB_TOKEN) est requis pour déclencher le workflow.",
                }
            ),
            500,
        )

    payload = request.get_json(silent=True) or {}
    ref = _resolve_workflow_ref(payload)
    inputs = None
    if isinstance(payload, dict):
        inputs = _normalise_workflow_inputs(payload.get("inputs"))

    url = (
        f"{GITHUB_API_BASE_URL}/repos/{repository}/actions/workflows/"
        f"{quote(workflow_identifier, safe='')}"
        "/dispatches"
    )

    body = {"ref": ref or DEFAULT_WORKFLOW_REF}
    if inputs:
        body["inputs"] = inputs

    app.logger.info(
        "Dispatching GitHub workflow %s on %s (ref=%s)",
        workflow_identifier,
        repository,
        body["ref"],
    )

    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=utf-8",
        "User-Agent": "econodeal-admin-workflow-trigger",
    }

    try:
        response = requests.post(url, headers=headers, json=body, timeout=10)
    except requests.RequestException as exc:  # pragma: no cover - network error
        app.logger.exception("Unable to dispatch GitHub workflow")
        return (
            jsonify(
                {
                    "error": f"Impossible de contacter l'API GitHub : {exc}",
                }
            ),
            500,
        )

    if response.status_code >= 400:
        message = f"GitHub a retourné le statut {response.status_code}."
        try:
            details = response.json()
            if isinstance(details, dict) and details.get("message"):
                message = str(details["message"])
        except ValueError:
            pass
        app.logger.error(
            "GitHub workflow dispatch failed (%s): %s",
            response.status_code,
            message,
        )
        return jsonify({"error": message}), response.status_code

    return (
        jsonify(
            {
                "status": "ok",
                "message": "Déclenchement du workflow GitHub effectué. Surveillez l'onglet Actions pour suivre le run.",
            }
        ),
        200,
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=False)
