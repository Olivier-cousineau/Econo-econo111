import json
from http.server import BaseHTTPRequestHandler
from typing import Any, Dict

import stripe

from stripe_backend import (
    StripeConfigurationError,
    StripePlanError,
    create_checkout_session,
)


class handler(BaseHTTPRequestHandler):
    def _set_headers(self, status: int) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    def do_OPTIONS(self) -> None:  # pragma: no cover - handled by platform
        self._set_headers(204)

    def _read_body(self) -> Dict[str, Any]:
        try:
            length = int(self.headers.get("content-length", "0"))
        except ValueError:
            length = 0
        body = self.rfile.read(length) if length else b""
        if not body:
            return {}
        try:
            return json.loads(body.decode("utf-8"))
        except json.JSONDecodeError:
            return {}

    def do_POST(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
        payload = self._read_body()
        status = 200
        try:
            response = create_checkout_session(payload)
        except StripeConfigurationError as exc:
            response = {"error": str(exc)}
            status = 500
        except StripePlanError as exc:
            response = {"error": str(exc)}
            status = 400
        except stripe.error.StripeError as exc:  # pragma: no cover - network/API error
            response = {"error": exc.user_message or str(exc)}
            status = 400
        except Exception as exc:  # pragma: no cover - unexpected error
            response = {"error": str(exc)}
            status = 500

        self._set_headers(status)
        if status != 204:
            self.wfile.write(json.dumps(response).encode("utf-8"))
