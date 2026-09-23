"""Keep the FanFicFare dependency and site-specific details in one module."""

import re
from collections.abc import Callable
from html import unescape
from importlib.resources import files
from urllib.parse import parse_qs, urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup
from fanficfare.adapters.adapter_literotica import LANG_LIST, LiteroticaSiteAdapter
from fanficfare.adapters.adapter_storiesonlinenet import StoriesOnlineNetAdapter
from fanficfare.adapters.adapter_mcstoriescom import MCStoriesComSiteAdapter
from fanficfare.configurable import Configuration

from .models import Chapter, DownloadError, Story


def normalize_url(value: str) -> str:
    value = value.strip()
    if "://" not in value:
        value = "https://" + value
    try:
        parts = urlsplit(value)
        host = (parts.hostname or "").lower()
        if parts.port not in (None, 80, 443) or parts.username or parts.password:
            raise ValueError("Unexpected credentials or port")
    except ValueError as exc:
        raise DownloadError("Invalid URL.") from exc
    if parts.scheme not in ("http", "https"):
        raise DownloadError("Please supply a story URL from a supported site.")
    path = parts.path
    if host == "literotica.com":
        host = "www.literotica.com"
    if host in {f"{lang}.literotica.com" for lang in LANG_LIST}:
        path = path.removeprefix("/beta").rstrip("/")
        if not re.fullmatch(r"/(?:s/[A-Za-z0-9_-]+|series/se/[A-Za-z0-9_-]+)", path):
            raise DownloadError("Expected a Literotica /s/story-name or /series/se/series-id URL.")
    elif host in ("storiesonline.net", "www.storiesonline.net"):
        host = "storiesonline.net"
        path = path.rstrip("/")
        if not re.fullmatch(r"/[sn]/[0-9]+(?::[0-9]+)?(?:/[A-Za-z0-9_-]+(?:/[0-9]+)?)?", path):
            raise DownloadError("Expected a StoriesOnline /s/1234/story-title or /n/1234/story-title URL.")
    elif host in ("mcstories.com", "www.mcstories.com"):
        host = "mcstories.com"
        path = path.rstrip("/")
        if not re.fullmatch(r"/[A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+\.html)?", path) or path.split("/")[1].lower() in {"titles", "authors", "tags", "readerspicks"}:
            raise DownloadError("Expected an MCStories /StoryTitle/ or /StoryTitle/index.html URL.")
        if path.count("/") == 1:
            path += "/"
    else:
        raise DownloadError("Supported sites: Literotica, StoriesOnline, and MCStories.")
    return urlunsplit(("https", host, path, "", ""))


def make_configuration(site: str = "literotica.com") -> Configuration:
    config = Configuration([site], "html")
    config.read_string(files("fanficfare").joinpath("defaults.ini").read_text(encoding="utf-8"))
    config.read_string("""
[overrides]
is_adult: true
include_images: false
never_make_cover: true
description_in_chapter: false
clean_chapter_titles: false
use_cloudscraper: false
use_browser_cache: false
slow_down_sleep_time: 2
connect_timeout: 30
continue_on_chapter_error: false
""")
    return config


