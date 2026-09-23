from pathlib import Path
import pytest
from lit_rip import cli
from lit_rip.export import filename, render, save
from lit_rip.models import Chapter, DownloadError, Story

URL = "https://www.literotica.com/s/example"


@pytest.fixture
def story():
    return Story("A café visit", "An Author", URL, (
        Chapter("Chapter One", URL, "<p>Hello <em>world</em>.</p><p>Another paragraph.</p><script>bad()</script>"),
    ))


def test_markdown_preserves_paragraphs_and_emphasis(story):
    result = render(story)
    assert "# A café visit" in result
    assert "Hello *world*.\n\nAnother paragraph." in result
    assert f"Source: <{URL}>" in result
    assert "bad()" not in result


def test_plain_text_keeps_inline_words_together(story):
    result = render(story, "txt")
    assert "Hello world." in result
    assert "*world*" not in result
    assert "Another paragraph." in result


def test_no_overwrite_and_explicit_replacement(tmp_path, story):
    target = tmp_path / "nested" / "story.md"
    target.parent.mkdir()
    target.write_text("existing", encoding="utf-8")
    with pytest.raises(FileExistsError):
        save(story, target)
    assert target.read_text() == "existing"
    assert not list(target.parent.glob(".lit-rip-*"))
    save(story, target, force=True)
    assert "A café visit" in target.read_text(encoding="utf-8")


def test_empty_chapter_cannot_replace_file(tmp_path):
    story = Story("Empty", "Author", URL, (Chapter("Chapter", URL, "<p></p>"),))
    target = tmp_path / "story.md"
    target.write_text("original")
    with pytest.raises(DownloadError):
        save(story, target, force=True)
    assert target.read_text() == "original"


def test_filename_cannot_escape_directory():
    story = Story("../../strange/title", "someone", URL, ())
    assert Path(filename(story, "md")).name == filename(story, "md")


def test_cli_download_and_info(monkeypatch, tmp_path, story, capsys):
    class FakeDownloader:
        def __init__(self, url, *, series=False):
            assert url == URL
        def inspect(self):
            return story
        def download(self, progress):
            progress(1, 1, story.title)
            return story
    monkeypatch.setattr(cli, "Downloader", FakeDownloader)
    assert cli.main(["info", URL]) == 0
    assert "1 chapter(s)" in capsys.readouterr().out
    target = tmp_path / "output.txt"
    assert cli.main(["download", URL, "-o", str(target)]) == 0
    assert "Hello world." in target.read_text()
    assert cli.main(["download", URL, "-o", str(target)]) == 1
    assert "already exists" in capsys.readouterr().err


def test_failed_download_leaves_no_file(monkeypatch, tmp_path, story):
    class BrokenDownloader:
        def __init__(self, *args, **kwargs):
            pass
        def inspect(self):
            return story
        def download(self, progress):
            raise DownloadError("Chapter 2 failed")
    monkeypatch.setattr(cli, "Downloader", BrokenDownloader)
    target = tmp_path / "output.md"
    assert cli.main(["download", URL, "-o", str(target)]) == 1
    assert not target.exists()


def test_format_mismatch_fails_before_network(tmp_path):
    with pytest.raises(SystemExit) as error:
        cli.main(["download", URL, "--format", "md", "-o", str(tmp_path / "story.txt")])
    assert error.value.code == 2
