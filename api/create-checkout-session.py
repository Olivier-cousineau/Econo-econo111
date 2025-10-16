import json
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Dict, Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from stripe_backend import create_checkout_session_payload  # noqa: E402


class handler(BaseHTTPRequestHandler):  # pragma: no cover - Vercel runtime specific
    def _set_common_headers(self, status: int = HTTPStatus.OK) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
        self._set_common_headers(HTTPStatus.NO_CONTENT)
        self.end_headers()

    def do_POST(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
        length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(length) if length > 0 else b""

        try:
            body: Dict[str, Any] = json.loads(raw_body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            body = {}

        payload, status = create_checkout_session_payload(body)
        self._set_common_headers(status)
        self.end_headers()
        self.wfile.write(json.dumps(payload).encode("utf-8"))

    # Fallback for unexpected verbs
    def do_GET(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
        self._set_common_headers(HTTPStatus.METHOD_NOT_ALLOWED)
        self.end_headers()
        self.wfile.write(json.dumps({"error": "Method not allowed."}).encode("utf-8"))

