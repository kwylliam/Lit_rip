# Lit Rip

A small Python app with a browser interface and command-line tools that saves public Literotica, StoriesOnline, and MCStories stories as UTF-8 Markdown or plain text. Requires Python 3.11 or newer.

## Portable Linux bundle

The release folder `dist/lit-rip-linux-x86_64-v0.2.0/` and archive `dist/lit-rip-linux-x86_64-v0.2.0.tar.gz` include Python and all required packages. You can transfer the archive to a comparable 64-bit Linux computer, extract it, and run its `launch-lit-rip.sh`. You do not need to recreate a virtual environment on the destination. Keep the entire folder together. See [PORTABLE.md](PORTABLE.md) for the transfer steps and compatibility limits.

To rebuild the archive on Linux Mint after code changes:

```sh
.venv-desktop/bin/python -m pip install "pyinstaller>=6,<7"
./scripts/build-portable-linux.sh
```

The build script refuses to overwrite an existing release. Move the previous `dist/lit-rip-linux-x86_64-v0.2.0/` folder and archive before rebuilding. Build on the oldest Linux distribution you intend to support; Linux system libraries are not bundled in full.

## Setup

From this folder:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]'
```

The virtual environment is already installed in this workspace. You can also run `.venv/bin/lit-rip` without activating it.

## Browser app

```sh
.venv/bin/lit-rip gui
```

This starts a local server and opens the app in your default browser. Paste a story or series URL, or expand **Find a Literotica story by title** and search for a title. Results show the author so you can distinguish matching names. Choose **Use story** for that submission or **Use series** for its whole series, then choose Markdown or plain text and click **Prepare download**. When the chapters are ready, click **Download Markdown** or **Download text file**. Your browser handles the save location; the app does not write browser downloads into the project's `downloads/` folder.

Keep the terminal open while using the app. Press **Ctrl+C** there to stop the server. Closing the browser tab alone does not stop it. Refreshing the page in the same tab restores the latest job while the server is still running.

By default the app chooses an available port. To choose one, or skip opening the browser automatically:

```sh
.venv/bin/lit-rip gui --port 8899
.venv/bin/lit-rip gui --no-browser
```

Open the exact address printed in the terminal. The server listens only on `127.0.0.1`, so it is local to your machine. No hosting account or new runtime dependency is required. This is a local utility, not a public web service.

Downloads run one at a time. The app keeps at most three prepared files in memory; links expire after 30 minutes or when the server stops. Save your file before then. If a download fails, the page displays the error and lets you try again.

## Linux Mint desktop launcher

Use the executable `launch-lit-rip.sh` script as your desktop launcher's command:

```text
/home/kamau/Documents/SMT/Lit_rip/launch-lit-rip.sh
```

Set the launcher name to **Lit Rip** and type to **Application** (not “Application in Terminal”), or leave **Run in terminal** unchecked. No working directory or virtual-environment activation is needed. The script opens the browser app and keeps its local server running without a terminal window.

The launcher uses `.venv-desktop`, created with Linux Mint's Python. This is separate from `.venv`, which was created inside VSCodium's Flatpak runtime. It also switches to the host automatically when started from a Flatpak editor. The desktop environment is already installed in this workspace.

To recreate it, run these commands in **Linux Mint's Terminal**, from the project folder:

```sh
python3 -m venv --without-pip .venv-desktop
python3 -m pip --python .venv-desktop/bin/python install pip -e .
```

These commands use the host's existing pip to install into the virtual environment; no system packages are modified. If `.venv-desktop` does not exist, the launcher will try `.venv` and check that the app's dependencies load before starting.

Startup output and errors go to `.lit-rip-launcher.log` in the project folder. Closing the browser tab does not stop the server. Each launch starts a new server on an available port.

If you move this project, update the command in your desktop launcher to the script's new location.

## Command-line usage

Find a story by its title or a few words from the title:

```sh
lit-rip search "The Town of Nrfle"
lit-rip search "The Town of Nrfle" --page 2
lit-rip search "The Town of Nrfle" --json
```

Search lists titles, authors, story URLs, and available series URLs. Copy the URL you want into the `download` command below. Title search currently covers only Literotica's English-language catalogue and uses its relevance ordering; titles need not be exact. If there are more matches, use **Next** in the browser or `--page` in the CLI. An unavailable search service produces an error rather than an empty result list.

Preview a story or series before downloading:

```sh
lit-rip info "https://www.literotica.com/series/se/493634882"
```

Download a series into one Markdown file in `downloads/`:

```sh
lit-rip download "https://www.literotica.com/series/se/493634882"
```

Download just the Literotica submission at a story URL, including all its pages:

```sh
lit-rip download "https://www.literotica.com/s/the-town-of-nrfle"
```

Expand a Literotica story URL to its whole series:

```sh
lit-rip download "https://www.literotica.com/s/the-town-of-nrfle" --series
```

StoriesOnline and MCStories story URLs include all chapters listed for that story. The Literotica `--series` option does not apply to these sites:

```sh
lit-rip info "https://storiesonline.net/s/16269/final-reward"
lit-rip download "https://storiesonline.net/s/16269/final-reward"
lit-rip info "https://mcstories.com/AbsoluteYes/index.html"
lit-rip download "https://mcstories.com/AToZeb/index.html"
```

Choose plain text or an exact destination:

```sh
lit-rip download "https://www.literotica.com/series/se/493634882" --format txt
lit-rip download "https://www.literotica.com/series/se/493634882" -o downloads/my-series.md
```

An explicit `.txt` output path selects plain text automatically. Use `--output-dir PATH` to change the directory for generated filenames. Existing files are kept unless you pass `--force`.

`python -m lit_rip` also works. Run `lit-rip download --help` for all options. Add `--debug` after the subcommand for detailed diagnostics.

## Current behavior

- Literotica story URLs download just that submission; Literotica series URLs and `--series` download the whole series. StoriesOnline and MCStories story URLs include their listed chapters automatically, in order.
- Literotica page links are followed within each chapter, including when only the first, next, and last pages are listed.
- Output includes title, author, source links, download time, and chapter headings. Markdown preserves paragraphs and emphasis.
- Requests use FanFicFare's in-memory cache, a randomized delay of about 1–3 seconds, a 30-second request timeout, and bounded retries with backoff for transient failures.
- An unavailable chapter, missing story body, or repeated page stops the download with an error. Files are published only after all selected chapters have been downloaded and rendered. Rerunning a failed download starts over; resumable downloads are not implemented yet.
- No browser, account credentials, or database are needed for public pages. A blocked response is reported as an error.

Downloads accept public story URLs from the three supported sites, plus Literotica series URLs. Title search covers Literotica only; use a URL for StoriesOnline and MCStories. Individual chapter files and EPUB export are future work. Non-English story subdomains are accepted but have not been checked live. Artwork, audio, and poem URLs are outside this version's scope.

## Implementation

`src/lit_rip/downloader.py` isolates FanFicFare integration and site-specific handling; `models.py` contains the data objects; `export.py` handles rendering and file writes; `cli.py` provides the commands. `web.py` serves the browser interface and runs downloads in background threads; `static/` contains the HTML, CSS, and JavaScript. `search.py` queries Literotica’s search API and validates result links and pagination.

[FanFicFare](https://github.com/JimmXinu/FanFicFare) provides series metadata, HTTP handling, and story-body extraction. Version 4.61.0 is pinned because this app uses its adapter interface. Site-specific adapters keep Literotica single-story downloads from expanding automatically, follow its current pagination, and avoid a false StoriesOnline login check caused by a public navigation link. Website changes can still require updates; the app reports extraction failures instead of deliberately saving empty chapters.

## Tests

```sh
python -m pytest -q
python -m pip check
```

Tests use synthetic, non-explicit story pages and do not contact the website. They cover URL validation across all three sites, single-story versus series scope, old and new Literotica pagination layouts, chapter ordering, missing/repeated pages, Markdown and plain-text formatting, CLI errors, protection against accidental overwrites, HTTP attachment downloads, background job errors, local browser request validation, search metadata and pagination, invalid search responses, and CLI search output.

Live smoke tests successfully downloaded the supplied two-chapter Literotica series, a public StoriesOnline story, and a public MCStories story. A 48-chapter MCStories index was checked for chapter order, and its first two chapter bodies were extracted. Downloaded files and the virtual environment are excluded by `.gitignore`.
