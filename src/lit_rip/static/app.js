"use strict";
const form = document.querySelector("#download-form");
const fields = document.querySelector("#fields");
const feedback = document.querySelector("#feedback");
const progress = document.querySelector("#progress");
const save = document.querySelector("#save-file");
const retry = document.querySelector("#retry");
const note = document.querySelector("#download-note");
const label = document.querySelector("#status-label");
const title = document.querySelector("#story-title");
const author = document.querySelector("#story-author");
const message = document.querySelector("#message");
const prepare = document.querySelector("#prepare");
const token = document.querySelector('meta[name="lit-rip-token"]').content;
const urlField = document.querySelector("#url");
const seriesField = document.querySelector("#series");
function updateSeriesOption() {
  const value = urlField.value.trim();
  let host = "";
  try { host = new URL(value.includes("://") ? value : `https://${value}`).hostname.toLowerCase(); }
  catch (_) { /* Let the server validate incomplete URLs. */ }
  const otherSite = ["storiesonline.net", "www.storiesonline.net", "mcstories.com", "www.mcstories.com"].includes(host);
  if (otherSite) seriesField.checked = false;
  seriesField.disabled = otherSite;
  document.querySelector("#series-help").textContent = otherSite
    ? "All chapters of this story are included automatically."
    : "If this Literotica story belongs to a series, get every chapter.";
}
urlField.addEventListener("input", updateSeriesOption);
updateSeriesOption();
let jobId = null;
let downloadBusy = false;
let searchBusy = false;
const searchFields = document.querySelector("#search-fields");
const resultFields = document.querySelector("#search-result-fields");
function updateSearchControls() {
  searchFields.disabled = searchBusy || downloadBusy;
  resultFields.disabled = searchBusy || downloadBusy;
}

function remember(id) {
  try {
    if (id) sessionStorage.setItem("lit-rip-job", id);
    else sessionStorage.removeItem("lit-rip-job");
  } catch (_) { /* Storage may be unavailable in private browser settings. */ }
}
function busy(value) {
  downloadBusy = value;
  updateSearchControls();
  fields.disabled = value;
  prepare.textContent = value ? "Preparing your file…" : "Prepare download ↓";
}
function showError(text) {
  feedback.hidden = false;
  feedback.classList.add("error");
  label.textContent = "COULDN’T FINISH";
  message.textContent = text;
  progress.hidden = true;
  save.hidden = true;
  note.hidden = true;
}
async function request(url, options = {}, timeout = 15000) {
  let response;
  try {
    response = await fetch(url, {...options, signal: AbortSignal.timeout(timeout)});
  } catch (_) {
    throw new Error("Can’t reach Lit Rip. Check that the app is still running in your terminal.");
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
  busy(true);
  try {
    while (jobId) {
      const job = await request(`/api/jobs/${jobId}`);
      feedback.hidden = false;
      title.textContent = job.title;
      author.textContent = job.author ? `By ${job.author}` : "";
      message.textContent = job.message;
      label.textContent = job.state === "ready" ? "READY FOR YOUR SHELF" : "COLLECTING YOUR STORY";
      progress.hidden = job.state !== "working";
      if (job.total) {
        progress.max = job.total;
        progress.value = job.completed;
      } else {
        progress.removeAttribute("value");
      }
      if (job.state === "ready") {
        save.href = `/api/jobs/${jobId}/file`;
        save.download = job.name;
        save.textContent = `Download ${job.format === "md" ? "Markdown" : "text file"} ↓`;
        save.hidden = false;
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
  // Read the form before disabling the fields (disabled inputs are omitted).
  const body = JSON.stringify({url: document.querySelector("#url").value.trim(),
    series: document.querySelector("#series").checked,
    format: new FormData(form).get("format")});
  busy(true);
  feedback.hidden = false;
  feedback.classList.remove("error");
  title.textContent = "";
  author.textContent = "";
  label.textContent = "LET’S GET YOUR STORY";
  message.textContent = "Finding the story and chapters…";
  save.hidden = true;
  note.hidden = true;
  retry.hidden = true;
  progress.hidden = false;
  progress.removeAttribute("value");
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
  document.querySelector("#url").value = wholeSeries ? item.series_url : item.url;
  document.querySelector("#series").checked = wholeSeries;
  updateSeriesOption();
  document.querySelector("#url-help").textContent = `Selected: ${wholeSeries ? (item.series_title || item.title) : item.title} — ${item.author}`;
  document.querySelector("#title-search").open = false;
  document.querySelector("#url").focus();
  document.querySelector("#download-form").scrollIntoView({block: "nearest"});
}
function resultElement(item) {
  const row = document.createElement("li");
  row.className = "search-result";
  const heading = document.createElement("h3");
  heading.textContent = item.title;
  const byline = document.createElement("p");
  byline.textContent = `By ${item.author}`;
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
  row.append(heading, byline, actions);
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
      ? `${result.results.length} matching stories on page ${result.page} for “${result.query}”.`
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
