import os
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

from stripe_backend import create_checkout_session_payload, get_publishable_key_payload

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
    payload, status = get_publishable_key_payload()
    return jsonify(payload), status


@app.route("/create-checkout-session", methods=["POST"])
def create_checkout_session() -> object:
    payload = request.get_json(silent=True) or {}
    payload, status = create_checkout_session_payload(payload)
    return jsonify(payload), status


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
