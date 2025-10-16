import os
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
import stripe

from pricing_checkout import create_checkout_session as build_checkout_session

BASE_DIR = Path(__file__).resolve().parent

app = Flask(__name__, static_folder=str(BASE_DIR), static_url_path="")
CORS(app)


@app.route("/")
def root() -> object:
    return send_from_directory(str(BASE_DIR), "index.html")


@app.route("/<path:asset>")
def serve_asset(asset: str) -> object:
    return send_from_directory(str(BASE_DIR), asset)


@app.route("/config", methods=["GET"])
def get_publishable_key() -> object:
    publishable_key = os.environ.get("STRIPE_PUBLISHABLE_KEY")
    if not publishable_key:
        return (
            jsonify({"error": "Missing STRIPE_PUBLISHABLE_KEY environment variable."}),
            500,
        )
    return jsonify({"publishableKey": publishable_key})


@app.route("/create-checkout-session", methods=["POST"])
def create_checkout_session() -> object:
    payload = request.get_json(silent=True) or {}

    try:
        session = build_checkout_session(payload)
    except RuntimeError as exc:  # pragma: no cover - configuration error
        return jsonify({"error": str(exc)}), 500
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
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
