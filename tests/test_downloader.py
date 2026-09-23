import pytest
from lit_rip.downloader import Downloader, LiteroticaAdapter, StoriesOnlineAdapter, make_configuration, normalize_url
from lit_rip.models import DownloadError

URL = "https://www.literotica.com/s/example-ch-01"
NEXT = "https://www.literotica.com/s/example-ch-02"
SERIES = "https://www.literotica.com/series/se/123"
STORIESONLINE = "https://storiesonline.net/s/16269/final-reward"
MCSTORIES = "https://mcstories.com/AToZeb/index.html"


def page(text, links="", nav_class="panel _pagination_example"):
    return (f'<h1>Example Chapter</h1><a class="_author__title_demo" href="/authors/example">Test Author</a>'
            f'<aside>Advertisement</aside><div class="_article__content_demo"><div><p>{text}</p></div></div>'
            f'<nav class="{nav_class}">{links}</nav><section id="comments">A comment</section>')


@pytest.mark.parametrize("value", [URL + "?page=3#top", URL.replace("https://www.", ""), URL + "/"])
def test_url_normalization(value):
    assert normalize_url(value) == URL


@pytest.mark.parametrize("value", ["some title", "https://literotica.com.evil.example/s/a",
    "https://evil.example/s/a", "file:///etc/passwd", "https://user:pass@literotica.com/s/a",
    "https://literotica.com/authors/someone", "https://literotica.com:9000/s/a"])
def test_rejects_unsupported_urls(value):
    with pytest.raises(DownloadError):
        normalize_url(value)


@pytest.mark.parametrize("value,expected", [
    ("storiesonline.net/s/16269/final-reward?foo=1", STORIESONLINE),
    ("https://www.storiesonline.net/n/1234/example/2", "https://storiesonline.net/n/1234/example/2"),
    ("mcstories.com/AToZeb/", "https://mcstories.com/AToZeb/"),
    ("https://www.mcstories.com/AToZeb/index.html#top", MCSTORIES),
])
def test_other_site_urls(value, expected):
    assert normalize_url(value) == expected


@pytest.mark.parametrize("value", [
    "https://storiesonline.net/authors/1234", "https://storiesonline.net/s/not-an-id/story",
    "https://mcstories.com/Titles.html", "https://mcstories.com/Tags/story.html",
    "https://mcstories.com.evil.example/AToZeb/index.html",
])
def test_rejects_nonstory_site_urls(value):
    with pytest.raises(DownloadError):
        normalize_url(value)


def test_site_selection_and_series_scope():
    assert isinstance(Downloader(STORIESONLINE).adapter, StoriesOnlineAdapter)
    assert Downloader(MCSTORIES).adapter.__class__.__name__ == "MCStoriesComSiteAdapter"
    for url in (STORIESONLINE, MCSTORIES):
        with pytest.raises(DownloadError, match="whole-series option applies to Literotica"):
            Downloader(url, series=True)


def test_storiesonline_public_login_navigation_is_not_a_wall():
    adapter = Downloader(STORIESONLINE).adapter
    assert not adapter.needToLoginCheck('<nav><a href="/login">Log In</a></nav><article>Story</article>')
    assert adapter.needToLoginCheck("Invalid Password!")


@pytest.mark.parametrize("nav_class", ["panel clearfix _pagination_old", "panel _pagination_new"])
def test_all_pages_in_order(monkeypatch, nav_class):
    adapter = LiteroticaAdapter(make_configuration(), URL)
    responses = {
        URL: page("First page.", '<a href="?page=3">Last</a><a href="?page=2">Next</a>', nav_class),
        URL + "?page=2": page("Second page.", '<a href="?page=3">Next</a>'),
        URL + "?page=3": page("Third page."),
    }
    calls = []
    def fetch(url):
        calls.append(url)
        return responses[url]
    monkeypatch.setattr(adapter, "get_request", fetch)
    result = adapter.getChapterText(URL)
    assert result.index("First page.") < result.index("Second page.") < result.index("Third page.")
    assert calls == list(responses)
    assert "Advertisement" not in result
    assert "A comment" not in result


def test_discovers_pages_from_later_page(monkeypatch):
    adapter = LiteroticaAdapter(make_configuration(), URL)
    responses = {URL: page("First", '<a href="?page=2">Next</a>'),
        URL + "?page=2": page("Second", '<a href="?page=3">Next</a>'), URL + "?page=3": page("Third")}
    monkeypatch.setattr(adapter, "get_request", responses.__getitem__)
    assert "Third" in adapter.getChapterText(URL)


@pytest.mark.parametrize("second", ["<h1>Access denied</h1>", page("First")])
def test_missing_or_repeated_page_is_an_error(monkeypatch, second):
    adapter = LiteroticaAdapter(make_configuration(), URL)
    responses = {URL: page("First", '<a href="?page=2">Next</a>'), URL + "?page=2": second}
    monkeypatch.setattr(adapter, "get_request", responses.__getitem__)
    with pytest.raises(DownloadError):
        adapter.getChapterText(URL)


def test_single_chapter_does_not_expand_series(monkeypatch):
    downloader = Downloader(URL)
    raw = page("A quiet walk.") + f'<a class="_files__link_test" href="{SERIES}">Series</a>'
    monkeypatch.setattr(downloader.adapter, "get_request_redirected", lambda url: (raw, url))
    metadata = downloader.inspect()
    assert metadata.title == "Example Chapter"
    assert metadata.author == "Test Author"
    assert [chapter.url for chapter in metadata.chapters] == [URL]


def test_series_scope_and_order(monkeypatch):
    from fanficfare.adapters.adapter_literotica import LiteroticaSiteAdapter
    def metadata(adapter):
        adapter._setURL(SERIES)
        adapter.story.setMetadata("title", "Example Series")
        adapter.story.setMetadata("author", "Test Author")
        adapter.add_chapter("Chapter One", URL)
        adapter.add_chapter("Chapter Two", NEXT)
    monkeypatch.setattr(LiteroticaSiteAdapter, "extractChapterUrlsAndMetadata", metadata)
    for url, whole in ((URL, True), (SERIES, False)):
        downloader = Downloader(url, series=whole)
        story = downloader.inspect()
        assert [chapter.url for chapter in story.chapters] == [URL, NEXT]
        assert story.url == SERIES


def test_chapter_failure_reports_position(monkeypatch):
    downloader = Downloader(URL)
    monkeypatch.setattr(downloader.adapter, "get_request_redirected", lambda url: (page("Text"), url))
    monkeypatch.setattr(downloader.adapter, "get_request", lambda url: "<h1>Blocked</h1>")
    with pytest.raises(DownloadError, match="Chapter 1/1 failed"):
        downloader.download()


def test_mcstories_chapter_order_and_empty_body(monkeypatch):
    downloader = Downloader(MCSTORIES)
    first = "https://mcstories.com/AToZeb/AToZeb1.html"
    second = "https://mcstories.com/AToZeb/AToZeb2.html"
    def metadata():
        downloader.adapter.story.setMetadata("title", "Example")
        downloader.adapter.story.setMetadata("author", "Writer")
        downloader.adapter.add_chapter("One", first)
        downloader.adapter.add_chapter("Two", second)
    monkeypatch.setattr(downloader.adapter, "extractChapterUrlsAndMetadata", metadata)
    story = downloader.inspect()
    assert [chapter.url for chapter in story.chapters] == [first, second]
    monkeypatch.setattr(downloader.adapter, "getChapterText", lambda url: "<p>First body</p>" if url == first else "")
    with pytest.raises(DownloadError, match="Chapter 2/2 failed"):
        downloader.download()
