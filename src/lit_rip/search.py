"""Search the public catalogues of the supported story sites."""

import json
import re
import threading
from dataclasses import asdict, dataclass
from urllib.parse import parse_qs, urljoin, urlsplit

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .downloader import normalize_url
from .models import DownloadError

LITEROTICA_ENDPOINT = "https://literotica.com/api/3/search/stories"
# Backwards-compatible name used by the original Literotica-only search code.
ENDPOINT = LITEROTICA_ENDPOINT
STORIESONLINE_FORM = "https://storiesonline.net/library/searchf.php"
STORIESONLINE_ENDPOINT = "https://storiesonline.net/library/search.php"
MCSTORIES_INDEX = "https://mcstories.com/Tags/mc.html"
SEXSTORIES_SEARCH = "https://sexstories.com/search/"
SEARCH_SITES = ("all", "literotica", "storiesonline", "mcstories", "sexstories")
SITE_LABELS = {
    "all": "All sites",
    "literotica": "Literotica",
    "storiesonline": "StoriesOnline",
    "mcstories": "MCStories",
    "sexstories": "SexStories",
}
PAGE_SIZE = 20


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


def validate_site(site):
    if site is None:
        return "literotica"
    if not isinstance(site, str) or site not in SEARCH_SITES:
        raise ValueError("Choose a supported search site.")
    return site


def plain(value):
    if hasattr(value, "get_text"):
        return value.get_text(" ", strip=True)
    if not isinstance(value, str):
        return ""
    return BeautifulSoup(value, "html.parser").get_text(" ", strip=True)


def session():
    client = requests.Session()
    # These catalogues are public HTML/API pages, but a normal browser-like
    # user agent avoids an unnecessary denial from some of the sites.
    client.headers["User-Agent"] = "Mozilla/5.0 (compatible; LitRip/0.2)"
    retries = Retry(total=1, connect=1, read=0, status=1, backoff_factor=.5,
                    status_forcelist=(502, 503, 504), allowed_methods=("GET", "POST"),
                    respect_retry_after_header=False)
    client.mount("https://", HTTPAdapter(max_retries=retries))
    return client


@dataclass(frozen=True)
class SearchResult:
    title: str
    author: str
    url: str
    series_url: str = ""
    series_title: str = ""
    site: str = ""


@dataclass(frozen=True)
class SearchPage:
    query: str
    page: int
    total: int
    has_more: bool
    results: tuple[SearchResult, ...]
    site: str = "literotica"

    def as_dict(self):
        return asdict(self)


def parse_results(data, query, page):
    """Parse a Literotica API response."""
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
            results.append(SearchResult(title, author, url, series_url,
                                        plain(series_meta.get("title")), "literotica"))
        return SearchPage(query, page, total, page * size < total, tuple(results), "literotica")
    except (KeyError, TypeError, AttributeError, ValueError, DownloadError) as exc:
        raise SearchError("Literotica returned an unexpected search response. Please try again later.") from exc


def _safe_site_url(base, href, site):
    url = normalize_url(urljoin(base, href))
    expected = {
        "storiesonline": "storiesonline.net",
        "mcstories": "mcstories.com",
        "sexstories": "sexstories.com",
    }[site]
    if urlsplit(url).hostname != expected:
        raise SearchError("The search site returned an unexpected story link.")
    return url


def _title_matches(title, query):
    folded = title.casefold()
    return all(term in folded for term in re.findall(r"\w+", query.casefold(), flags=re.UNICODE))


def parse_storiesonline_results(html, query, page):
    """Parse one StoriesOnline advanced-search result page."""
    soup = BeautifulSoup(html, "html.parser")
    summary = plain(soup.select_one("#smhead"))
    match = re.search(r"Displaying stories\s+(\d+)\s+through\s+(\d+)\s+of\s+(\d+)", summary, re.I)
    if match:
        first, last, total = (int(value) for value in match.groups())
    elif re.search(r"no stories", soup.get_text(" ", strip=True), re.I):
        first = last = total = 0
    else:
        raise SearchError("StoriesOnline returned an unexpected search response. Please try again later.")

    results = []
    seen = set()
    for entry in soup.select("div.storyList div.entry"):
        title_link = entry.select_one("h3.sname a[href]")
        if title_link is None:
            continue
        try:
            url = _safe_site_url("https://storiesonline.net/", title_link["href"], "storiesonline")
        except (KeyError, SearchError, DownloadError) as exc:
            raise SearchError("StoriesOnline returned an unexpected story link.") from exc
        if url in seen:
            continue
        seen.add(url)
        author_link = entry.select_one('h3.sname a[href^="/a/"]')
        author = plain(author_link) or "Unknown author"
        results.append(SearchResult(plain(title_link), author, url, site="storiesonline"))

    linked_pages = []
    for link in soup.select("a[href]"):
        params = parse_qs(urlsplit(urljoin("https://storiesonline.net/", link["href"])).query)
        try:
            linked_pages.extend(int(value) for value in params.get("p", []))
        except ValueError:
            continue
    has_more = last < total or any(number > page for number in linked_pages)
    return SearchPage(query, page, total, has_more, tuple(results), "storiesonline")


def parse_mcstories_index(html, query):
    """Return matching MCStories title links from its public catalogue."""
    soup = BeautifulSoup(html, "html.parser")
    results = []
    seen = set()
    for row in soup.select("table#index tr"):
        link = row.select_one("a[href]")
        if link is None:
            continue
        title = plain(link.select_one("cite") or link)
        if not title or not _title_matches(title, query):
            continue
        try:
            url = _safe_site_url("https://mcstories.com/", link["href"], "mcstories")
        except (KeyError, SearchError, DownloadError) as exc:
            raise SearchError("MCStories returned an unexpected story link.") from exc
        if url in seen:
            continue
        seen.add(url)
        results.append((title, url))
    return tuple(results)


