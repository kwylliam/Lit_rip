import json
from copy import deepcopy

import pytest
import requests

from lit_rip import cli
from lit_rip.search import (
    SearchClient, SearchError, SearchBusyError, SearchPage, SearchResult,
    parse_mcstories_index, parse_results, parse_storiesonline_results,
    parse_sexstories_results,
    validate_search, validate_site,
)


@pytest.fixture
def response():
    return {"data": [
        {"type": "story", "title": "A &amp; B", "url": "a-and-b", "author": {"username": "Writer"},
         "series": {"meta": {"id": 123, "title": "A longer story"}}},
        {"type": "story", "title": "A different story", "url": "another-story", "authorname": "Other Writer"},
    ], "meta": {"total": 2, "pageSize": 50}}


def test_titles_authors_and_series(response):
    result = parse_results(response, "A story", 1)
    assert result.results[0].title == "A & B"
    assert result.results[0].author == "Writer"
    assert result.results[0].url == "https://www.literotica.com/s/a-and-b"
    assert result.results[0].series_url == "https://www.literotica.com/series/se/123"
    assert result.results[1].author == "Other Writer"
    assert not result.results[1].series_url
    assert not result.has_more


def test_empty_is_distinct_from_invalid_response():
    result = parse_results({"data": [], "meta": {"total": 0, "pageSize": 50}}, "Missing", 1)
    assert not result.results
    with pytest.raises(SearchError):
        parse_results({"error": "Service unavailable"}, "Missing", 1)


def test_pagination_and_unsupported_entries(response):
    response["meta"]["total"] = 101
    response["data"].append({"type": "poem"})
    response["data"].append(deepcopy(response["data"][0]))
    assert len(parse_results(response, "query", 1).results) == 2
    assert parse_results(response, "query", 2).has_more
    assert not parse_results(response, "query", 3).has_more


@pytest.mark.parametrize("url", ["https://evil.example/s/story", "https://storiesonline.net/s/1234/example"])
def test_unsafe_link_is_rejected(response, url):
    response["data"][0]["url"] = url
    with pytest.raises(SearchError):
        parse_results(response, "query", 1)


@pytest.mark.parametrize("query,page", [(None,1), ("",1), ("a",1), ("x"*201,1), ("valid",0), ("valid",True), ("valid",1001)])
def test_validation(query, page):
    with pytest.raises(ValueError):
        validate_search(query,page)


def test_query_normalization():
    assert validate_search("  A  café\nvisit ") == ("A café visit",1)


def test_site_validation():
    assert validate_site(None) == "literotica"
    assert validate_site("mcstories") == "mcstories"
    assert validate_site("sexstories") == "sexstories"
    with pytest.raises(ValueError):
        validate_site("unknown")


def test_storiesonline_result_parser():
    html = """
    <h4 id="smhead">Displaying stories 1 through 2 of 3</h4>
    <div class="storyList">
      <div class="entry"><h3 class="sname"><a href="/s/123/a-story">A Story</a> by <a href="/a/writer">Writer</a></h3></div>
      <div class="entry"><h3 class="sname"><a href="/n/456/another-story/2">Another Story</a> by <a href="/a/other">Other</a></h3></div>
    </div>
    <a href="/library/search.php?p=2">2</a>
    """
    result = parse_storiesonline_results(html, "story", 1)
    assert result.total == 3
    assert result.has_more
    assert result.results[0] == SearchResult("A Story", "Writer", "https://storiesonline.net/s/123/a-story", site="storiesonline")
    assert result.results[1].url == "https://storiesonline.net/n/456/another-story/2"


def test_mcstories_title_index_parser():
    html = """
    <table id="index">
      <tr><td><a href="../StoryOne/index.html"><cite>The Story One</cite></a></td></tr>
      <tr><td><a href="../Other/index.html"><cite>Something Else</cite></a></td></tr>
      <tr><td><a href="https://evil.example/story"><cite>Bad Link</cite></a></td></tr>
    </table>
    """
    result = parse_mcstories_index(html, "story one")
    assert result == (("The Story One", "https://mcstories.com/StoryOne/index.html"),)


def test_sexstories_keyword_parser():
    html = """
    <div class="pager"><a href="/search/1/relevance/story////">1</a><a href="/search/2/relevance/story////">2</a></div>
    <ul class="stories_list">
      <li><h4><a href="/story/123/first-story">First Story</a> by <a href="/profile1/Writer">Writer</a></h4></li>
      <li><h4><a href="/story/456/second-story">Second Story</a> by <a href="/profile2/Other">Other</a></h4></li>
    </ul>
    """
    result = parse_sexstories_results(html, "story", 1)
    assert result == SearchPage("story", 1, 2, False, (
        SearchResult("First Story", "Writer", "https://sexstories.com/story/123/first-story", site="sexstories"),
        SearchResult("Second Story", "Other", "https://sexstories.com/story/456/second-story", site="sexstories"),
    ), "sexstories")


def test_all_site_search_combines_provider_pages():
    class Provider:
        def __init__(self, site):
            self.site = site
        def search(self, query, page):
            return SearchPage(query, page, 1, False,
                              (SearchResult(self.site, "Writer", "https://example.invalid/"),), self.site)

    client = SearchClient({name: Provider(name) for name in ("literotica", "storiesonline", "mcstories", "sexstories")})
    result = client.search("story", site="all")
    assert result.site == "all"
    assert result.total == 4
    assert [item.title for item in result.results] == ["literotica", "storiesonline", "mcstories", "sexstories"]


def test_api_parameters_and_user_agent(monkeypatch, response):
    calls = []
    class Session:
        def __init__(self):
            self.headers = {}
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def mount(self, *args):
            pass
        def get(self, url, **kwargs):
            calls.append((url, kwargs, self.headers))
            class Response:
                def raise_for_status(self):
                    pass
                def json(self):
                    return response
            return Response()
    monkeypatch.setattr("lit_rip.search.requests.Session", Session)
    assert len(SearchClient().search("A café",2).results) == 2
    url, kwargs, headers = calls[0]
    assert url == "https://literotica.com/api/3/search/stories"
    assert json.loads(kwargs["params"]["params"]) == {"q":"A café", "page":2, "languages":[1]}
    assert "Mozilla" in headers["User-Agent"]
    assert kwargs["timeout"] == (5,15)


def test_network_failure_releases_lock(monkeypatch):
    def fail(*args, **kwargs):
        raise requests.ConnectionError("Offline")
    monkeypatch.setattr("lit_rip.search.requests.Session.get",fail)
    client = SearchClient()
    with pytest.raises(SearchError,match="Could not reach"):
        client.search("valid")
    assert not client.lock.locked()
    with client.lock, pytest.raises(SearchBusyError):
        client.search("valid")


def test_cli_search_json_and_page(monkeypatch, response, capsys):
    class FakeSearch:
        def search(self, query, page):
            return parse_results(response,query,page)
    monkeypatch.setattr("lit_rip.search.SearchClient", FakeSearch)
    assert cli.main(["search","A","story","--page","2","--json"]) == 0
    data=json.loads(capsys.readouterr().out)
    assert data["query"] == "A story"
    assert data["page"] == 2
    assert data["results"][0]["author"] == "Writer"
    with pytest.raises(SystemExit):
        cli.main(["search","valid","--page","0"])
