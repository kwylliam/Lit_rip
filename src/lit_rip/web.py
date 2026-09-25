"""Browser interface; downloaded files stay in memory."""

import json
import logging
import os
import secrets
import threading
import time
import webbrowser
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from urllib.parse import quote, urlsplit

from .downloader import Downloader, normalize_url
from .export import filename, render
from .models import DownloadError
from .search import SearchClient, SearchError, SearchBusyError


class BusyError(Exception):
    pass


@dataclass
class Job:
    id: str
    format: str
    state: str = "working"
    message: str = "Finding the story and chapters…"
    title: str = ""
    author: str = ""
    completed: int = 0
    total: int = 0
    name: str = ""
    content: bytes | None = None
    updated: float = field(default_factory=time.monotonic)

    def status(self):
        return {key: getattr(self, key) for key in
                ("id", "format", "state", "message", "title", "author", "completed", "total", "name")}


class Jobs:
    """One active download; retain at most three results for thirty minutes."""

    def __init__(self, downloader_factory=Downloader):
        self.downloader_factory = downloader_factory
        self.lock = threading.Lock()
        self.items: dict[str, Job] = {}

    def _prune(self):
        now = time.monotonic()
        for key, job in list(self.items.items()):
            if job.state != "working" and now - job.updated > 1800:
                del self.items[key]

    def start(self, url: str, series: bool, format: str):
        url = normalize_url(url)
        with self.lock:
            self._prune()
            if any(job.state == "working" for job in self.items.values()):
                raise BusyError("Another download is in progress. Wait for it to finish, then try again.")
            while len(self.items) >= 3:
                del self.items[next(iter(self.items))]
            job = Job(secrets.token_hex(16), format)
            self.items[job.id] = job
        threading.Thread(target=self._run, args=(job.id, url, series), daemon=True).start()
        return job.id

    def _update(self, job_id, **values):
        with self.lock:
            job = self.items[job_id]
            for key, value in values.items():
                setattr(job, key, value)
            job.updated = time.monotonic()

    def _run(self, job_id, url, series):
        try:
            downloader = self.downloader_factory(url, series=series)
            story = downloader.inspect()
            self._update(job_id, title=story.title, author=story.author, total=len(story.chapters))
            def progress(index, total, title):
                self._update(job_id, completed=index - 1, total=total,
                             message=f"Getting chapter {index} of {total}: {title}")
            story = downloader.download(progress)
            with self.lock:
                format = self.items[job_id].format
            content = render(story, format).encode("utf-8")
            self._update(job_id, content=content, name=filename(story, format),
                         completed=len(story.chapters), state="ready", message="Your file is ready.")
        except Exception as exc:
            logging.getLogger(__name__).debug("Browser download failed", exc_info=True)
            message = str(exc) if isinstance(exc, (DownloadError, OSError)) else "Something went wrong while preparing the file. Please try again."
            self._update(job_id, state="error", message=message)

    def get(self, job_id):
        with self.lock:
            self._prune()
            job = self.items.get(job_id)
            if job is None:
                return None
            return job.status(), job.content


class BrowserServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, port=0, *, host="127.0.0.1", public_host=None, allowed_hosts=None,
                 jobs=None, search_client=None):
        self.jobs = jobs if jobs is not None else Jobs()
        self.search_client = search_client if search_client is not None else SearchClient()
        self.token = secrets.token_hex(32)
        self.bind_host = host
        self.public_host = public_host or ("127.0.0.1" if host in ("0.0.0.0", "::") else host)
        configured_hosts = allowed_hosts if allowed_hosts is not None else os.environ.get("LIT_RIP_ALLOWED_HOSTS")
        explicit_hosts = configured_hosts is not None
        if isinstance(configured_hosts, str) and not configured_hosts.strip():
            explicit_hosts = False
        if isinstance(configured_hosts, str):
            configured_hosts = {value.strip() for value in configured_hosts.split(",") if value.strip()}
        elif configured_hosts is None or configured_hosts == "":
            configured_hosts = set()
        else:
            configured_hosts = set(configured_hosts)
        super().__init__((host, port), Handler)
        self.origin = f"http://{self.public_host}:{self.server_port}"
        if configured_hosts:
            self.allowed_hosts = configured_hosts
        elif explicit_hosts or host in ("0.0.0.0", "::"):
            self.allowed_hosts = {"*"} if not configured_hosts and host in ("0.0.0.0", "::") else set()
        else:
            self.allowed_hosts = {f"{host}:{self.server_port}", f"localhost:{self.server_port}",
                                  f"127.0.0.1:{self.server_port}", f"[::1]:{self.server_port}"}

    def host_allowed(self, value):
        return "*" in self.allowed_hosts or value in self.allowed_hosts


