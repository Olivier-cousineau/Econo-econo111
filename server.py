import os
from pathlib import Path
from typing import Optional

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
import stripe

BASE_DIR = Path(__file__).resolve().parent


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


PUBLISHABLE_KEY_CANDIDATES = (
    "STRIPE_PUBLISHABLE_KEY",
    "NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY",
    "STRIPE_PUBLIC_KEY",
)


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


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=False)
