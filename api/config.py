import json
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from stripe_backend import get_publishable_key_payload  # noqa: E402


class handler(BaseHTTPRequestHandler):  # pragma: no cover - Vercel runtime specific
    def _set_common_headers(self, status: int = HTTPStatus.OK) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
        self._set_common_headers(HTTPStatus.NO_CONTENT)
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
        payload, status = get_publishable_key_payload()
        self._set_common_headers(status)
        self.end_headers()
        self.wfile.write(json.dumps(payload).encode("utf-8"))

    # Fallback for unexpected verbs
    def do_POST(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
        self._set_common_headers(HTTPStatus.METHOD_NOT_ALLOWED)
        self.end_headers()
        self.wfile.write(json.dumps({"error": "Method not allowed."}).encode("utf-8"))