class Handler(BaseHTTPRequestHandler):
    server: BrowserServer

    def log_message(self, format, *args):
        logging.getLogger(__name__).debug(format, *args)

    def setup(self):
        super().setup()
        self.connection.settimeout(10)

    def _send(self, status, body, content_type="application/json; charset=utf-8", disposition=None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        if disposition:
            self.send_header("Content-Disposition", disposition)
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _json(self, status, data):
        self._send(status, json.dumps(data).encode("utf-8"))

    def _local_request(self):
        # Reject foreign websites and DNS rebinding to this local server.
        host = self.headers.get("Host", "")
        if not self.server.host_allowed(host):
            self._json(403, {"error": "Use the local address printed in the terminal."})
            return False
        origin = self.headers.get("Origin")
        parsed_origin = urlsplit(origin) if origin else None
        if ((parsed_origin and (parsed_origin.scheme != "http" or parsed_origin.netloc != host))
                or self.headers.get("Sec-Fetch-Site") == "cross-site"):
            self._json(403, {"error": "This app accepts requests from its own browser page only."})
            return False
        return True

    def do_GET(self):
        if not self._local_request():
            return
        path = urlsplit(self.path).path
        assets = {"/": ("index.html", "text/html; charset=utf-8"),
                  "/app.css": ("app.css", "text/css; charset=utf-8"),
                  "/app.js": ("app.js", "text/javascript; charset=utf-8")}
        if path in assets:
            name, content_type = assets[path]
            body = files("lit_rip").joinpath("static", name).read_bytes()
            if name == "index.html":
                body = body.replace(b"__TOKEN__", self.server.token.encode("ascii"))
            self._send(200, body, content_type)
            return
        if path == "/favicon.ico":
            self._send(204, b"")
            return
        parts = path.strip("/").split("/")
        if len(parts) in (3, 4) and parts[:2] == ["api", "jobs"]:
            job = self.server.jobs.get(parts[2])
            if job is None:
                self._json(404, {"error": "This download has expired. Prepare the file again."})
                return
            status, content = job
            if len(parts) == 3:
                self._json(200, status)
                return
            if parts[3] == "file":
                if status["state"] != "ready" or content is None:
                    self._json(409, {"error": "The file is not ready yet."})
                    return
                disposition = f"attachment; filename=story.{status['format']}; filename*=UTF-8''{quote(status['name'], safe='')}"
                mime = "text/markdown" if status["format"] == "md" else "text/plain"
                self._send(200, content, mime + "; charset=utf-8", disposition)
                return
        self._json(404, {"error": "Not found."})

    def do_POST(self):
        if not self._local_request():
            return
        if not secrets.compare_digest(self.headers.get("X-Lit-Rip-Token", ""), self.server.token):
            self._json(403, {"error": "Please reload the app and try again."})
            return
        if self.path not in ("/api/jobs", "/api/search"):
            self._json(404, {"error": "Not found."})
            return
        if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
            self._json(415, {"error": "Expected JSON."})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 8192:
                raise ValueError("Request is empty or too large.")
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict):
                raise ValueError("Expected a JSON object.")
            if self.path == "/api/search":
                # Keep the two-argument call for older injected test clients;
                # the site field is optional for API callers and defaults to
                # the original Literotica search.
                if "site" in data:
                    result = self.server.search_client.search(data.get("query"), data.get("page", 1), data.get("site"))
                else:
                    result = self.server.search_client.search(data.get("query"), data.get("page", 1))
                self._json(200, result.as_dict())
                return
            if not isinstance(data.get("url"), str):
                raise ValueError("Enter a story or series URL.")
            if data.get("format") not in ("md", "txt") or type(data.get("series")) is not bool:
                raise ValueError("Choose a valid format and series option.")
            job_id = self.server.jobs.start(data["url"], data["series"], data["format"])
        except SearchBusyError as exc:
            self._json(409, {"error": str(exc)})
        except SearchError as exc:
            self._json(502, {"error": str(exc)})
        except BusyError as exc:
            self._json(409, {"error": str(exc)})
        except (ValueError, DownloadError) as exc:
            self._json(400, {"error": str(exc)})
        else:
            self._json(202, {"id": job_id})


def serve(port=0, *, host="127.0.0.1", public_host=None, allowed_hosts=None, open_browser=True):
    with BrowserServer(port, host=host, public_host=public_host, allowed_hosts=allowed_hosts) as server:
        print(f"Lit Rip is running at {server.origin}", flush=True)
        print("Keep this terminal open. Press Ctrl+C to stop.", flush=True)
        if open_browser:
            def launch():
                try:
                    if not webbrowser.open(server.origin):
                        print("Open the address above in your browser.", flush=True)
                except webbrowser.Error:
                    print("Open the address above in your browser.", flush=True)
            threading.Thread(target=launch, daemon=True).start()
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\nLit Rip stopped.")
    return 0
