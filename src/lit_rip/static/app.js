"use strict";

const form = document.querySelector("#download-form");
const fields = document.querySelector("#fields");
const feedback = document.querySelector("#feedback");
const progressWrap = document.querySelector("#progress-wrap");
const progress = document.querySelector("#progress");
const progressCount = document.querySelector("#progress-count");
const progressPercent = document.querySelector("#progress-percent");
const save = document.querySelector("#save-file");
const retry = document.querySelector("#retry");
const startOver = document.querySelector("#start-over");
const note = document.querySelector("#download-note");
const label = document.querySelector("#status-label");
const stateIcon = document.querySelector("#state-icon");
const title = document.querySelector("#story-title");
const author = document.querySelector("#story-author");
const message = document.querySelector("#message");
const prepare = document.querySelector("#prepare");
const token = document.querySelector('meta[name="lit-rip-token"]').content;
const urlField = document.querySelector("#url");
const seriesField = document.querySelector("#series");
const singleStoryField = document.querySelector("#single-story");
const sourceStatus = document.querySelector("#source-status");
const scopeGroup = document.querySelector("#scope-group");
const scopeNote = document.querySelector("#scope-note");
const linkPanel = document.querySelector("#link-panel");
const titleSearch = document.querySelector("#title-search");
const linkMode = document.querySelector("#link-mode");
const titleMode = document.querySelector("#title-mode");
const modeTabs = [linkMode, titleMode];

let jobId = null;
let downloadBusy = false;
let searchBusy = false;

function setMode(mode) {
  const searching = mode === "search";
  linkPanel.hidden = searching;
  titleSearch.hidden = !searching;
  linkMode.classList.toggle("is-active", !searching);
  titleMode.classList.toggle("is-active", searching);
  linkMode.setAttribute("aria-selected", String(!searching));
  titleMode.setAttribute("aria-selected", String(searching));
  if (searching) document.querySelector("#query").focus();
}

linkMode.addEventListener("click", () => setMode("link"));
titleMode.addEventListener("click", () => setMode("search"));

function updateSeriesOption() {
  const value = urlField.value.trim();
  let host = "";
  try { host = new URL(value.includes("://") ? value : `https://${value}`).hostname.toLowerCase(); }
  catch (_) { /* Let the server validate incomplete URLs. */ }

  const literotica = host === "literotica.com" || host.endsWith(".literotica.com");
  const storiesOnline = host === "storiesonline.net" || host === "www.storiesonline.net";
  const mcStories = host === "mcstories.com" || host === "www.mcstories.com";

  sourceStatus.hidden = !(literotica || storiesOnline || mcStories);
  sourceStatus.textContent = literotica ? "✓ Literotica" : storiesOnline ? "✓ StoriesOnline" : mcStories ? "✓ MCStories" : "";
  scopeGroup.hidden = !literotica;
  scopeNote.hidden = !(storiesOnline || mcStories);
  seriesField.disabled = !literotica;
  if (!literotica) {
    seriesField.checked = false;
    singleStoryField.checked = true;
  }
}

urlField.addEventListener("input", updateSeriesOption);
singleStoryField.addEventListener("change", () => { if (singleStoryField.checked) seriesField.checked = false; });
seriesField.addEventListener("change", () => { singleStoryField.checked = !seriesField.checked; });
updateSeriesOption();

function updateSearchControls() {
  const disabled = searchBusy || downloadBusy;
  document.querySelector("#search-fields").disabled = disabled;
  document.querySelector("#search-result-fields").disabled = disabled;
  modeTabs.forEach(tab => { tab.disabled = disabled; });
}

function remember(id) {
  try {
    if (id) sessionStorage.setItem("lit-rip-job", id);
    else sessionStorage.removeItem("lit-rip-job");
  } catch (_) { /* Storage may be unavailable in private browser settings. */ }
}

function setState(state) {
  feedback.dataset.state = state;
  stateIcon.textContent = state === "ready" ? "✓" : state === "error" ? "!" : "…";
}