class LiteroticaAdapter(LiteroticaSiteAdapter):
    """Upstream series metadata, with single-story scope and strict pagination."""

    def __init__(self, config: Configuration, url: str, whole_series: bool = False):
        self.whole_series = whole_series or "/series/se/" in url
        super().__init__(config, url)

    def extractChapterUrlsAndMetadata(self):
        if self.whole_series:
            return super().extractChapterUrlsAndMetadata()

        # Upstream automatically expands story URLs into their entire series.
        # Read just the requested submission's metadata for our default scope.
        raw, redirected = self.get_request_redirected(self.url)
        self._setURL(normalize_url(redirected))
        soup = self.make_soup(raw)
        title = soup.find("h1")
        author = soup.select_one('a[class^="_author__title"], a.y_eU')
        if not title or not author or not title.get_text(strip=True):
            raise DownloadError("Story title or author was not found. The page may be unavailable or its layout has changed.")
        self.story.setMetadata("title", title.get_text(" ", strip=True))
        self.story.setMetadata("author", author.get_text(" ", strip=True))
        self.story.setMetadata("authorUrl", urljoin(self.url, author.get("href", "")))
        self.add_chapter(title.get_text(" ", strip=True), self.url)

    def getPageText(self, raw_page, url):
        body = super().getPageText(raw_page, url)
        if not BeautifulSoup(body, "html.parser").get_text(strip=True):
            raise DownloadError(f"No story text found at {url}. No output was saved.")
        return body

    def getChapterText(self, url):
        # FanFicFare 4.61's selector requires the obsolete 'clearfix' class.
        # Follow numeric page links, checking each page before joining it.
        base = normalize_url(url)
        pending = {1}
        completed: set[int] = set()
        bodies: dict[int, str] = {}
        fingerprints: set[str] = set()
        while pending:
            page = min(pending)
            pending.remove(page)
            page_url = base if page == 1 else f"{base}?page={page}"
            raw = self.get_request(page_url)
            soup = self.make_soup(raw)
            body = self.getPageText(raw, page_url)
            fingerprint = BeautifulSoup(body, "html.parser").get_text(" ", strip=True)
            if fingerprint in fingerprints:
                raise DownloadError(f"Page {page} repeated earlier text; refusing an incomplete download.")
            fingerprints.add(fingerprint)
            bodies[page] = body
            completed.add(page)

            # Inspect all same-story page links, including 'next' and 'last'.
            # This also handles pagination bars with gaps in displayed numbers.
            for link in soup.select("a[href]"):
                target = urljoin(page_url, link["href"])
                parts = urlsplit(target)
                page_values = parse_qs(parts.query).get("page")
                if not page_values:
                    continue
                try:
                    if normalize_url(target) != base:
                        continue
                    last = int(page_values[0])
                except (DownloadError, ValueError):
                    continue
                if not 1 <= last <= 1000:
                    raise DownloadError("Unexpected page count; refusing to download an unbounded number of pages.")
                pending.update(set(range(1, last + 1)) - completed)
            if len(completed) > 1000:
                raise DownloadError("Too many pages in this chapter.")
        return "\n".join(bodies[number] for number in sorted(bodies))


class StoriesOnlineAdapter(StoriesOnlineNetAdapter):
    """Avoid treating the public site's navigation link as a login wall."""

    def needToLoginCheck(self, data):
        # FanFicFare 4.61 treats any occurrence of "Log In" as a denial,
        # including the navigation link on publicly readable stories.
        return any(marker in data for marker in (
            "Free Registration", "Invalid Password!", "Invalid User Name!",
            "Access to unlinked chapters requires", "Log in to Storiesonline",
            "WLPC log in System",
        ))


class Downloader:
    def __init__(self, url: str, *, series: bool = False):
        self.url = normalize_url(url)
        host = urlsplit(self.url).hostname
        if host and host.endswith("literotica.com"):
            self.adapter = LiteroticaAdapter(make_configuration("literotica.com"), self.url, series)
        elif host == "storiesonline.net":
            if series:
                raise DownloadError("The whole-series option applies to Literotica URLs. StoriesOnline story URLs already include their chapters.")
            self.adapter = StoriesOnlineAdapter(make_configuration(host), self.url)
        elif host == "mcstories.com":
            if series:
                raise DownloadError("The whole-series option applies to Literotica URLs. MCStories story URLs already include their chapters.")
            self.adapter = MCStoriesComSiteAdapter(make_configuration(host), self.url)
        else:
            raise DownloadError("Unsupported story URL.")
        self._metadata: Story | None = None

    def inspect(self) -> Story:
        if self._metadata:
            return self._metadata
        try:
            self.adapter.getStoryMetadataOnly(get_cover=False)
            metadata = self.adapter.story
            chapters = []
            seen = set()
            for entry in self.adapter.get_chapters():
                url = normalize_url(urljoin(self.adapter.url, entry["url"]))
                if url in seen:
                    continue
                seen.add(url)
                chapters.append(Chapter(unescape(entry["title"]), url))
            if not chapters:
                raise DownloadError("No chapters were found; the series may be unavailable or its layout has changed.")
            self._metadata = Story(
                unescape(metadata.getMetadata("title") or "Untitled"),
                unescape(metadata.getMetadata("author") or "Unknown author"),
                normalize_url(self.adapter.url),
                tuple(chapters),
            )
            return self._metadata
        except DownloadError:
            raise
        except Exception as exc:
            raise DownloadError(f"Could not read story information: {exc}") from exc

    def download(self, progress: Callable[[int, int, str], None] | None = None) -> Story:
        story = self.inspect()
        chapters = []
        for index, chapter in enumerate(story.chapters, start=1):
            if progress:
                progress(index, len(story.chapters), chapter.title)
            try:
                body = self.adapter.getChapterText(chapter.url)
                if not BeautifulSoup(body, "html.parser").get_text(strip=True):
                    raise DownloadError("No story text was found; the page may require sign-in or its layout may have changed.")
            except Exception as exc:
                raise DownloadError(f"Chapter {index}/{len(story.chapters)} failed ({chapter.url}): {exc}") from exc
            chapters.append(Chapter(chapter.title, chapter.url, body))
        return Story(story.title, story.author, story.url, tuple(chapters))
