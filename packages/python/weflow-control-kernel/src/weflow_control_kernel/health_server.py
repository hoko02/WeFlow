"""Local-only HTTP health server for non-API skeleton processes."""

from __future__ import annotations

import json
from collections.abc import Mapping
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .status import build_service_status


def serve_health(
    service_name: str,
    port: int,
    *,
    environment: Mapping[str, str] | None = None,
    root: Path | None = None,
) -> None:
    """Serve only liveness/readiness diagnostics on loopback, never business routes."""

    class HealthHandler(BaseHTTPRequestHandler):
        def _write_status(self, status_code: int, payload: dict[str, object]) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            status = build_service_status(service_name, environment=environment, root=root)
            if self.path == "/health/live":
                self._write_status(200, status)
                return
            if self.path == "/health/ready":
                self._write_status(200 if status["ready"] else 503, status)
                return
            self._write_status(404, {"detail": "foundation-health-endpoint-not-found"})

        def log_message(self, _: str, *__: object) -> None:
            """Avoid emitting request values to terminal logs in Change 0."""

    server = ThreadingHTTPServer(("127.0.0.1", port), HealthHandler)
    try:
        server.serve_forever(poll_interval=0.25)
    finally:
        server.server_close()
