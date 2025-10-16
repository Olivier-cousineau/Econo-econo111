import json
from http.server import BaseHTTPRequestHandler
from typing import Any, Dict

import stripe

from pricing_checkout import create_checkout_session


def _set_cors_headers(handler: BaseHTTPRequestHandler) -> None:
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type")
    handler.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")


def _write_json(handler: BaseHTTPRequestHandler, status_code: int, payload: Dict[str, Any]) -> None:
    handler.send_response(status_code)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.end_headers()
    handler.wfile.write(json.dumps(payload).encode("utf-8"))


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self) -> None:  # noqa: N802 (Vercel interface)
        self.send_response(204)
        _set_cors_headers(self)
        self.end_headers()

    def do_POST(self) -> None:  # noqa: N802 (Vercel interface)
        length_header = self.headers.get("content-length") or self.headers.get("Content-Length")
        try:
            length = int(length_header) if length_header else 0
        except ValueError:
            length = 0

        raw_body = self.rfile.read(length) if length else b""
        if raw_body:
            try:
                payload: Dict[str, Any] = json.loads(raw_body.decode("utf-8"))
            except json.JSONDecodeError:
                _write_json(self, 400, {"error": "Invalid JSON payload."})
                return
        else:
            payload = {}

        try:
            session = create_checkout_session(payload)
        except RuntimeError as exc:
            _write_json(self, 500, {"error": str(exc)})
            return
        except ValueError as exc:
            _write_json(self, 400, {"error": str(exc)})
            return
        except stripe.error.StripeError as exc:
            message = exc.user_message or str(exc)
            _write_json(self, 400, {"error": message})
            return
        except Exception as exc:  # pragma: no cover - unexpected error
            _write_json(self, 500, {"error": str(exc)})
            return

        _write_json(self, 200, {"sessionId": session.get("id")})
