import pytest
from lit_rip.downloader import Downloader, LiteroticaAdapter, SexStoriesAdapter, StoriesOnlineAdapter, make_configuration, normalize_url
from lit_rip.models import DownloadError

URL = "https://www.literotica.com/s/example-ch-01"
NEXT = "https://www.literotica.com/s/example-ch-02"
SERIES = "https://www.literotica.com/series/se/123"
STORIESONLINE = "https://storiesonline.net/s/16269/final-reward"
MCSTORIES = "https://mcstories.com/AToZeb/index.html"
SEXSTORIES = "https://sexstories.com/story/115518/backseat_sister"


def page(text, links="", nav_class="panel _pagination_example"):
    return (f'<h1>Example Chapter</h1><a class="_author__title_demo" href="/authors/example">Test Author</a>'
            f'<aside>Advertisement</aside><div class="_article__content_demo"><div><p>{text}</p></div></div>'
            f'<nav class="{nav_class}">{links}</nav><section id="comments">A comment</section>')


def sexstories_page(text="Story text."):
    return ('''<div id="story_center_panel">
        <div id="top_panel"><div class="story_info"><h2>Example Story <span class="title_link">by <a href="/profile123/TestAuthor">Test Author</a></span></h2></div></div>
        <div class="block_panel"><h2>Introduction:</h2>Summary only.</div>
        <div class="block_panel"><p>''' + text + '''</p><script>bad()</script></div>
        <div class="block_panel"><div class="count_comments">1 comment</div><form>Comment</form></div>
    </div>''')


def sexstories_series_page(title, text="Story text."):
    return ('''<div id="story_center_panel">
        <div id="top_panel"><div class="story_info"><h2>''' + title + ''' <span class="title_link">by <a href="/profile123/TestAuthor">Test Author</a></span></h2></div></div>
        <div class="block_panel"><h2>Introduction:</h2>Summary only.</div>
        <div class="block_panel"><p>''' + text + '''</p></div>
        <div class="block_panel"><div class="count_comments">0 comments</div></div>
    </div>''')


def sexstories_author_page():
    return '''<table>
        <tr><td><a href="/story/21/">Example Saga - Part 02 Second</a></td></tr>
        <tr><td><a href="/story/20/">Example Saga - Part 01 First</a></td></tr>
        <tr><td><a href="/story/99/">Another Story</a></td></tr>
    </table>'''


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
    ("www.sexstories.com/story/115518/backseat_sister?ref=1#top", SEXSTORIES),
    ("https://sexstories.com/story/111809/", "https://sexstories.com/story/111809/"),
    ("https://sexstories.com/story/83448/_quot_my_halloween_party_at_the_mortuary_quot_", "https://sexstories.com/story/83448/_quot_my_halloween_party_at_the_mortuary_quot_"),
])
def test_other_site_urls(value, expected):
    assert normalize_url(value) == expected


@pytest.mark.parametrize("value", [
    "https://storiesonline.net/authors/1234", "https://storiesonline.net/s/not-an-id/story",
    "https://mcstories.com/Titles.html", "https://mcstories.com/Tags/story.html",
    "https://mcstories.com.evil.example/AToZeb/index.html",
    "https://sexstories.com/story/not-an-id/story-title", "https://sexstories.com.evil.example/story/1/title",
])
def test_rejects_nonstory_site_urls(value):
    with pytest.raises(DownloadError):
        normalize_url(value)


def test_site_selection_and_series_scope():
    assert isinstance(Downloader(STORIESONLINE).adapter, StoriesOnlineAdapter)
    assert Downloader(MCSTORIES).adapter.__class__.__name__ == "MCStoriesComSiteAdapter"
    assert isinstance(Downloader(SEXSTORIES).adapter, SexStoriesAdapter)
    for url in (STORIESONLINE, MCSTORIES):
        with pytest.raises(DownloadError, match="whole-series option applies to Literotica"):
            Downloader(url, series=True)
    with pytest.raises(DownloadError, match="single-page submissions"):
        Downloader(SEXSTORIES, series=True)


def test_sexstories_metadata_and_body(monkeypatch):
    downloader = Downloader(SEXSTORIES)
    monkeypatch.setattr(downloader.adapter, "get_request", lambda url: sexstories_page())
    metadata = downloader.inspect()
    assert metadata.title == "Example Story"
    assert metadata.author == "Test Author"
    assert metadata.chapters[0].url == SEXSTORIES
    story = downloader.download()
    assert "Story text." in story.chapters[0].html
    assert "Summary only." not in story.chapters[0].html
    assert "bad()" not in story.chapters[0].html
    assert "Comment" not in story.chapters[0].html


def test_sexstories_detects_numbered_parts_from_author_page(monkeypatch):
    url = "https://sexstories.com/story/21/"
    downloader = Downloader(url)
    responses = {
        url: sexstories_series_page("Example Saga - Part 02 Second"),
        "https://sexstories.com/profile123/TestAuthor": sexstories_author_page(),
    }
    monkeypatch.setattr(downloader.adapter, "get_request", responses.__getitem__)
    story = downloader.inspect()
    assert [(chapter.title, chapter.url) for chapter in story.chapters] == [
        ("Example Saga - Part 01 First", "https://sexstories.com/story/20/"),
        ("Example Saga - Part 02 Second", url),
    ]


def test_sexstories_detects_pt_parts_from_author_page(monkeypatch):
    url = "https://sexstories.com/story/31/"
    downloader = Downloader(url)
    responses = {
        url: sexstories_series_page("Example Saga Pt. 02 Second"),
        "https://sexstories.com/profile123/TestAuthor": '''<table>
            <tr><td><a href="/story/30/">Example Saga Pt.01 First</a></td></tr>
            <tr><td><a href="/story/31/">Example Saga Pt. 02 Second</a></td></tr>
        </table>''',
    }
    monkeypatch.setattr(downloader.adapter, "get_request", responses.__getitem__)
    story = downloader.inspect()
    assert [chapter.title for chapter in story.chapters] == [
        "Example Saga Pt.01 First", "Example Saga Pt. 02 Second",
    ]


def test_sexstories_detects_word_numbered_parts_from_author_page(monkeypatch):
    url = "https://sexstories.com/story/41/"
    downloader = Downloader(url)
    responses = {
        url: sexstories_series_page("Example Saga Part Ten(1)"),
        "https://sexstories.com/profile123/TestAuthor": '''<table>
            <tr><td><a href="/story/40/">Example Saga Part Nine</a></td></tr>
            <tr><td><a href="/story/41/">Example Saga Part Ten(1)</a></td></tr>
        </table>''',
    }
    monkeypatch.setattr(downloader.adapter, "get_request", responses.__getitem__)
    story = downloader.inspect()
    assert [chapter.title for chapter in story.chapters] == [
        "Example Saga Part Nine", "Example Saga Part Ten(1)",
    ]


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
