import json
import os
from http.server import BaseHTTPRequestHandler
from typing import Any, Dict


def _write_json(handler: BaseHTTPRequestHandler, status_code: int, payload: Dict[str, Any]) -> None:
    handler.send_response(status_code)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.end_headers()
    handler.wfile.write(json.dumps(payload).encode("utf-8"))


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self) -> None:  # noqa: N802 (Vercel interface)
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802 (Vercel interface)
        publishable_key = os.environ.get("STRIPE_PUBLISHABLE_KEY")
        if not publishable_key:
            _write_json(
                self,
                500,
                {"error": "Missing STRIPE_PUBLISHABLE_KEY environment variable."},
            )
            return

        _write_json(self, 200, {"publishableKey": publishable_key})
