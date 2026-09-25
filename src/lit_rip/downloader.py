"""Keep the FanFicFare dependency and site-specific details in one module."""

import re
from collections.abc import Callable
from html import unescape
from importlib.resources import files
from urllib.parse import parse_qs, urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup
from fanficfare import exceptions as fff_exceptions
from fanficfare.adapters.adapter_literotica import LANG_LIST, LiteroticaSiteAdapter
from fanficfare.adapters.adapter_storiesonlinenet import StoriesOnlineNetAdapter
from fanficfare.adapters.adapter_mcstoriescom import MCStoriesComSiteAdapter
from fanficfare.adapters.base_adapter import BaseSiteAdapter
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
    elif host in ("sexstories.com", "www.sexstories.com"):
        host = "sexstories.com"
        path = path.rstrip("/")
        if re.fullmatch(r"/story/[0-9]+", path):
            # Author pages link to the short form, which only works with a
            # trailing slash on the site.
            path += "/"
        elif not re.fullmatch(r"/story/[0-9]+/[A-Za-z0-9._%+~\-][A-Za-z0-9._%+~\-]*", path):
            raise DownloadError("Expected a SexStories /story/12345/story-title URL.")
    else:
        raise DownloadError("Supported sites: Literotica, StoriesOnline, MCStories, and SexStories.")
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


class SexStoriesAdapter(BaseSiteAdapter):
    """Read SexStories pages and infer numbered parts from the author page."""

    _SERIES_PATTERNS = (
        re.compile(r"^(?P<base>.+?)\s*[-–—]?\s*Part\s+(?P<number>[0-9]+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty)\s*(?:\([0-9]+\))?(?=$|\s|[:._-])", re.IGNORECASE),
        re.compile(r"^(?P<base>.+?)\s*[-–—]\s*Chapter\s+(?P<number>[0-9]+)\b", re.IGNORECASE),
        re.compile(r"^(?P<base>.+?)\s*[-–—]?\s*Pt\.?\s*(?P<number>[0-9]+)\b", re.IGNORECASE),
        re.compile(r"^(?P<base>.+?)\s+Ch\.\s*(?P<number>[0-9]+)\b", re.IGNORECASE),
    )

    _NUMBER_WORDS = {
        "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
        "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
        "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
        "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
        "nineteen": 19, "twenty": 20,
    }

    @staticmethod
    def getSiteDomain():
        return "sexstories.com"

    @classmethod
    def getAcceptDomains(cls):
        return ["sexstories.com", "www.sexstories.com"]

    @classmethod
    def getSiteExampleURLs(cls):
        return "https://sexstories.com/story/12345/story-title"

    def getSiteURLPattern(self):
        return r"https?://(www\.)?sexstories\.com/story/[0-9]+(?:/[A-Za-z0-9._%+~\-][A-Za-z0-9._%+~\-]*)?/?"

    def __init__(self, config: Configuration, url: str):
        super().__init__(config, url)
        self.story.setMetadata("siteabbrev", "sexstories")
        self.story.setMetadata("storyId", self.parsedUrl.path.split("/")[2])
        self._setURL(url)

    @staticmethod
    def _story_content(soup: BeautifulSoup):
        center = soup.select_one("#story_center_panel")
        if center is None:
            return None
        for panel in center.select(".block_panel"):
            if panel.select_one("#stories_comments, .count_comments, form"):
                continue
            heading = panel.find("h2")
            if heading and "introduction" in heading.get_text(" ", strip=True).lower():
                continue
            if panel.get_text(strip=True):
                return panel
        return None

    @classmethod
    def _series_key(cls, title: str):
        for pattern in cls._SERIES_PATTERNS:
            match = pattern.match(title.strip())
            if match:
                return (re.sub(r"\s+", " ", match.group("base").strip()).casefold(), pattern.pattern)
        return None

    @classmethod
    def _series_number(cls, title: str, key):
        for pattern in cls._SERIES_PATTERNS:
            if pattern.pattern == key[1]:
                match = pattern.match(title.strip())
                if not match:
                    return None
                token = match.group("number").casefold()
                return int(token) if token.isdigit() else cls._NUMBER_WORDS[token]
        return None

    def _add_author_page_chapters(self, author_url: str, title: str):
        key = self._series_key(title)
        if key is None:
            self.add_chapter(title, self.url)
            return

        try:
            profile = self.make_soup(self.get_request(author_url))
            candidates = []
            for link in profile.select('a[href^="/story/"]'):
                chapter_title = link.get_text(" ", strip=True)
                chapter_url = urljoin(author_url, link.get("href", ""))
                if self._series_key(chapter_title) != key:
                    continue
                number = self._series_number(chapter_title, key)
                if number is not None:
                    candidates.append((number, chapter_title, chapter_url))
            candidates.sort(key=lambda item: (item[0], item[1].casefold()))
            seen = set()
            for _, chapter_title, chapter_url in candidates:
                if chapter_url not in seen:
                    seen.add(chapter_url)
                    self.add_chapter(chapter_title, chapter_url)
        except Exception as exc:
            logger.debug("Could not inspect SexStories author page %s: %s", author_url, exc)

        if not self.chapterUrls:
            self.add_chapter(title, self.url)

    def extractChapterUrlsAndMetadata(self):
        if not (self.is_adult or self.getConfig("is_adult")):
            raise fff_exceptions.AdultCheckRequired(self.url)

        data = self.get_request(self.url)
        soup = self.make_soup(data)
        heading = soup.select_one("#story_center_panel .story_info h2")
        author = heading.select_one(".title_link a") if heading else None
        content = self._story_content(soup)
        if heading is None or author is None or content is None:
            raise DownloadError("Story metadata or story text was not found. The page may be unavailable or its layout may have changed.")

        author_name = author.get_text(" ", strip=True)
        title_link = heading.select_one(".title_link")
        if title_link:
            title_link.extract()
        title = heading.get_text(" ", strip=True)
        if not title or not author_name:
            raise DownloadError("Story title or author was not found. The page may be unavailable or its layout may have changed.")
        self.story.setMetadata("title", title)
        self.story.setMetadata("author", author_name)
        author_url = urljoin(self.url, author.get("href", ""))
        self.story.setMetadata("authorUrl", author_url)
        self._add_author_page_chapters(author_url, title)

    def getChapterText(self, url):
        data = self.get_request(url)
        soup = self.make_soup(data)
        content = self._story_content(soup)
        if content is None:
            raise DownloadError("No story text was found. The page may be unavailable or its layout may have changed.")
        for node in content.select("script, style"):
            node.decompose()
        return self.utf8FromSoup(url, content)


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
        elif host == "sexstories.com":
            if series:
                raise DownloadError("The whole-series option applies to Literotica URLs. SexStories story URLs are single-page submissions.")
            self.adapter = SexStoriesAdapter(make_configuration(host), self.url)
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