def _mc_author(html):
    soup = BeautifulSoup(html, "html.parser")
    creator = soup.select_one('meta[name="dcterms.creator"]')
    if creator and creator.get("content"):
        return plain(creator["content"])
    return plain(soup.select_one("h3.byline")) or "Unknown author"


def parse_sexstories_results(html, query, page):
    """Parse the first result page from SexStories' public keyword search."""
    soup = BeautifulSoup(html, "html.parser")
    results = []
    seen = set()
    for entry in soup.select("ul.stories_list > li"):
        title_link = entry.select_one('h4 a[href^="/story/"]')
        if title_link is None:
            continue
        try:
            url = _safe_site_url("https://sexstories.com/", title_link["href"], "sexstories")
        except (KeyError, SearchError, DownloadError) as exc:
            raise SearchError("SexStories returned an unexpected story link.") from exc
        if url in seen:
            continue
        seen.add(url)
        author = plain(entry.select_one('h4 a[href^="/profile"]')) or "Unknown author"
        results.append(SearchResult(plain(title_link), author, url, site="sexstories"))
    # The site's later result-page route currently returns an unbounded
    # catalogue instead of the requested page. Keep this provider truthful
    # and bounded until that endpoint becomes reliable.
    return SearchPage(query, page, len(results), False, tuple(results), "sexstories")


class LiteroticaSearch:
    def search(self, query, page):
        with session() as client:
            response = client.get(LITEROTICA_ENDPOINT, params={"params": json.dumps({
                "q": query, "page": page, "languages": [1],
            })}, timeout=(5, 15))
            response.raise_for_status()
            data = response.json()
        return parse_results(data, query, page)


class StoriesOnlineSearch:
    def search(self, query, page):
        with session() as client:
            form = client.get(STORIESONLINE_FORM, timeout=(5, 15))
            form.raise_for_status()
            token_match = re.search(r'name="token"[^>]*value="([^"]+)"', form.text)
            if not token_match:
                raise SearchError("StoriesOnline did not provide a search token. Please try again later.")
            response = client.post(STORIESONLINE_ENDPOINT, data={
                "token": token_match.group(1),
                "title": query,
                "cmd": "StartSearch",
                "p": page,
                "sf": "alpha",
                "so": "asc",
            }, timeout=(5, 20))
            response.raise_for_status()
            return parse_storiesonline_results(response.text, query, page)


class MCStoriesSearch:
    def __init__(self):
        self._index = None
        self._matches = {}
        self._authors = {}

    def _get_index(self, client):
        if self._index is None:
            response = client.get(MCSTORIES_INDEX, timeout=(5, 20))
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            entries = []
            seen = set()
            for row in soup.select("table#index tr"):
                link = row.select_one("a[href]")
                if link is None:
                    continue
                title = plain(link.select_one("cite") or link)
                if not title:
                    continue
                try:
                    url = _safe_site_url("https://mcstories.com/", link["href"], "mcstories")
                except (KeyError, SearchError, DownloadError) as exc:
                    raise SearchError("MCStories returned an unexpected story link.") from exc
                if url not in seen:
                    seen.add(url)
                    entries.append((title, url))
            self._index = tuple(entries)
        return self._index

    def search(self, query, page):
        with session() as client:
            index = self._get_index(client)
            if query not in self._matches:
                self._matches[query] = tuple((title, url) for title, url in index
                                              if _title_matches(title, query))
            matches = self._matches[query]
            start = (page - 1) * PAGE_SIZE
            selected = matches[start:start + PAGE_SIZE]
            results = []
            for title, url in selected:
                if url not in self._authors:
                    try:
                        response = client.get(url, timeout=(5, 15))
                        response.raise_for_status()
                        self._authors[url] = _mc_author(response.text)
                    except requests.RequestException:
                        self._authors[url] = "Unknown author"
                results.append(SearchResult(title, self._authors[url], url, site="mcstories"))
            return SearchPage(query, page, len(matches), start + len(selected) < len(matches),
                              tuple(results), "mcstories")


class SexStoriesSearch:
    def search(self, query, page):
        if page != 1:
            return SearchPage(query, page, 0, False, (), "sexstories")
        with session() as client:
            response = client.post(SEXSTORIES_SEARCH, data={
                "search": query,
                "type": "stories",
                "search_result": "Search",
            }, timeout=(5, 20))
            response.raise_for_status()
            return parse_sexstories_results(response.text, query, page)


class SearchClient:
    def __init__(self, providers=None):
        self.lock = threading.Lock()
        self.providers = providers or {
            "literotica": LiteroticaSearch(),
            "storiesonline": StoriesOnlineSearch(),
            "mcstories": MCStoriesSearch(),
            "sexstories": SexStoriesSearch(),
        }

    def search(self, query, page=1, site="literotica"):
        query, page = validate_search(query, page)
        site = validate_site(site)
        if not self.lock.acquire(blocking=False):
            raise SearchBusyError("Another search is running. Please try again in a moment.")
        try:
            if site == "all":
                pages = [self.providers[name].search(query, page) for name in SEARCH_SITES[1:]]
                results = tuple(item for result in pages for item in result.results)
                return SearchPage(query, page, sum(result.total for result in pages),
                                  any(result.has_more for result in pages), results, "all")
            return self.providers[site].search(query, page)
        except requests.RequestException as exc:
            raise SearchError(f"Could not reach {SITE_LABELS[site]} search. Please try again shortly.") from exc
        except ValueError as exc:
            raise SearchError(f"{SITE_LABELS[site]} did not return search results. Please try again later.") from exc
        finally:
            self.lock.release()
