import json
import os
from pathlib import Path
from typing import Dict, Iterable, Optional
from urllib.parse import quote

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

from api.payments import create_checkout_session as create_stripe_checkout
from api.payments import get_publishable_key as resolve_publishable_key
from config.settings import get_settings
from services.walmart import (
    detect_penny_deals as compute_walmart_penny_deals,
    resolve_dataset_path,
)

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


@app.route("/")
def root() -> object:
    return send_from_directory(str(BASE_DIR), "index.html")


@app.route("/<path:asset>")
def serve_asset(asset: str) -> object:
    return send_from_directory(str(BASE_DIR), asset)


@app.route("/admin/penny-deals", methods=["POST"])
def detect_penny_deals() -> object:
    try:
        penny_deals, errors = compute_walmart_penny_deals(settings)
    except FileNotFoundError:
        return (
            jsonify(
                {
                    "error": (
                        f"Le fichier source {settings.walmart_source_file.name} est introuvable."
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
        settings.penny_deal_output_file.parent.mkdir(parents=True, exist_ok=True)
        settings.penny_deal_output_file.write_text(
            json.dumps(penny_deals, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError as exc:
        return jsonify({"error": f"Impossible d'enregistrer le rapport : {exc}"}), 500

    try:
        relative_output = settings.penny_deal_output_file.relative_to(BASE_DIR)
    except ValueError:
        relative_output = settings.penny_deal_output_file

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


def _iter_dataset_files() -> Iterable[Path]:
    data_root = settings.data_dir
    if not data_root.exists() or not data_root.is_dir():
        return []
    return sorted(data_root.rglob("*.json"))


def _load_dataset(relative_path: str) -> Dict[str, object]:
    dataset_path = resolve_dataset_path(settings, relative_path)

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
        default_path = settings.deals_default_path
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
