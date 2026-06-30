"""Read-only HTML dashboard for HydraMem.

Exposes a tiny stdlib-only HTTP server with three endpoints:

* ``/``           — HTML overview of the most recent stats + Night Gardener status.
* ``/stats.json`` — same data as JSON for scripting.
* ``/healthz``    — liveness probe.

Read-only by design: no endpoint writes to the graph or the telemetry DB.
Run with ``python -m hydramem.dashboard``. The server binds to localhost by
default; pass ``--host`` to expose it elsewhere.
"""
from __future__ import annotations

import argparse
import html
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from hydramem.cli import _compute_stats, _load_garden_metrics
from hydramem.core.logging import get_logger

logger = get_logger(__name__)


def _gather(days: int) -> dict:
    stats = _compute_stats(days=days) or {"period_days": days}
    stats.update(_load_garden_metrics())
    return stats


def _render_html(stats: dict) -> str:
    rows = "".join(
        f"<tr><th>{html.escape(str(k))}</th><td>{html.escape(str(v))}</td></tr>"
        for k, v in stats.items()
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>HydraMem dashboard</title>
<style>
 body {{ font-family: system-ui, sans-serif; max-width: 720px; margin: 2em auto;
        padding: 0 1em; color: #222; }}
 h1   {{ margin-bottom: 0.2em; }}
 small {{ color: #666; }}
 table {{ width: 100%; border-collapse: collapse; margin-top: 1em; }}
 th, td {{ text-align: left; padding: 6px 8px; border-bottom: 1px solid #eee;
          font-variant-numeric: tabular-nums; }}
 th   {{ background: #fafafa; width: 55%; }}
 tr:hover {{ background: #f6f6f6; }}
</style></head>
<body>
<h1>HydraMem dashboard</h1>
<small>Read-only view of telemetry + Night Gardener metrics.</small>
<table>{rows}</table>
<p><small>JSON: <a href="/stats.json">/stats.json</a></small></p>
</body></html>"""


class _Handler(BaseHTTPRequestHandler):
    days: int = 7  # set by main()

    def log_message(self, fmt: str, *args) -> None:  # noqa: D401
        logger.info("dashboard %s - %s", self.address_string(), fmt % args)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/healthz":
            self._send(200, "ok", "text/plain")
            return
        stats = _gather(self.days)
        if self.path.startswith("/stats.json"):
            self._send(200, json.dumps(stats, indent=2, default=str), "application/json")
            return
        if self.path in ("/", "/index.html"):
            self._send(200, _render_html(stats), "text/html; charset=utf-8")
            return
        self._send(404, "not found", "text/plain")

    def _send(self, status: int, body: str, ctype: str) -> None:
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)


def serve(host: str = "127.0.0.1", port: int = 8765, days: int = 7) -> None:
    _Handler.days = days
    server = ThreadingHTTPServer((host, port), _Handler)
    logger.info("HydraMem dashboard serving on http://%s:%d", host, port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("dashboard shutting down")
    finally:
        server.server_close()


def main() -> None:
    p = argparse.ArgumentParser(prog="hydramem-dashboard", description=__doc__)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--days", type=int, default=7)
    args = p.parse_args()
    serve(host=args.host, port=args.port, days=args.days)


if __name__ == "__main__":
    main()
