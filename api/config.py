from http.server import BaseHTTPRequestHandler

from stripe_backend import ConfigurationError, dump_json, get_publishable_key_payload


class handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 - interface defined by BaseHTTPRequestHandler
        try:
            payload = get_publishable_key_payload()
            status = 200
        except ConfigurationError as exc:
            payload = {"error": str(exc)}
            status = 500

        body = dump_json(payload)
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

