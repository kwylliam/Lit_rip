import argparse
import logging
import os
import sys
from pathlib import Path

from . import __version__
from .downloader import Downloader
from .export import filename, save
from .models import DownloadError


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="lit-rip", description="Save public stories from Literotica, StoriesOnline, MCStories, or SexStories as Markdown or plain text.")
    root.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = root.add_subparsers(dest="command", required=True)
    for name, help_text in (("download", "Download all pages and save a file"),
                            ("info", "Preview the title, author, and chapter list")):
        command = commands.add_parser(name, help=help_text)
        command.add_argument("url", help="Story or series URL (use the search command to find titles)")
        command.add_argument("--series", action="store_true", help="Include the entire Literotica series containing this story")
        command.add_argument("--debug", action="store_true", help="Show diagnostic logging and tracebacks")
        if name == "download":
            command.add_argument("--format", choices=("md", "txt"), help="Output format (default: md, or inferred from --output)")
            command.add_argument("-o", "--output", type=Path, help="Exact output file path")
            command.add_argument("--output-dir", type=Path, default=Path("downloads"), help="Directory for generated filenames (default: downloads)")
            command.add_argument("--force", action="store_true", help="Replace an existing output file")
    search = commands.add_parser("search", help="Find stories by title")
    search.add_argument("query", nargs="+", help="Title or words from a title")
    search.add_argument("--page", type=int, default=1, help="Result page (default: 1)")
    search.add_argument("--site", choices=("literotica", "storiesonline", "mcstories", "sexstories", "all"),
                        default="literotica", help="Search site (default: literotica)")
    search.add_argument("--json", action="store_true", help="Print structured results")
    search.add_argument("--debug", action="store_true", help="Show diagnostic logging")
    gui = commands.add_parser("gui", help="Open the local browser app")
    gui.add_argument("--port", type=int, default=0, help="Local port (default: choose an available port)")
    gui.add_argument("--host", default=os.environ.get("LIT_RIP_HOST", "127.0.0.1"),
                     help="Bind address (default: 127.0.0.1; use 0.0.0.0 in a container)")
    gui.add_argument("--public-host", default=os.environ.get("LIT_RIP_PUBLIC_HOST"),
                     help="Host name/IP shown in the startup URL")
    gui.add_argument("--allowed-hosts", default=os.environ.get("LIT_RIP_ALLOWED_HOSTS"),
                     help="Comma-separated Host values accepted by the browser API")
    gui.add_argument("--no-browser", action="store_true", help="Print the address without opening a browser")
    gui.add_argument("--debug", action="store_true", help="Show diagnostic logging")
    return root


def main(argv: list[str] | None = None) -> int:
    argument_parser = parser()
    args = argument_parser.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.debug else logging.ERROR)
    fff_logger = logging.getLogger("fanficfare")
    fff_logger.handlers.clear()
    fff_logger.setLevel(logging.DEBUG if args.debug else logging.ERROR)
    try:
        if args.command == "search":
            from .search import SearchClient, validate_search
            try:
                query, page = validate_search(" ".join(args.query), args.page)
            except ValueError as exc:
                argument_parser.error(str(exc))
            client = SearchClient()
            result = client.search(query, page) if args.site == "literotica" else client.search(query, page, args.site)
            if args.json:
                import json
                print(json.dumps(result.as_dict(), ensure_ascii=False, indent=2))
            else:
                print(f"Search: {result.query} — page {result.page}")
                if not result.results:
                    print("No matching downloadable stories on this page. Try a different title or fewer words.")
                for index, item in enumerate(result.results, start=1):
                    source = f" [{item.site}]" if item.site and item.site != result.site else ""
                    print(f"{index}. {item.title} — {item.author}{source}\n   {item.url}")
                    if item.series_url:
                        print(f"   Series: {item.series_title or 'View series'}\n   {item.series_url}")
                if result.has_more:
                    print(f"More results available: use --page {result.page + 1}.")
            return 0
        if args.command == "gui":
            if not 0 <= args.port <= 65535:
                argument_parser.error("Port must be between 0 and 65535.")
            from .web import serve
            return serve(port=args.port, host=args.host, public_host=args.public_host,
                         allowed_hosts=args.allowed_hosts, open_browser=not args.no_browser)
        if args.command == "download":
            suffix = args.output.suffix.lower().lstrip(".") if args.output else ""
            format = args.format or (suffix if suffix in ("md", "txt") else "md")
            if suffix and suffix != format:
                argument_parser.error(f"Output extension .{suffix} does not match format {format}; use .{format}.")
            if args.output and args.output.exists() and not args.force:
                raise FileExistsError(args.output)

        downloader = Downloader(args.url, series=args.series)
        story = downloader.inspect()
        if args.command == "info":
            print(f"{story.title}\nBy {story.author}\n{story.url}\n{len(story.chapters)} chapter(s)")
            for index, chapter in enumerate(story.chapters, start=1):
                print(f"{index}. {chapter.title}\n   {chapter.url}")
            return 0

        destination = args.output or args.output_dir / filename(story, format)
        if destination.exists() and not args.force:
            raise FileExistsError(destination)
        print(f"Downloading {len(story.chapters)} chapter(s)...", file=sys.stderr)
        story = downloader.download(lambda index, total, title: print(f"[{index}/{total}] {title}", file=sys.stderr))
        save(story, destination, format=format, force=args.force)
        print(f"Saved {destination} ({len(story.chapters)} chapter(s))")
        return 0
    except FileExistsError as exc:
        print(f"Error: output already exists: {exc}. Choose another path or use --force.", file=sys.stderr)
        return 1
    except (DownloadError, OSError) as exc:
        if args.debug:
            logging.exception("Download failed")
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nCancelled; no new output was saved.", file=sys.stderr)
        return 130
