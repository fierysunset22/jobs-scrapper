"""Local live dashboard server (stdlib only).

Serves dashboard.html and exposes POST /api/refresh, which re-runs the full
fetch → diff → regenerate pipeline so the dashboard's Refresh button pulls
genuinely fresh data. Intended for localhost use only.

    python3 serve.py            # http://127.0.0.1:8787
    python3 serve.py --port 9000
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
CONFIG = ROOT / "config.json"
DASHBOARD = ROOT / "dashboard" / "index.html"

# Serialize refreshes so two button presses can't run the pipeline concurrently
# and clobber each other's snapshot writes.
_refresh_lock = threading.Lock()
# Serialize preference writes so concurrent tabs can't corrupt the file.
_prefs_lock = threading.Lock()

# Reject absurd preference payloads outright (the real thing is a few KB).
_MAX_PREFS_BYTES = 5_000_000


def _run_pipeline() -> int:
    # Imported lazily so importing the server never pulls in the whole run stack.
    import run as runner
    return runner.run(CONFIG, DATA_DIR, seed=False)


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path in ("/", "/index.html"):
            # Serve the main dashboard index. Prefer the dashboard/index.html
            # file when present, otherwise fall back to the older single-file
            # location for compatibility.
            preferred = ROOT / "dashboard" / "index.html"
            if preferred.exists():
                self._send(200, preferred.read_bytes(), "text/html; charset=utf-8")
                return
            if not DASHBOARD.exists():
                self._send(503, b"dashboard not generated yet; run python3 run.py",
                           "text/plain; charset=utf-8")
                return
            self._send(200, DASHBOARD.read_bytes(), "text/html; charset=utf-8")
            return
        # Serve static files under /dashboard/* (styles, app.js, data.json).
        if path.startswith("/dashboard/"):
            fp = ROOT / path.lstrip("/")
            if fp.exists() and fp.is_file():
                if fp.suffix == ".css":
                    ctype = "text/css; charset=utf-8"
                elif fp.suffix == ".js":
                    ctype = "application/javascript; charset=utf-8"
                elif fp.suffix == ".json":
                    ctype = "application/json; charset=utf-8"
                else:
                    ctype = "application/octet-stream"
                self._send(200, fp.read_bytes(), ctype)
                return
        elif path == "/api/health":
            self._send(200, b'{"ok":true}', "application/json")
        elif path == "/api/prefs":
            from scraper import prefs as prefs_store
            with _prefs_lock:
                data = prefs_store.load_prefs(DATA_DIR)
            self._send(200, json.dumps(data).encode(), "application/json")
        else:
            self._send(404, b"not found", "text/plain; charset=utf-8")

    def do_POST(self):
        path = self.path.split("?")[0]
        if path == "/api/prefs":
            self._save_prefs()
            return
        if path == "/api/update-filters":
            self._update_filters()
            return
        if path != "/api/refresh":
            self._send(404, b"not found", "text/plain; charset=utf-8")
            return
        # If a refresh is already running, don't queue another — just report busy.
        if not _refresh_lock.acquire(blocking=False):
            self._send(409, b'{"ok":false,"error":"refresh already running"}',
                       "application/json")
            return
        try:
            self._run_and_respond()
        finally:
            _refresh_lock.release()

    def _save_prefs(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > _MAX_PREFS_BYTES:
            self._send(400, b'{"ok":false,"error":"bad payload size"}',
                       "application/json")
            return
        try:
            body = json.loads(self.rfile.read(length))
        except ValueError:
            self._send(400, b'{"ok":false,"error":"invalid json"}',
                       "application/json")
            return
        from scraper import prefs as prefs_store
        with _prefs_lock:
            saved = prefs_store.save_prefs(DATA_DIR, body)
        self._send(200, json.dumps({"ok": True, **saved}).encode(),
                   "application/json")

    def _update_filters(self):
        """Apply UI-only filter overrides without mutating the repo config."""
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > 10_000:
            self._send(400, b'{"ok":false,"error":"bad payload size"}',
                       "application/json")
            return
        try:
            body = json.loads(self.rfile.read(length))
        except ValueError:
            self._send(400, b'{"ok":false,"error":"invalid json"}',
                       "application/json")
            return

        # Important: do not touch config.json here. The repo config is the
        # default source for filters, while any edits from the browser stay in
        # localStorage as a session-specific override.
        # We still accept the request so the UI can reload, but we never mutate
        # the on-disk config file.

        # Re-run the pipeline with new filters. Don't block the HTTP response
        # on the potentially long-running pipeline: schedule it in a
        # background thread so the UI gets an immediate 200 and the refresh
        # happens asynchronously. The refresh lock still serializes runs.
        def _background_run():
            if not _refresh_lock.acquire(blocking=False):
                return
            try:
                try:
                    _run_pipeline()
                except Exception as exc:
                    print(f"[server] background pipeline failed: {exc}")
            finally:
                _refresh_lock.release()

        t = threading.Thread(target=_background_run, daemon=True)
        t.start()
        # Respond immediately — the client can still trigger an explicit
        # Refresh which reports busy if a run is active.
        self._send(200, b'{"ok":true,"background":true}', "application/json")

    def _run_and_respond(self):
        try:
            _run_pipeline()
            self._send(200, b'{"ok":true}', "application/json")
        except Exception as exc:  # report failure to the button instead of 500-ing silently
            body = json.dumps({"ok": False, "error": str(exc)}).encode()
            self._send(500, body, "application/json")

    def log_message(self, fmt, *args):  # quieter console
        print(f"[server] {self.address_string()} {fmt % args}")


def serve(host: str = "127.0.0.1", port: int = 8787) -> None:
    from scraper.env import load_env
    load_env(ROOT / ".env")
    # Make sure there's something to serve on first launch.
    if not DASHBOARD.exists():
        from scraper.dashboard import build_dashboard
        build_dashboard(DATA_DIR, DASHBOARD, CONFIG)

    httpd = ThreadingHTTPServer((host, port), Handler)
    url = f"http://{host}:{port}"
    print(f"Job Tracker dashboard live at {url}")
    print("  • open that URL in your browser")
    print("  • the Refresh button now re-fetches all companies and updates live")
    print("  • Ctrl-C to stop")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped.")
        httpd.server_close()
