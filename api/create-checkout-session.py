import json
from http.server import BaseHTTPRequestHandler
from typing import Any, Dict

import stripe

from stripe_backend import (
    ConfigurationError,
    InvalidPlanError,
    create_checkout_session,
    dump_json,
)


class handler(BaseHTTPRequestHandler):
    def _read_json_body(self) -> Dict[str, Any]:
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            content_length = 0

        raw_body = self.rfile.read(content_length) if content_length > 0 else b""
        if not raw_body:
            return {}

        try:
            return json.loads(raw_body.decode("utf-8"))
        except json.JSONDecodeError:
            return {}

    def do_POST(self) -> None:  # noqa: N802 - interface defined by BaseHTTPRequestHandler
        if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
            payload: Dict[str, Any] = {}
        else:
            payload = self._read_json_body()

        status = 200
        body: Dict[str, Any]

        try:
            session = create_checkout_session(payload)
            body = {"sessionId": session.get("id")}
        except InvalidPlanError as exc:
            status = 400
            body = {"error": str(exc)}
        except ConfigurationError as exc:
            status = 500
            body = {"error": str(exc)}
        except stripe.error.StripeError as exc:
            status = 400
            body = {"error": exc.user_message or str(exc)}
        except Exception as exc:  # pragma: no cover - unexpected failure
            status = 500
            body = {"error": str(exc)}

        raw = dump_json(body)
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