function busy(value) {
  downloadBusy = value;
  updateSearchControls();
  fields.disabled = value;
  prepare.innerHTML = value ? "Preparing your file…" : 'Prepare download <span aria-hidden="true">↗</span>';
}

function showError(text) {
  feedback.hidden = false;
  form.hidden = true;
  setState("error");
  label.textContent = "Couldn’t prepare the file";
  message.textContent = text;
  progressWrap.hidden = true;
  progress.hidden = true;
  save.hidden = true;
  retry.hidden = true;
  startOver.hidden = false;
  note.hidden = true;
}

function updateProgress(job) {
  progressWrap.hidden = false;
  progress.hidden = false;
  if (job.total) {
    progress.max = job.total;
    progress.value = job.completed;
    progressCount.textContent = `${job.completed} of ${job.total} chapters`;
    progressPercent.textContent = `${Math.round((job.completed / job.total) * 100)}%`;
  } else {
    progress.removeAttribute("value");
    progressCount.textContent = "Preparing chapters…";
    progressPercent.textContent = "";
  }
}

async function request(url, options = {}, timeout = 15000) {
  let response;
  try {
    response = await fetch(url, {...options, signal: AbortSignal.timeout(timeout)});
  } catch (_) {
    throw new Error("Can’t reach Lit Rip. Check that the app is still running.");
  }
  const data = await response.json();
  if (!response.ok) {
    const error = new Error(data.error || "The request failed. Please try again.");
    error.status = response.status;
    throw error;
  }
  return data;
}

async function poll() {
  retry.hidden = true;
  feedback.classList.remove("error");
  feedback.hidden = false;
  form.hidden = true;
  setState("working");
  busy(true);
  try {
    while (jobId) {
      const job = await request(`/api/jobs/${jobId}`);
      title.textContent = job.title;
      author.textContent = job.author ? `By ${job.author}` : "";
      message.textContent = job.message;
      label.textContent = job.state === "ready" ? "Ready to download" : "Preparing your file";
      if (job.state === "working") updateProgress(job);
      if (job.state === "ready") {
        setState("ready");
        progressWrap.hidden = true;
        progress.hidden = true;
        save.href = `/api/jobs/${jobId}/file`;
        save.download = job.name;
        save.textContent = `Download ${job.format === "md" ? "Markdown" : "text file"}`;
        save.hidden = false;
        startOver.hidden = false;
        note.hidden = false;
        busy(false);
        return;
      }
      if (job.state === "error") {
        showError(job.message);
        busy(false);
        remember(null);
        jobId = null;
        return;
      }
      await new Promise(resolve => setTimeout(resolve, 800));
    }
  } catch (error) {
    showError(error.message);
    if (error.status === 404 || error.status === 403) {
      remember(null);
      jobId = null;
      busy(false);
    } else {
      retry.hidden = false;
    }
  }
}

form.addEventListener("submit", async event => {
  event.preventDefault();
  const body = JSON.stringify({url: urlField.value.trim(), series: seriesField.checked,
    format: new FormData(form).get("format")});
  busy(true);
  form.hidden = true;
  feedback.hidden = false;
  setState("working");
  title.textContent = "";
  author.textContent = "";
  label.textContent = "Preparing your file";
  message.textContent = "Finding the story and chapters…";
  progressWrap.hidden = false;
  progress.hidden = false;
  progress.removeAttribute("value");
  progressCount.textContent = "Preparing chapters…";
  progressPercent.textContent = "";
  save.hidden = true;
  note.hidden = true;
  retry.hidden = true;
  startOver.hidden = true;
  try {
    const job = await request("/api/jobs", {method: "POST", body,
      headers: {"Content-Type": "application/json", "X-Lit-Rip-Token": token}});
    jobId = job.id;
    remember(jobId);
    await poll();
  } catch (error) {
    showError(error.message);
    busy(false);
  }
});

