import json
from copy import deepcopy

import pytest
import requests

from lit_rip import cli
from lit_rip.search import SearchClient, SearchError, SearchBusyError, parse_results, validate_search


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
