"""Temporal-shaped control-worker boundary with no workflow implementation in Change 0."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence

from weflow_control_kernel.health_server import serve_health
from weflow_control_kernel.status import build_service_status

SERVICE_NAME = "control-worker"
DEFAULT_PORT = 8001


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serve", action="store_true", help="serve local health endpoints only")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    arguments = parser.parse_args(argv)
    if arguments.serve:
        serve_health(SERVICE_NAME, arguments.port)
        return 0
    print(json.dumps(build_service_status(SERVICE_NAME), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
