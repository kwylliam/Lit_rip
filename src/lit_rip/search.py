"""Search Literotica's public catalogue without downloading story bodies."""

import json
import threading
from dataclasses import asdict, dataclass
from urllib.parse import urljoin, urlsplit

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .downloader import normalize_url
from .models import DownloadError

ENDPOINT = "https://literotica.com/api/3/search/stories"


class SearchError(DownloadError):
    pass


class SearchBusyError(SearchError):
    pass


def validate_search(query, page=1):
    if not isinstance(query, str):
        raise ValueError("Enter a story title.")
    query = " ".join(query.split())
    if not 2 <= len(query) <= 200:
        raise ValueError("Enter a title between 2 and 200 characters.")
    if type(page) is not int or not 1 <= page <= 1000:
        raise ValueError("Search page must be between 1 and 1000.")
    return query, page


def plain(value):
    if not isinstance(value, str):
        return ""
    return BeautifulSoup(value, "html.parser").get_text(" ", strip=True)


@dataclass(frozen=True)
class SearchResult:
    title: str
    author: str
    url: str
    series_url: str = ""
    series_title: str = ""


@dataclass(frozen=True)
class SearchPage:
    query: str
    page: int
    total: int
    has_more: bool
    results: tuple[SearchResult, ...]

    def as_dict(self):
        return asdict(self)


def parse_results(data, query, page):
    try:
        entries = data["data"]
        meta = data["meta"]
        total, size = meta["total"], meta["pageSize"]
        if not isinstance(entries, list) or type(total) is not int or total < 0 or type(size) is not int or size <= 0:
            raise ValueError("Unexpected search response")
        results = []
        seen = set()
        for item in entries:
            if not isinstance(item, dict):
                raise ValueError("Invalid search entry")
            if item.get("type") != "story":
                continue
            title = plain(item.get("title"))
            slug = item.get("url")
            if not title or not isinstance(slug, str) or not slug:
                raise ValueError("Missing story title or link")
            url = normalize_url(urljoin("https://www.literotica.com/s/", slug))
            if urlsplit(url).hostname != "www.literotica.com":
                raise ValueError("Unexpected search result host")
            if url in seen:
                continue
            seen.add(url)
            author_data = item.get("author") or {}
            author = plain(item.get("authorname")) or plain(author_data.get("username")) or "Unknown author"
            series = item.get("series") or {}
            series_meta = series.get("meta") or {}
            series_id = str(series_meta.get("id", ""))
            series_url = ""
            if series_id.isascii() and series_id.isdigit() and int(series_id) > 0:
                series_url = f"https://www.literotica.com/series/se/{series_id}"
            results.append(SearchResult(title, author, url, series_url, plain(series_meta.get("title"))))
        return SearchPage(query, page, total, page * size < total, tuple(results))
    except (KeyError, TypeError, AttributeError, ValueError, DownloadError) as exc:
        raise SearchError("Literotica returned an unexpected search response. Please try again later.") from exc


class SearchClient:
    def __init__(self):
        self.lock = threading.Lock()

    def search(self, query, page=1):
        query, page = validate_search(query, page)
        if not self.lock.acquire(blocking=False):
            raise SearchBusyError("Another search is running. Please try again in a moment.")
        try:
            with requests.Session() as session:
                # The search service closes connections from the default requests UA.
                session.headers["User-Agent"] = "Mozilla/5.0 (compatible; LitRip/0.1)"
                retries = Retry(total=1, connect=1, read=0, status=1, backoff_factor=.5,
                                status_forcelist=(502, 503, 504), allowed_methods=("GET",),
                                respect_retry_after_header=False)
                session.mount("https://", HTTPAdapter(max_retries=retries))
                response = session.get(ENDPOINT, params={"params": json.dumps({
                    "q": query, "page": page, "languages": [1],
                })}, timeout=(5, 15))
                response.raise_for_status()
                data = response.json()
            return parse_results(data, query, page)
        except requests.RequestException as exc:
            raise SearchError("Could not reach Literotica search. Please try again shortly.") from exc
        except ValueError as exc:
            raise SearchError("Literotica did not return search results. Please try again later.") from exc
        finally:
            self.lock.release()
