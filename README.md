# Lit Rip

A small Python app with a browser interface and command-line tools that saves public Literotica, StoriesOnline, MCStories, and SexStories stories as UTF-8 Markdown or plain text. Requires Python 3.11 or newer.

## Portable Linux bundle

The repository includes a [portable Linux archive](dist/lit-rip-linux-x86_64-v0.2.3.tar.gz) containing Python and all required packages. Transfer the archive to a compatible 64-bit Linux computer, extract it, and run the `launch-lit-rip.sh` inside the extracted bundle. You do not need to recreate a virtual environment on the destination. Keep the extracted folder together. The `launch-lit-rip.sh` at the source-project root is for a checkout with `.venv` or `.venv-desktop`; it is not the portable launcher. See [PORTABLE.md](PORTABLE.md) for the transfer steps and compatibility limits.

To rebuild the archive after code changes on a 64-bit Linux system:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/python -m pip install "pyinstaller>=6,<7"
./scripts/build-portable-linux.sh
```

The build script refuses to overwrite an existing release. Move the previous versioned folder and archive before rebuilding. Build on the oldest Linux distribution you intend to support; Linux system libraries are not bundled in full. Set `LIT_RIP_PYTHON` if you want the script to use a different Python environment.

## Setup

From a clone of this repository:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]'
```

Installing `python3-venv` only provides the virtual-environment support; the final `pip install` step installs Lit Rip and its dependencies. You can also perform the setup without activating the environment:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e .
./launch-lit-rip.sh
```

You can also run `.venv/bin/lit-rip` without activating the environment.

## Browser app

```sh
.venv/bin/lit-rip gui
```

This starts a local server and opens the app in your default browser. Paste a story or series URL, or expand **Find by title** and choose Literotica, StoriesOnline, MCStories, SexStories, or all four sites. Results show the author and source so you can distinguish matching names. Choose **Use story** for that submission or **Use series** for a Literotica series, then choose Markdown or plain text and click **Prepare download**. When the chapters are ready, click **Download Markdown** or **Download text file**. Your browser handles the save location; the app does not write browser downloads into the project's `downloads/` folder.

Keep the terminal open while using the app. Press **Ctrl+C** there to stop the server. Closing the browser tab alone does not stop it. Refreshing the page in the same tab restores the latest job while the server is still running.

By default the app chooses an available port. To choose one, or skip opening the browser automatically:

```sh
.venv/bin/lit-rip gui --port 8899
.venv/bin/lit-rip gui --no-browser
```

Open the exact address printed in the terminal. The server listens only on `127.0.0.1`, so it is local to your machine. No hosting account or new runtime dependency is required. This is a local utility, not a public web service.

Downloads run one at a time. The app keeps at most three prepared files in memory; links expire after 30 minutes or when the server stops. Save your file before then. If a download fails, the page displays the error and lets you try again.

## Docker and TrueNAS SCALE

The repository includes a Docker image and Compose definition for running the browser app on a home server. The container listens on port `8899`; Compose publishes it as `9089` by default. Prepared files and search results stay in memory, so no volume is required.

For a local Docker host:

```sh
docker compose build
docker compose up -d
```

Then open `http://NAS_IP:9089`. Set these values in a `.env` file when needed:

```text
LIT_RIP_PORT=9089
LIT_RIP_PUBLIC_HOST=192.168.1.20
LIT_RIP_ALLOWED_HOSTS=192.168.1.20:9089,nas.local:9089
```

The Compose default allows any `Host` header because the service is normally reached through a NAS port mapping. Keep it limited to the trusted home network or set `LIT_RIP_ALLOWED_HOSTS` explicitly. The app has no user-account or login system, so do not expose it directly to the public internet.

TrueNAS SCALE can install custom OCI-container apps from its Apps interface, including through the **Install via YAML** Docker Compose editor. Build this image on a computer with Docker and push it to a registry your NAS can reach:

```sh
docker build -t REGISTRY_USER/lit-rip:0.2.3 .
docker push REGISTRY_USER/lit-rip:0.2.3
```

In the TrueNAS YAML editor, replace the `build` section with `image: REGISTRY_USER/lit-rip:0.2.3`. Publish host port `9089` to container port `8899`, and retain the read-only filesystem, temporary `/tmp`, and health check settings. The NAS does not need the source checkout after the image is pushed.

A registry is optional. To transfer the image directly, build it with Compose, export it, copy the archive to the NAS, and load it there:

```sh
docker compose build
docker save -o lit-rip-0.2.3.tar lit-rip:0.2.3
# copy lit-rip-0.2.3.tar to the NAS
docker load -i lit-rip-0.2.3.tar
```

Then use the local image `lit-rip:0.2.3` in the TrueNAS custom-app settings and choose a **Never pull** policy. This is convenient for a one-off installation; a registry is more convenient when you want to publish updated images repeatedly.

## Desktop launcher on Linux

