import os
import re
import tempfile
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import html2text
from bs4 import BeautifulSoup
from markdownify import markdownify

from .models import DownloadError, Story


def filename(story: Story, format: str) -> str:
    title = unicodedata.normalize("NFKC", f"{story.title} - {story.author}")
    title = re.sub(r'[^\w .-]', "_", title)
    title = re.sub(r"\s+", " ", title).strip(" .")[:120].rstrip(" .") or "story"
    return f"{title}.{format}"


def escape_heading(text: str) -> str:
    return re.sub(r"([\\`*_{}\[\]<>#!|])", r"\\\1", " ".join(text.split()))


def render(story: Story, format: str = "md") -> str:
    if format not in ("md", "txt"):
        raise ValueError("Expected md or txt")
    downloaded = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if format == "md":
        parts = [f"# {escape_heading(story.title)}", f"Author: {escape_heading(story.author)}",
                 f"Source: <{story.url}>", f"Downloaded: {downloaded}"]
    else:
        parts = [story.title, f"Author: {story.author}", f"Source: {story.url}", f"Downloaded: {downloaded}"]
    for chapter in story.chapters:
        soup = BeautifulSoup(chapter.html, "html.parser")
        for tag in soup.select("script, style, iframe, img"):
            tag.decompose()
        if not soup.get_text(strip=True):
            raise DownloadError(f"Chapter '{chapter.title}' is empty; no output was saved.")
        if format == "md":
            parts.extend([f"## {escape_heading(chapter.title)}", f"Source: <{chapter.url}>",
                          markdownify(str(soup), heading_style="ATX").strip()])
        else:
            converter = html2text.HTML2Text()
            converter.body_width = 0
            converter.ignore_emphasis = True
            converter.ignore_links = True
            converter.ignore_images = True
            converter.unicode_snob = True
            parts.extend([chapter.title, f"Source: {chapter.url}", converter.handle(str(soup)).strip()])
    return "\n\n".join(parts) + "\n"


def save(story: Story, destination: Path, *, format: str = "md", force: bool = False) -> Path:
    """Publish only a fully rendered file, without overwriting by accident."""
    content = render(story, format)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n",
                                         dir=destination.parent, prefix=".lit-rip-", delete=False) as stream:
            temp_path = Path(stream.name)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        if force:
            os.replace(temp_path, destination)
        else:
            # Unlike exists()+replace(), link() cannot overwrite a file created
            # by another process between the check and the final write.
            os.link(temp_path, destination)
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
    return destination
