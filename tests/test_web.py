import json
import threading
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from lit_rip import cli
from lit_rip.models import Chapter, DownloadError, Story
from lit_rip.web import BrowserServer, Jobs

URL = "https://www.literotica.com/s/example"
STORY = Story("A café visit", "An Author", URL, (Chapter("One", URL, "<p>A quiet <em>morning</em>.</p>"),))


class FakeDownloader:
    def __init__(self, url, *, series=False):
        self.url = url
        self.series = series
    def inspect(self):
        return STORY
    def download(self, progress):
        progress(1, 1, "One")
        return STORY


@pytest.fixture
def server():
    with BrowserServer(jobs=Jobs(FakeDownloader)) as instance:
        thread = threading.Thread(target=instance.serve_forever, daemon=True)
        thread.start()
        yield instance
        instance.shutdown()
        thread.join(timeout=2)


def request(server, path, *, data=None, headers=None):
    default_headers = {}
    if data is not None:
        default_headers.update({"Content-Type": "application/json", "X-Lit-Rip-Token": server.token})
    default_headers.update(headers or {})
    req = Request(server.origin + path, data=json.dumps(data).encode() if data is not None else None, headers=default_headers)
    try:
        response = urlopen(req, timeout=3)
    except HTTPError as error:
        response = error
    with response:
        return response.status, response.headers, response.read()


def start(server, format="md"):
    code, _, body = request(server, "/api/jobs", data={"url": URL, "series": False, "format": format})
    assert code == 202
    return json.loads(body)["id"]


def wait(server, id):
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        code, _, body = request(server, f"/api/jobs/{id}")
        assert code == 200
        data = json.loads(body)
        if data["state"] != "working":
            return data
        time.sleep(.01)
    pytest.fail("Job did not finish")


@pytest.mark.parametrize("format", ["md", "txt"])
def test_browser_download_response(server, format):
    id = start(server, format)
    status = wait(server, id)
    assert status["state"] == "ready"
    assert status["completed"] == status["total"] == 1
    code, headers, content = request(server, f"/api/jobs/{id}/file")
    assert code == 200
    assert headers["Content-Disposition"].startswith("attachment;")
    assert "caf%C3%A9" in headers["Content-Disposition"]
    assert headers["Content-Length"] == str(len(content))
    expected = "A quiet *morning*." if format == "md" else "A quiet morning."
    assert expected in content.decode("utf-8")
    assert headers["Cache-Control"] == "no-store"


@pytest.mark.parametrize("url", [
    "https://storiesonline.net/s/16269/final-reward",
    "https://mcstories.com/AToZeb/index.html",
])
def test_browser_accepts_other_supported_story_urls(server, url):
    code, _, body = request(server, "/api/jobs", data={"url": url, "series": False, "format": "md"})
    assert code == 202
    job = wait(server, json.loads(body)["id"])
    assert job["state"] == "ready"


def test_assets_and_no_filesystem_serving(server):
    code, headers, body = request(server, "/")
    assert code == 200
    assert server.token.encode() in body
    assert b"__TOKEN__" not in body
    assert "frame-ancestors 'none'" in headers["Content-Security-Policy"]
    for asset in ("/app.js", "/app.css"):
        assert request(server, asset)[0] == 200
    for path in ("/../pyproject.toml", "/downloads/private.md", "/api/jobs/missing"):
        assert request(server, path)[0] == 404


@pytest.mark.parametrize("data", [[], {}, {"url": URL, "format": "exe", "series": False},
    {"url": URL, "format": "md", "series": "yes"},
    {"url": "https://example.com/", "format": "md", "series": False}])
def test_invalid_requests_are_rejected(server, data):
    assert request(server, "/api/jobs", data=data)[0] == 400
    assert not server.jobs.items


@pytest.mark.parametrize("headers", [{"X-Lit-Rip-Token": "bad"}, {"Origin": "https://example.com"},
    {"Host": "evil.example"}, {"Sec-Fetch-Site": "cross-site"}])
def test_cross_site_requests_are_rejected(server, headers):
    assert request(server, "/api/jobs", data={"url": URL, "series": False, "format": "md"}, headers=headers)[0] == 403
    assert not server.jobs.items


def test_failed_job_has_no_download(server):
    class Broken(FakeDownloader):
        def download(self, progress):
            raise DownloadError("Chapter unavailable")
    server.jobs.downloader_factory = Broken
    id = start(server)
    status = wait(server, id)
    assert status["state"] == "error"
    assert status["message"] == "Chapter unavailable"
    assert request(server, f"/api/jobs/{id}/file")[0] == 409


def test_busy_and_incomplete_download(server):
    gate = threading.Event()
    class Slow(FakeDownloader):
        def download(self, progress):
            gate.wait(timeout=3)
            return STORY
    server.jobs.downloader_factory = Slow
    id = start(server)
    try:
        assert request(server, f"/api/jobs/{id}/file")[0] == 409
        assert request(server, "/api/jobs", data={"url": URL, "format": "txt", "series": True})[0] == 409
    finally:
        gate.set()
    assert wait(server, id)["state"] == "ready"


def test_expired_results_are_removed(server):
    id = start(server)
    wait(server, id)
    with server.jobs.lock:
        server.jobs.items[id].updated -= 1801
    assert request(server, f"/api/jobs/{id}")[0] == 404


def test_gui_command(monkeypatch):
    calls = []
    monkeypatch.setattr("lit_rip.web.serve", lambda **kwargs: calls.append(kwargs) or 0)
    assert cli.main(["gui", "--port", "8899", "--no-browser"]) == 0
    assert calls == [{"port": 8899, "host": "127.0.0.1", "public_host": None,
                      "allowed_hosts": None, "open_browser": False}]
    with pytest.raises(SystemExit):
        cli.main(["gui", "--port", "70000"])


def test_network_server_accepts_configured_host():
    with BrowserServer(host="0.0.0.0", public_host="nas.example",
                       allowed_hosts="nas.example:8899") as instance:
        assert instance.public_host == "nas.example"
        assert instance.host_allowed("nas.example:8899")
        assert not instance.host_allowed("evil.example:8899")


def test_search_endpoint(server):
    from lit_rip.search import SearchPage, SearchResult
    class FakeSearch:
        def search(self, query, page):
            assert query == "A café"
            assert page == 2
            return SearchPage(query, page, 60, False, (SearchResult("A café", "Writer", URL),))
    server.search_client = FakeSearch()
    code, _, body = request(server, "/api/search", data={"query": "A café", "page": 2})
    assert code == 200
    data = json.loads(body)
    assert data["results"][0]["author"] == "Writer"
    assert data["page"] == 2
    assert not server.jobs.items


def test_search_validation_and_token(server):
    assert request(server, "/api/search", data={"query": ""})[0] == 400
    assert request(server, "/api/search", data={"query": "valid", "page": "bad"})[0] == 400
    assert request(server, "/api/search", data={"query": "valid"}, headers={"X-Lit-Rip-Token": "bad"})[0] == 403


def test_search_failure_is_not_an_empty_result(server):
    from lit_rip.search import SearchError
    class BrokenSearch:
        def search(self, query, page):
            raise SearchError("Search unavailable")
    server.search_client = BrokenSearch()
    code, _, body = request(server, "/api/search", data={"query": "A title"})
    assert code == 502
    assert json.loads(body)["error"] == "Search unavailable"
