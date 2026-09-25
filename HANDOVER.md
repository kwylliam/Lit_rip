# Lit Rip handover and change log

Last reviewed: 2026-09-24  
Repository: `https://github.com/kwylliam/Lit_rip`  
Branch/commit: `main` at `ea02d6b` (`ui improvement`), with working-tree changes after that commit

This file is the short project memory for moving between computers or coding assistants. Update it after meaningful changes, especially changes to site parsing, search, packaging, or the user interface.

## What the app is

Lit Rip is a local Python 3.11+ utility that accepts public story URLs from:

- Literotica
- StoriesOnline
- MCStories
- SexStories

It downloads story chapters through FanFicFare and produces one UTF-8 Markdown or plain-text file. It has both a CLI and a loopback-only browser UI. It does not use a database, account credentials, or a hosted service.

## What has been completed

### Initial application (`2b8489c`)

- Added the Python package, CLI, browser UI, tests, desktop launcher, and portable-bundle build scripts.
- Added URL validation for the four supported download sites.
- Added FanFicFare integration for metadata, chapter discovery, and chapter-body extraction.
- Added site-specific handling:
  - Literotica single-story downloads stay limited to the requested submission; Literotica series URLs or `--series` download the series.
  - Literotica chapter pagination is followed and repeated/missing pages fail safely.
  - StoriesOnline public pages do not get mistaken for a login wall because of the site's navigation link.
  - StoriesOnline and MCStories story URLs include their listed chapters automatically.
- Added a local SexStories adapter because FanFicFare has an adapter for the different `asexstories.com` domain, not `sexstories.com`.
  - SexStories public `/story/<id>/` and `/story/<id>/<slug>` pages are downloaded; numbered `Part`, `Chapter`, `Ch.`, and `Pt.` entries from the author's page are combined and sorted numerically. Arabic and common word numbers through twenty are recognized, including forms such as `Part Ten(1)`.
  - The adapter extracts title, author, and story content while excluding the introduction, comments, scripts, and page controls.
- Added Markdown/plain-text rendering and safe output handling.
- Added local background download jobs with progress, temporary in-memory files, expiry, and browser request checks.
- Added Literotica title search through its public search API, with author/series metadata, pagination, JSON CLI output, validation, and UI selection of a story or series.

### Portable Linux bundle and documentation (`e3b9a5d`)

- Added the portable x86_64 Linux archive workflow and generalized setup/transfer documentation.
- The portable launcher includes Python and dependencies; the destination machine still needs internet access and a browser.

### UI and release update (`ea02d6b`)

- Refined the browser UI, responsive styling, search flow, download feedback, and local desktop launcher behavior.
- Updated the app version to `0.2.2`.
- Built `dist/lit-rip-linux-x86_64-v0.2.2.tar.gz`.

### Multi-site title search (working tree)

- Added StoriesOnline title search through its public advanced-search form.
- Added MCStories title search through its public catalogue, with author lookup from matching story pages and an in-memory catalogue cache.
- Added a browser site selector for Literotica, StoriesOnline, MCStories, SexStories, or all four.
- Added CLI `--site` support and source labels in text/JSON results.
- Added parser/provider tests and refreshed the README/this handover.

### Development launcher fix (working tree)

- Source checkouts now prefer a working local virtual environment before using the Flatpak host handoff. This allows a development `.venv` created inside the editor sandbox to run without rebuilding the portable binary.
- Portable bundles still hand off to the host as before.
- This checkout now has both `.venv` for the sandbox/editor Python and `.venv-desktop` for the host Python; both are ignored by git.

### SexStories fetching (working tree)

- Added SexStories URL validation and downloader routing in `src/lit_rip/downloader.py`.
- Added synthetic parser tests and verified a live public story download through both `info` and `download`.
- Added SexStories recognition to the browser link form and updated the README/package description.
- Added SexStories keyword/title search through its public search form. It returns the site's first bounded result page; later page links currently return an unbounded catalogue response and are intentionally not exposed as pagination.

## Current architecture

- `src/lit_rip/downloader.py` — URL normalization, FanFicFare configuration, site adapters, chapter discovery/download.
- `src/lit_rip/models.py` — `Story`, `Chapter`, and `DownloadError`.
- `src/lit_rip/export.py` — Markdown/plain-text rendering and filenames.
- `src/lit_rip/search.py` — separate Literotica, StoriesOnline, MCStories, and SexStories title-search providers behind one client.
- `src/lit_rip/cli.py` — `search`, `info`, `download`, and `gui` commands.
- `src/lit_rip/web.py` — local HTTP server, background jobs, API routes, and download responses.
- `src/lit_rip/static/` — browser HTML/CSS/JavaScript.
- `Dockerfile`, `.dockerignore`, and `compose.yaml` — container image and Docker Compose deployment for a NAS or local Docker host.
- `tests/` — synthetic tests; they do not contact the live sites.

The main design boundary is that download logic is site-specific, while rendering, job management, and the browser UI are shared. A future multi-site search should follow the same separation: one search provider per site behind a common result model, then one shared UI.

