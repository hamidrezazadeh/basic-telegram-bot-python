"""Receipt collector website. Runs only on your computer.

Start it:   python3 web.py
Then open:  http://127.0.0.1:8000
"""
import argparse
import json
import os
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlparse

import collect_receipts as cr

HERE = os.path.dirname(os.path.abspath(__file__))
ACCOUNTS_FILE = os.path.join(HERE, "accounts.json")
OUT_DIR = os.path.join(HERE, "output")
PAGE = os.path.join(HERE, "static", "index.html")

state_lock = threading.Lock()
job = {"running": False, "log": [], "error": ""}


# ---------- accounts ----------
def read_accounts():
    return cr.load_accounts(ACCOUNTS_FILE)


def write_accounts(accounts):
    with open(ACCOUNTS_FILE, "w") as f:
        json.dump({"accounts": accounts}, f, indent=2)
    try:
        os.chmod(ACCOUNTS_FILE, 0o600)  # only you can read it
    except OSError:
        pass


def public_accounts():
    """Never send passwords back to the browser."""
    return [{"email": a["email"]} for a in read_accounts()]


# ---------- collecting (runs in background) ----------
def run_job(query):
    def log(line):
        with state_lock:
            job["log"].append(line)

    try:
        cr.collect(read_accounts(), query, OUT_DIR, log)
    except Exception as e:  # show any error on the page
        with state_lock:
            job["error"] = str(e)
    finally:
        with state_lock:
            job["running"] = False


def read_results():
    path = os.path.join(OUT_DIR, "receipts.json")
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ---------- HTTP ----------
class Handler(BaseHTTPRequestHandler):
    server_version = "Receipts/1.0"

    def log_message(self, *args):
        pass  # keep the terminal quiet

    # Block other websites from talking to this local server.
    def _safe(self):
        host = (self.headers.get("Host") or "").split(":")[0]
        if host not in ("127.0.0.1", "localhost"):
            self._send(403, b"Forbidden")
            return False
        return True

    def _send(self, code, body, ctype="text/plain; charset=utf-8", extra=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, data, code=200):
        self._send(code, json.dumps(data).encode(), "application/json")

    def _body(self):
        # JSON only: a normal web form from another site cannot send this.
        if not (self.headers.get("Content-Type") or "").startswith("application/json"):
            return None
        n = int(self.headers.get("Content-Length") or 0)
        try:
            return json.loads(self.rfile.read(n) or b"{}")
        except ValueError:
            return None

    def _file(self, path, ctype, download_name=None):
        with open(path, "rb") as f:
            data = f.read()
        extra = {}
        if download_name:
            extra["Content-Disposition"] = f'attachment; filename="{download_name}"'
        self._send(200, data, ctype, extra)

    def do_GET(self):
        if not self._safe():
            return
        path = urlparse(self.path).path
        if path == "/":
            self._file(PAGE, "text/html; charset=utf-8")
        elif path == "/api/accounts":
            self._json(public_accounts())
        elif path == "/api/status":
            with state_lock:
                self._json(dict(job))
        elif path == "/api/receipts":
            self._json(read_results())
        elif path == "/download/receipts.csv":
            csv_path = os.path.join(OUT_DIR, "receipts.csv")
            if os.path.exists(csv_path):
                self._file(csv_path, "text/csv; charset=utf-8", "receipts.csv")
            else:
                self._send(404, b"No CSV yet")
        elif path.startswith("/files/"):
            self._attachment(unquote(path[len("/files/"):]))
        else:
            self._send(404, b"Not found")

    def _attachment(self, rel):
        base = os.path.realpath(os.path.join(OUT_DIR, "attachments"))
        full = os.path.realpath(os.path.join(OUT_DIR, rel))
        if not full.startswith(base + os.sep) or not os.path.isfile(full):
            self._send(404, b"Not found")
            return
        ext = os.path.splitext(full)[1].lower()
        ctype = {".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg",
                 ".jpeg": "image/jpeg", ".gif": "image/gif", ".webp": "image/webp"}.get(
            ext, "application/octet-stream")
        self._file(full, ctype)

    def do_POST(self):
        if not self._safe():
            return
        data = self._body()
        if data is None:
            self._json({"error": "Bad request"}, 400)
            return
        path = urlparse(self.path).path

        if path == "/api/accounts":
            address = (data.get("email") or "").strip().lower()
            password = (data.get("app_password") or "").replace(" ", "")
            if "@" not in address or len(password) < 16:
                self._json({"error": "Enter an email and the 16-letter app password."}, 400)
                return
            accounts = [a for a in read_accounts() if a["email"].lower() != address]
            accounts.append({"email": address, "app_password": password})
            write_accounts(accounts)
            self._json(public_accounts())

        elif path == "/api/accounts/delete":
            address = (data.get("email") or "").strip().lower()
            write_accounts([a for a in read_accounts() if a["email"].lower() != address])
            self._json(public_accounts())

        elif path == "/api/collect":
            if not read_accounts():
                self._json({"error": "Add an account first."}, 400)
                return
            try:
                days = max(1, min(int(data.get("days") or 90), 3650))
            except ValueError:
                days = 90
            query = cr.build_query(days, (data.get("query") or "").strip() or None)
            with state_lock:
                if job["running"]:
                    self._json({"error": "Already running."}, 409)
                    return
                job.update(running=True, log=[], error="")
            threading.Thread(target=run_job, args=(query,), daemon=True).start()
            self._json({"ok": True})
        else:
            self._send(404, b"Not found")


def main():
    ap = argparse.ArgumentParser(description="Receipt collector website (local only).")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()

    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    url = f"http://127.0.0.1:{args.port}"
    print(f"Receipts website: {url}   (press Ctrl+C to stop)")
    if not args.no_browser:
        threading.Timer(0.5, webbrowser.open, args=(url,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
