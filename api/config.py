import json
from http.server import BaseHTTPRequestHandler

from stripe_backend import StripeConfigurationError, ensure_publishable_key


class handler(BaseHTTPRequestHandler):
    def _set_headers(self, status: int) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    def do_OPTIONS(self) -> None:  # pragma: no cover - handled by platform
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
        try:
            payload = {"publishableKey": ensure_publishable_key()}
            status = 200
        except StripeConfigurationError as exc:
            payload = {"error": str(exc)}
            status = 500

        self._set_headers(status)
        self.wfile.write(json.dumps(payload).encode("utf-8"))