## Current behavior and limitations

- The browser UI starts with `lit-rip gui`; it listens only on `127.0.0.1` by default. Container deployments use `--host 0.0.0.0` and a configurable `LIT_RIP_ALLOWED_HOSTS` allow-list.
- Only one download or one search is allowed at a time in the local server instance.
- Prepared files are kept in memory, at most three at a time, and expire after 30 minutes or when the server stops.
- Downloads use FanFicFare 4.61.0, bounded retries, a 30-second request timeout, and a randomized delay of about 1–3 seconds.
- Failed downloads are not resumable and do not publish partial files.
- Title search now covers Literotica, StoriesOnline, MCStories, and SexStories, and searches catalogue/title metadata rather than story bodies. Literotica is English-only; SexStories uses its public keyword search and currently exposes one reliable result page.
- SexStories story fetching is supported, including inferred numbered series from author pages.
- Series detection is necessarily best-effort: some titles imply a series but the site's linked author page does not expose the related entries. In that case the downloader safely keeps the selected submission as one chapter rather than guessing IDs or crawling a broad ID range.
- Non-English Literotica subdomains are accepted by URL validation but have not been live-verified.
- EPUB export, individual chapter files, artwork/audio, and a local story database are not implemented.

## Setup and verification

From a fresh checkout:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m pytest -q
.venv/bin/python -m pip check
```

Latest verification in this working tree: `90 passed`, `pip check` clean, and `git diff --check` clean. Docker was not available on the development machine, so the image build itself still needs to be run on a Docker host. The portable `v0.2.3` bundle was built before the latest URL/series fix. Do not rebuild the portable bundle until development testing is complete.

The Docker image is intended for a TrueNAS SCALE custom app. It does not write downloads to disk: prepared files are kept in memory and expire with the server. A local Docker installation can use `docker compose build && docker compose up -d`; a TrueNAS installation can use either a pushed registry image or a locally loaded image because the NAS YAML app definition references an image rather than this checkout's build context.

A registry is not mandatory: build with Compose, run `docker save -o lit-rip-0.2.3.tar lit-rip:0.2.3`, copy the archive to the NAS, run `docker load -i lit-rip-0.2.3.tar`, and configure the custom app to use the local image with a never-pull policy. A registry is preferable for repeatable updates.

Run the browser app with:

```sh
.venv/bin/lit-rip gui
```

Before adding this file, the worktree was clean. The system interpreter on the review machine did not have `pytest`, so `python3 -m pytest -q` could not run (`No module named pytest`). This is an environment/setup issue, not a reported test failure. The previous portable release remains at `dist/lit-rip-linux-x86_64-v0.2.2.tar.gz`; the new `v0.2.3` archive is built after the version change.

## Keyword-search decision context

“Keyword search” can mean three different projects:

1. Search the sites' existing title, description, tag, and category indexes.
2. Search the full text of stories currently downloaded by Lit Rip.
3. Build a crawler/index of the sites' public story catalogues and search story bodies before downloading.

The first is the sensible next increment. It can provide useful discovery without downloading every story. The third is the large project: it needs crawling, persistent storage, indexing, deduplication, rate limiting, refresh jobs, failure recovery, and ongoing maintenance as the sites change.

Live site notes checked on 2026-09-24:

- Literotica has a public [story search](https://search.literotica.com/) and a separate [tag portal](https://tags.literotica.com/). The existing internal API client is already the least expensive integration point.
- StoriesOnline exposes [category search](https://storiesonline.net/library/categories.php) and [advanced search](https://storiesonline.net/library/searchf.php). Its advanced form includes title/author/description controls and a separate story-text search area; some controls are marked as requiring Premier services.
- MCStories is an archive organized around [titles](https://mcstories.com/Titles/index.html), [authors](https://mcstories.com/Authors/index.html), and [tags/categories](https://mcstories.com/Tags/index.html), with recent additions and readers' picks. It does not present an obvious general full-text search endpoint, so discovery there is likely HTML crawling or local indexing.

Recommended product sequence:

1. Keep the provider interface and result model separate from download behavior.
2. Add contract fixtures whenever a site's search HTML/API changes.
3. Add source filters, per-site result labels, pagination, and “Use story” actions in the existing UI.
4. Separately add “search my downloaded stories” using SQLite FTS5. This gives genuinely deep full-text search with a small, dependable scope and no site-wide crawler.
5. Only build a site-wide catalogue/full-text index if metadata search plus local-library search does not meet the need.

## Good next tasks

- Install the dev dependencies and run the complete test suite on the next machine.
- Decide whether the next search project is local-library full text or a separate site-wide crawler; do not expand this collector into a full corpus index by accident.
- If continuing this feature, preserve the three providers and add live contract fixtures when a site's search HTML/API changes.
- Add live contract fixtures or recorded HTML/API responses for each search provider so website changes fail visibly in tests.
- Avoid committing generated portable bundles unless a release is intentional; update `README.md`, `PORTABLE.md`, this file, and the version together when releasing.