retry.addEventListener("click", poll);
startOver.addEventListener("click", () => {
  jobId = null;
  remember(null);
  busy(false);
  form.hidden = false;
  feedback.hidden = true;
  setState("idle");
  save.hidden = true;
  retry.hidden = true;
  startOver.hidden = true;
  note.hidden = true;
  progressWrap.hidden = true;
  progress.hidden = true;
  setMode("link");
  urlField.value = "";
  document.querySelector("#url-help").textContent = "Paste a link from Literotica, StoriesOnline, or MCStories.";
  seriesField.checked = false;
  singleStoryField.checked = true;
  updateSeriesOption();
  urlField.focus();
});

try { jobId = sessionStorage.getItem("lit-rip-job"); } catch (_) { /* Optional. */ }
if (jobId) poll();

const searchForm = document.querySelector("#search-form");
const searchStatus = document.querySelector("#search-status");
const searchResults = document.querySelector("#search-results");
const searchPagination = document.querySelector("#search-pagination");
const previousPage = document.querySelector("#search-prev");
const nextPage = document.querySelector("#search-next");
let searchQuery = "";
let searchPage = 1;

function useResult(item, wholeSeries) {
  urlField.value = wholeSeries ? item.series_url : item.url;
  seriesField.checked = wholeSeries;
  singleStoryField.checked = !wholeSeries;
  updateSeriesOption();
  document.querySelector("#url-help").textContent = `Selected: ${wholeSeries ? (item.series_title || item.title) : item.title} — ${item.author}`;
  setMode("link");
  urlField.focus();
  linkPanel.scrollIntoView({block: "nearest"});
}

function resultElement(item) {
  const row = document.createElement("li");
  row.className = "search-result";
  const heading = document.createElement("h3");
  heading.textContent = item.title;
  const byline = document.createElement("p");
  byline.textContent = `By ${item.author}`;
  row.append(heading, byline);
  if (item.series_url) {
    const series = document.createElement("p");
    series.className = "result-series";
    series.textContent = `Series: ${item.series_title || "Available"}`;
    row.append(series);
  }
  const actions = document.createElement("div");
  actions.className = "result-actions";
  const choose = document.createElement("button");
  choose.type = "button";
  choose.className = "secondary";
  choose.textContent = "Use story";
  choose.addEventListener("click", () => useResult(item, false));
  actions.append(choose);
  if (item.series_url) {
    const seriesButton = document.createElement("button");
    seriesButton.type = "button";
    seriesButton.className = "secondary";
    seriesButton.textContent = "Use series";
    seriesButton.addEventListener("click", () => useResult(item, true));
    actions.append(seriesButton);
  }
  const source = document.createElement("a");
  source.href = item.url;
  source.target = "_blank";
  source.rel = "noopener noreferrer";
  source.textContent = "View on site ↗";
  actions.append(source);
  row.append(actions);
  return row;
}

async function search(query, pageNumber = 1) {
  if (searchBusy || downloadBusy) return;
  searchBusy = true;
  updateSearchControls();
  searchStatus.classList.remove("error");
  searchStatus.textContent = "Searching Literotica…";
  try {
    const result = await request("/api/search", {method: "POST",
      headers: {"Content-Type": "application/json", "X-Lit-Rip-Token": token},
      body: JSON.stringify({query, page: pageNumber})}, 60000);
    searchQuery = result.query;
    searchPage = result.page;
    searchResults.replaceChildren(...result.results.map(resultElement));
    searchStatus.textContent = result.results.length
      ? `${result.results.length} matching stories · page ${result.page}`
      : "No matching stories on this page. Try fewer words or another title.";
    searchPagination.hidden = result.page === 1 && !result.has_more;
    previousPage.disabled = result.page <= 1;
    nextPage.disabled = !result.has_more;
    document.querySelector("#search-page").textContent = `Page ${result.page}`;
  } catch (error) {
    searchStatus.textContent = error.message;
    searchStatus.classList.add("error");
    searchResults.replaceChildren();
    searchPagination.hidden = true;
  } finally {
    searchBusy = false;
    updateSearchControls();
  }
}

searchForm.addEventListener("submit", event => {
  event.preventDefault();
  search(document.querySelector("#query").value.trim());
});
previousPage.addEventListener("click", () => search(searchQuery, searchPage - 1));
nextPage.addEventListener("click", () => search(searchQuery, searchPage + 1));
