from dataclasses import dataclass


class DownloadError(Exception):
    """A download could not be completed safely."""


@dataclass(frozen=True)
class Chapter:
    title: str
    url: str
    html: str = ""


@dataclass(frozen=True)
class Story:
    title: str
    author: str
    url: str
    chapters: tuple[Chapter, ...]