Use the executable `launch-lit-rip.sh` script as your desktop launcher's command. Select the copy inside your cloned project; do not copy the script away from the project files.

```text
/path/to/Lit_rip/launch-lit-rip.sh
```

Set the launcher name to **Lit Rip** and type to **Application** (not “Application in Terminal”), or leave **Run in terminal** unchecked. No working directory or virtual-environment activation is needed. The script opens the browser app and keeps its local server running without a terminal window.

For a source checkout, the launcher uses `.venv` first and falls back to `.venv-desktop` for compatibility with older checkouts. When started from a Flatpak editor, it uses a working local environment if one is available and otherwise retries on the host. If the checkout is used both inside a Flatpak editor and from a desktop launcher, keep a separate host environment in `.venv-desktop`; virtual environments can be tied to the Python version visible in the environment that created them. Portable bundles always run on the host.

To create the source environment, run these commands from the project folder:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e .
```

These commands install the app into the project-local virtual environment; no system packages are modified. The launcher checks that the app's dependencies load before starting.

For a source checkout, startup output and errors go to `.lit-rip-launcher.log` in the project folder. Closing the browser tab does not stop the server. Each launch starts a new server on an available port.

If you move the project, update the command in your desktop launcher to the script's new location.

## Command-line usage

Find a story by its title or a few words from the title:

```sh
lit-rip search "The Town of Nrfle"
lit-rip search "The Town of Nrfle" --site storiesonline
lit-rip search "The Town of Nrfle" --site mcstories --page 2
lit-rip search "The Town of Nrfle" --site all --json
```

Search lists titles, authors, story URLs, source sites, and available Literotica series URLs. Copy the URL you want into the `download` command below. Literotica uses its public title-search API; StoriesOnline uses its public advanced title search; MCStories searches its public title catalogue and looks up authors on matching story pages; SexStories uses its public keyword search and returns its first result page. Searches match catalogue/title metadata rather than story bodies. An unavailable search service produces an error rather than an empty result list.

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

StoriesOnline and MCStories story URLs include all chapters listed for that story. SexStories URLs represent one single-page submission. The Literotica `--series` option does not apply to these sites:

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

- Literotica story URLs download just that submission; Literotica series URLs and `--series` download the whole series. StoriesOnline and MCStories story URLs include their listed chapters automatically, in order. SexStories URLs download one page or an inferred numbered author-page series.
- Literotica page links are followed within each chapter, including when only the first, next, and last pages are listed.
- Output includes title, author, source links, download time, and chapter headings. Markdown preserves paragraphs and emphasis.
- Requests use FanFicFare's in-memory cache, a randomized delay of about 1–3 seconds, a 30-second request timeout, and bounded retries with backoff for transient failures.
- An unavailable chapter, missing story body, or repeated page stops the download with an error. Files are published only after all selected chapters have been downloaded and rendered. Rerunning a failed download starts over; resumable downloads are not implemented yet.
- No browser, account credentials, or database are needed for public pages. A blocked response is reported as an error.

Downloads accept public story URLs from the four supported sites, plus Literotica series URLs. Each SexStories submission is one page, but numbered `Part`, `Chapter`, and `Ch.` sequences found on the author's public page are combined automatically. Title search covers all four supported sites; SexStories currently exposes one reliable result page. It is still catalogue/title search, not full-text story-body search. Individual chapter files and EPUB export are future work. Non-English story subdomains are accepted but have not been checked live. Artwork, audio, and poem URLs are outside this version's scope.

## Implementation

`src/lit_rip/downloader.py` isolates FanFicFare integration and site-specific handling; `models.py` contains the data objects; `export.py` handles rendering and file writes; `cli.py` provides the commands. `web.py` serves the browser interface and runs downloads in background threads; `static/` contains the HTML, CSS, and JavaScript. `search.py` contains separate Literotica, StoriesOnline, MCStories, and SexStories catalogue providers behind one search client. SexStories story pages use a small local adapter because FanFicFare does not support that site.

[FanFicFare](https://github.com/JimmXinu/FanFicFare) provides series metadata, HTTP handling, and story-body extraction. Version 4.61.0 is pinned because this app uses its adapter interface. Site-specific adapters keep Literotica single-story downloads from expanding automatically, follow its current pagination, and avoid a false StoriesOnline login check caused by a public navigation link. Website changes can still require updates; the app reports extraction failures instead of deliberately saving empty chapters.

## Tests

```sh
python -m pytest -q
python -m pip check
```

Tests use synthetic, non-explicit story pages and do not contact the website. They cover URL validation across all four download sites, single-story versus series scope, old and new Literotica pagination layouts, chapter ordering, missing/repeated pages, Markdown and plain-text formatting, CLI errors, protection against accidental overwrites, HTTP attachment downloads, background job errors, local browser request validation, search metadata and pagination, invalid search responses, and CLI search output.

Downloaded files and virtual environments are excluded by `.gitignore`.
