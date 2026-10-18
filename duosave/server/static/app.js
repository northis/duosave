/* Duosave frontend: search + review, RU/EN, light/dark theme. */
"use strict";

const I18N = {
  ru: {
    nav_cards: "Карточки", nav_review: "Проверка", nav_admin: "Обслуживание",
    search_ph: "Поиск по оригиналу и переводу…",
    all: "Все",
    sort_new: "Сначала новые", sort_old: "Сначала старые",
    mode_text: "Текст", mode_hybrid: "Гибрид", mode_semantic: "Смысл",
    sem_stale: "Семантический индекс отстаёт на {n} — запустите duosave index",
    sem_unavailable: "Семантический поиск недоступен: {reason}",
    empty: "Ничего не найдено",
    more: "Показать ещё",
    loading: "Загрузка…",
    load_error: "Не удалось загрузить",
    review_empty: "Очередь пуста",
    cards: "карточек", sources: "источники", source: "источник",
    accept: "Принять", reject: "Отклонить", edit: "Изменить", save: "Сохранить", cancel: "Отмена",
    status_auto: "авто", status_review: "проверка", status_manual: "подтверждено",
    review_queue: "На проверке:", no_guess: "Пары не найдено — посмотрите скриншот",
    lang_unknown: "— язык не определён", lang_label: "Язык карточки",
    path: "Путь:",
    upload_btn: "Загрузить картинку", upload_hint: "Перетащите картинку сюда или выберите файл",
    upload_busy: "Распознаю…", upload_card: "карточка: {original} — {translation}",
    upload_dup: "дубликат", upload_review: "в проверку", upload_open: "открыть",
    upload_err_csrf: "Запрос отклонён — обновите страницу",
    upload_err_too_large: "файл больше {mb} МБ", upload_err_too_large_no_limit: "файл слишком большой",
    upload_err_not_an_image: "это не картинка",
    upload_err_busy: "база занята — попробуйте ещё раз", upload_err_generic: "не удалось загрузить",
    share_title: "Итог шары",
    share_counts: "Новых карточек: {new} · В проверке: {review} · Не карточка: {skip} · Дубликатов: {dup}",
    share_open_card: "Открыть карточку", share_to_review: "В «Проверку»",
    share_to_search: "В поиск", share_redirect: "Открываю главную…",
    share_sw_stale: "Приложение не обновилось, закройте и откройте его заново",
    share_empty: "В шаре не было картинок",
    build_title: "Duosave {v}, коммит {sha}", build_dirty: "локальные изменения",
    req_timeout: "Сервер не ответил за {s} с: запрос, скорее всего, не дошёл до него",
  },
  en: {
    nav_cards: "Cards", nav_review: "Review", nav_admin: "Maintenance",
    search_ph: "Search by original and translation…",
    all: "All",
    sort_new: "Newest first", sort_old: "Oldest first",
    mode_text: "Text", mode_hybrid: "Hybrid", mode_semantic: "Semantic",
    sem_stale: "Semantic index is {n} cards behind — run duosave index",
    sem_unavailable: "Semantic search unavailable: {reason}",
    empty: "Nothing found",
    more: "Show more",
    loading: "Loading…",
    load_error: "Failed to load",
    review_empty: "Queue is empty",
    cards: "cards", sources: "sources", source: "source",
    accept: "Accept", reject: "Reject", edit: "Edit", save: "Save", cancel: "Cancel",
    status_auto: "auto", status_review: "review", status_manual: "verified",
    review_queue: "To review:", no_guess: "No pair found — check the screenshot",
    lang_unknown: "— language unknown", lang_label: "Card language",
    path: "Path:",
    upload_btn: "Upload an image", upload_hint: "Drop an image here or choose a file",
    upload_busy: "Recognizing…", upload_card: "card: {original} — {translation}",
    upload_dup: "duplicate", upload_review: "to review", upload_open: "open",
    upload_err_csrf: "Request rejected — reload the page",
    upload_err_too_large: "file is larger than {mb} MB", upload_err_too_large_no_limit: "file is too large",
    upload_err_not_an_image: "this is not an image",
    upload_err_busy: "database is busy — try again", upload_err_generic: "upload failed",
    share_title: "Share result",
    share_counts: "New cards: {new} · To review: {review} · Not a card: {skip} · Duplicates: {dup}",
    share_open_card: "Open the card", share_to_review: "To Review",
    share_to_search: "To search", share_redirect: "Opening the main page…",
    share_sw_stale: "The app has not updated — close and reopen it",
    share_empty: "No images in the share",
    build_title: "Duosave {v}, commit {sha}", build_dirty: "local changes",
    req_timeout: "No answer from the server in {s} s: the request most likely never reached it",
  },
};
let lang = localStorage.getItem("duosave_lang") || "ru";
function t(key) { return (I18N[lang] || I18N.ru)[key] || key; }
function applyI18n() {
  document.documentElement.lang = lang;
  document.querySelectorAll("[data-i18n]").forEach((el) => { el.textContent = t(el.dataset.i18n); });
  document.querySelectorAll("[data-i18n-ph]").forEach((el) => { el.placeholder = t(el.dataset.i18nPh); });
  document.querySelectorAll("[data-i18n-title]").forEach((el) => { el.title = t(el.dataset.i18nTitle); });
  document.querySelectorAll(".lang a").forEach((a) => a.classList.toggle("active", a.dataset.lang === lang));
}
document.querySelectorAll(".lang a").forEach((a) =>
  a.addEventListener("click", (e) => {
    e.preventDefault();
    lang = a.dataset.lang;
    localStorage.setItem("duosave_lang", lang);
    applyI18n();
    renderBuildInfo();
    if (document.getElementById("cards")) render(true);
    else if (document.getElementById("review-list")) loadReview(true);
    else if (document.getElementById("admin") && typeof renderAdmin === "function") renderAdmin();
    else if (document.getElementById("share")) renderShare();
  }));

/* theme */
const THEME_COLORS = { light: "#f6f1e8", dark: "#16171b" }; /* style.css --bg and the meta theme-color */
/* The page's own head script applied the stored (or system) theme before the first paint; it
   is the source of truth here so the two can never disagree. */
let theme = document.documentElement.dataset.theme
  || localStorage.getItem("duosave_theme")
  || (window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
function applyTheme() {
  document.documentElement.dataset.theme = theme;
  const btn = document.getElementById("theme-btn");
  if (btn) btn.textContent = theme === "dark" ? "☀️" : "🌙";
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.content = THEME_COLORS[theme] || THEME_COLORS.light;
}
function bindTheme() {
  const btn = document.getElementById("theme-btn");
  if (!btn) return;
  btn.addEventListener("click", () => {
    theme = theme === "dark" ? "light" : "dark";
    localStorage.setItem("duosave_theme", theme);
    applyTheme();
  });
}

/* The boot screen (the page's own first frame, see the head of every page) goes away with the
   first render. The watchdog covers a request that never answers: it must not hide the page. */
const BOOT_MAX_MS = 6000;
function bootDone() {
  const boot = document.getElementById("boot");
  if (!boot) return;
  boot.classList.add("boot-done");
  setTimeout(() => boot.remove(), 300); /* after the fade */
}
setTimeout(bootDone, BOOT_MAX_MS);

/* version + commit badge in the sticky header (two links: repo and commit) */
let buildInfo = null;
function renderBuildInfo() {
  const badge = document.getElementById("build-badge");
  if (!badge || !buildInfo) return;
  const version = document.getElementById("build-version");
  const commit = document.getElementById("build-commit");
  const title = t("build_title").replace("{v}", buildInfo.version).replace("{sha}", buildInfo.commit || "—")
    + (buildInfo.commit_date ? " · " + String(buildInfo.commit_date).slice(0, 10) : "")
    + (buildInfo.dirty ? " · " + t("build_dirty") : "");
  if (version) {
    version.textContent = "v" + buildInfo.version;
    version.title = title;
    /* the version badge opens the release tag; the commit badge keeps the commit page */
    if (buildInfo.repo_url) version.href = buildInfo.tag_url || (buildInfo.repo_url + "/tree/v" + buildInfo.version);
  }
  if (commit) {
    if (buildInfo.short) {
      commit.textContent = "· " + buildInfo.short + (buildInfo.dirty ? "*" : "");
      commit.href = buildInfo.commit_url;
      commit.title = title;
      commit.hidden = false;
    } else {
      commit.hidden = true;
    }
  }
  badge.hidden = false;
}
async function loadBuildInfo() {
  try { buildInfo = await fetchJson("/api/version"); } catch (err) { return; }
  renderBuildInfo();
}

/* The maintenance link exists only when the page is open on the local admin listener. */
async function loadSession() {
  try {
    const session = await fetchJson("/api/session");
    const link = document.getElementById("nav-admin");
    if (link && session.local_admin) link.hidden = false;
  } catch (err) { /* no admin on this listener */ }
}

/* The share target posts a navigation to /share: the worker rewrites it into API calls. */
function registerServiceWorker() {
  if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js");
}

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
/* data/media/drops/x.jpg -> /media/drops/x.jpg ; screens/a.png -> /src/screens/a.png */
function mediaUrl(p) { return "/media/" + String(p || "").replace(/^data[\\/]media[\\/]/, "").replace(/\\/g, "/"); }
function sourceUrl(p) { return "/src/" + String(p || "").replace(/\\/g, "/"); }
function fmtDate(ts) {
  if (!ts) return "";
  const d = new Date(ts * 1000);
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

function setStatus(text, busy) {
  const el = document.getElementById("stats-line");
  if (!el) return;
  el.textContent = text;
  el.classList.toggle("busy", !!busy);
}
function setBusy(container, busy) { if (container) container.classList.toggle("loading", !!busy); }
function hide(el) { if (el) el.style.display = "none"; }
function show(el) { if (el) el.style.display = "block"; }

/* Profiling: every API call is logged to the console with its total time, the server share
   (Server-Timing) and the server request id (#N in the `http start/done #N` server log).
   A request still pending after PERF_SLOW_MS is reported while it waits, so a hang shows up. */
const PERF_SLOW_MS = 5000;
function perfLog(level, ...args) {
  (console[level] || console.log).call(console, "[duosave]", ...args);
}
function serverTiming(res) {
  const header = res && res.headers ? res.headers.get("server-timing") || "" : "";
  const match = /dur=([\d.]+)/.exec(header);
  return match ? Math.round(parseFloat(match[1])) : null;
}
/* In-flight requests of this page: browsers open at most 6 HTTP/1.1 connections per origin,
   so a 7th request waits in the browser and never reaches the server. */
const inflight = new Set();
async function timedFetch(url, opts) {
  const options = Object.assign({}, opts || {});
  const method = options.method || "GET";
  const timeoutMs = options.timeoutMs || 0;
  delete options.timeoutMs;
  const controller = timeoutMs ? new AbortController() : null;
  if (controller) options.signal = controller.signal;
  const abortTimer = controller ? setTimeout(() => controller.abort(), timeoutMs) : null;
  const started = performance.now();
  const label = `${method} ${url}`;
  const key = label + " @" + Math.round(started);
  inflight.add(key);
  perfLog("debug", "→", label, `(in flight: ${inflight.size})`);
  const slow = setInterval(() => {
    perfLog("warn", "… still waiting", label, Math.round(performance.now() - started) + " ms",
      `in flight: ${inflight.size}`, Array.from(inflight));
  }, PERF_SLOW_MS);
  try {
    const res = await fetch(url, options);
    const ms = Math.round(performance.now() - started);
    const server = serverTiming(res);
    const id = res.headers.get("x-duosave-request");
    perfLog(ms >= 1000 ? "warn" : "debug", "←", label, res.status, ms + " ms",
      server !== null ? `(server headers ${server} ms)` : "", id ? "#" + id : "");
    return res;
  } catch (err) {
    perfLog("error", "✗", label, Math.round(performance.now() - started) + " ms", err);
    if (err && err.name === "AbortError") {
      const timeout = new Error(t("req_timeout").replace("{s}", Math.round(timeoutMs / 1000)));
      timeout.timeout = true;
      throw timeout;
    }
    throw err;
  } finally {
    inflight.delete(key);
    clearInterval(slow);
    if (abortTimer) clearTimeout(abortTimer);
  }
}

async function fetchJson(url) {
  const res = await timedFetch(url);
  if (!res.ok) throw new Error("HTTP " + res.status);
  return res.json();
}

/* ------------------------------- search --------------------------------- */
/* The main studied language, mirroring config.DEFAULT_LANGUAGE: the site opens on it. */
const DEFAULT_LANG = "pt";
const state = { q: "", lang: DEFAULT_LANG, app: "", sort: "new", mode: "hybrid", page: 0, total: 0, loaded: 0, card: 0 };
let reqSeq = 0;
let searchTimer = null;
let openCardId = null;

function readUrlState() {
  const p = new URLSearchParams(location.search);
  state.q = (p.get("q") || "").trim();
  /* an explicit `lang=` (even empty: "all languages") wins over the default */
  state.lang = p.has("lang") ? (p.get("lang") || "") : DEFAULT_LANG;
  state.app = p.get("app") || "";
  state.sort = p.get("sort") === "old" ? "old" : "new";
  const mode = p.get("mode");
  state.mode = mode === "text" || mode === "semantic" ? mode : "hybrid";
  const page = parseInt(p.get("page") || "0", 10);
  state.page = Number.isFinite(page) && page > 0 ? page : 0;
  const card = parseInt(p.get("card") || "0", 10);
  state.card = Number.isFinite(card) && card > 0 ? card : 0;
}
function syncUrl(mode) {
  const p = new URLSearchParams();
  if (state.q) p.set("q", state.q);
  if (state.lang !== DEFAULT_LANG) p.set("lang", state.lang);
  if (state.app) p.set("app", state.app);
  if (state.sort && state.sort !== "new") p.set("sort", state.sort);
  if (state.mode && state.mode !== "hybrid") p.set("mode", state.mode);
  if (state.page > 0) p.set("page", String(state.page));
  if (openCardId) p.set("card", String(openCardId));
  const qs = p.toString();
  const url = location.pathname + (qs ? "?" + qs : "");
  const method = mode === "push" ? "pushState" : "replaceState";
  history[method]({ duosave: true, card: openCardId || 0 }, "", url);
}
function applyStateToUi() {
  const input = document.getElementById("search");
  if (input) input.value = state.q;
  const groups = [["lang-chips", state.lang], ["app-chips", state.app], ["sort-chips", state.sort], ["mode-chips", state.mode]];
  for (const [id, value] of groups) {
    const wrap = document.getElementById(id);
    if (wrap) wrap.querySelectorAll(".chip").forEach((c) => c.classList.toggle("active", (c.dataset.value || "") === value));
  }
}

function bindChips(id, key) {
  const wrap = document.getElementById(id);
  if (!wrap) return;
  wrap.querySelectorAll(".chip").forEach((chip) =>
    chip.addEventListener("click", () => {
      wrap.querySelectorAll(".chip").forEach((c) => c.classList.remove("active"));
      chip.classList.add("active");
      state[key] = chip.dataset.value || "";
      state.page = 0;
      syncUrl("push");
      render(true);
    }));
}

async function loadPage(page) {
  const params = new URLSearchParams({
    q: state.q, lang: state.lang, app: state.app, page, limit: 60, sort: state.sort, mode: state.mode,
  });
  const data = await fetchJson("/api/search?" + params);
  const wrap = document.getElementById("cards");
  for (const card of data.items) {
    const div = document.createElement("article");
    div.className = "card";
    div.innerHTML = cardMarkup(card);
    div.addEventListener("click", () => showCard(card.id, true));
    wrap.appendChild(div);
  }
  state.loaded += data.items.length;
  return data;
}

async function render(reset) {
  const wrap = document.getElementById("cards");
  if (!wrap) return;
  const seq = ++reqSeq;
  if (reset) {
    state.loaded = 0;
    wrap.innerHTML = "";
  }
  hide(document.getElementById("empty"));
  setStatus(t("loading"), true);
  setBusy(wrap, true);
  try {
    let data = null;
    if (reset) {
      for (let p = 0; p <= state.page; p++) {
        data = await loadPage(p);
        if (seq !== reqSeq) return; /* superseded by a newer request */
        if (p < state.page && data.items.length === 0) break;
      }
    } else {
      data = await loadPage(state.page);
      if (seq !== reqSeq) return;
    }
    if (!data) return;
    state.total = data.total;
    const more = document.getElementById("more");
    if (more) more.style.display = state.loaded > 0 && state.loaded < data.total ? "block" : "none";
    let status = `${data.total} ${t("cards")}`;
    const semantic = data.semantic || {};
    if (semantic.stale > 0) status += ` · ${t("sem_stale").replace("{n}", semantic.stale)}`;
    if (semantic.available === false && state.mode !== "text") {
      status += ` · ${t("sem_unavailable").replace("{reason}", semantic.reason)}`;
    }
    setStatus(status, false);
    if (state.loaded === 0) show(document.getElementById("empty"));
  } catch (err) {
    if (seq !== reqSeq) return;
    setStatus(t("load_error"), false);
    show(document.getElementById("empty"));
  } finally {
    if (seq === reqSeq) { setBusy(wrap, false); bootDone(); }
  }
}

function initIndex() {
  readUrlState();
  applyStateToUi();
  bindTheme();
  applyTheme();
  loadBuildInfo();
  loadSession();
  registerServiceWorker();
  initUploadPanel();
  const input = document.getElementById("search");
  if (input) {
    input.addEventListener("input", () => {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(() => {
        state.q = input.value.trim();
        state.page = 0;
        syncUrl("push");
        render(true);
      }, 250);
    });
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        clearTimeout(searchTimer);
        state.q = input.value.trim();
        state.page = 0;
        syncUrl("push");
        render(true);
      }
    });
  }
  bindChips("lang-chips", "lang");
  bindChips("app-chips", "app");
  bindChips("sort-chips", "sort");
  bindChips("mode-chips", "mode");
  const more = document.getElementById("more");
  if (more) more.addEventListener("click", () => { state.page += 1; syncUrl("push"); render(false); });
  window.addEventListener("popstate", () => {
    const prev = { q: state.q, lang: state.lang, app: state.app, sort: state.sort, mode: state.mode, page: state.page };
    readUrlState();
    applyStateToUi();
    if (prev.q !== state.q || prev.lang !== state.lang || prev.app !== state.app
        || prev.sort !== state.sort || prev.mode !== state.mode || prev.page !== state.page) {
      render(true);
    }
    if (state.card && state.card !== openCardId) showCard(state.card, false);
    else if (!state.card && openCardId) hideCard();
  });
  applyI18n();
  render(true);
  if (state.card) showCard(state.card, false);
}

function cardMarkup(card) {
  const crop = card.sources && card.sources.find((s) => s.crop_path);
  const statusLabel = card.status === "manual" ? `<span class="badge manual">${t("status_manual")}</span>` : "";
  const dateLabel = card.card_time ? `<span class="badge date">${fmtDate(card.card_time)}</span>` : "";
  const media = crop ? `<div class="media"><img loading="lazy" src="${mediaUrl(crop.crop_path)}" alt=""></div>` : "";
  const srcPath = card.sources && card.sources[0] ? card.sources[0].path : "";
  const srcLine = card.app === "drops" || !srcPath ? ""
    : `<div class="src" title="${esc(srcPath)}">
         ${t("source")}: <a href="${sourceUrl(srcPath)}" target="_blank" onclick="event.stopPropagation()">${esc(srcPath)}</a></div>`;
  return `<div class="badges">
      <span class="badge lang">${esc(card.language)}</span>
      <span class="badge">${esc(card.app)}</span>${dateLabel}${statusLabel}
    </div>
    <p class="original">${esc(card.original)}</p>
    <p class="translation">${esc(card.translation)}</p>
    ${media}${srcLine}`;
}

async function showCard(id, push) {
  let card;
  try { card = await fetchJson("/api/cards/" + id); } catch (err) { return; }
  if (!card || !card.id) return;
  openCardId = card.id;
  renderCardModal(card);
  document.getElementById("modal-back").style.display = "flex";
  if (push) syncUrl("push");
}
function renderCardModal(card) {
  const crop = card.sources.find((s) => s.crop_path);
  const sources = card.sources.map((s) => {
    const when = s.file_time ? ` <span class="src-date">${fmtDate(s.file_time)}</span>` : "";
    const img = s.crop_path ? ` · <a href="${mediaUrl(s.crop_path)}" target="_blank">img</a>` : "";
    return `<div><a href="${sourceUrl(s.path)}" target="_blank">${esc(s.path)}</a>${when}${img}</div>`;
  }).join("");
  document.getElementById("modal-body").innerHTML = `
    <div class="badges">
      <span class="badge lang">${esc(card.language)}</span>
      <span class="badge">${esc(card.app)}</span>
      <span class="badge">${esc(card.screen_type || "")}</span>
      ${card.card_time ? `<span class="badge date">${fmtDate(card.card_time)}</span>` : ""}
    </div>
    <div class="pair">${esc(card.original)}<div class="tr">${esc(card.translation)}</div></div>
    ${crop ? `<img class="crop" src="${mediaUrl(crop.crop_path)}">` : ""}
    <div class="sources"><strong>${t("sources")}:</strong>${sources}</div>`;
}
function hideCard() {
  document.getElementById("modal-back").style.display = "none";
  openCardId = null;
}
function closeModal() {
  if (history.state && history.state.card) { history.back(); return; }
  hideCard();
  syncUrl("replace");
}

/* ------------------------------- review --------------------------------- */
let reviewPage = 0;
let reviewSeq = 0;
let languages = null; /* /api/languages: the combobox options, main language first */

async function loadLanguages() {
  try {
    languages = await fetchJson("/api/languages");
  } catch (err) {
    languages = null; /* the combobox falls back to "unknown" only */
  }
}

/* Options for the review combobox: the languages the site knows, detected one preselected. */
function languageOptions(selected) {
  const list = (languages && languages.languages) || [];
  const options = [`<option value=""${selected ? "" : " selected"}>${esc(t("lang_unknown"))}</option>`];
  for (const language of list) {
    const mark = language.code === selected ? " selected" : "";
    options.push(`<option value="${esc(language.code)}"${mark}>${esc(language.code.toUpperCase())} — ${esc(language.name)}</option>`);
  }
  return options.join("");
}

async function loadReview(reset) {
  const wrap = document.getElementById("review-list");
  if (!wrap) return;
  const seq = ++reviewSeq;
  if (reset) {
    reviewPage = 0;
    wrap.innerHTML = "";
  }
  hide(document.getElementById("empty"));
  setStatus(t("loading"), true);
  setBusy(wrap, true);
  try {
    const data = await fetchJson("/api/review?page=" + reviewPage + "&limit=40");
    if (seq !== reviewSeq) return;
    for (const item of data.items) {
      const div = document.createElement("div");
      div.className = "review-item";
      div.innerHTML = reviewMarkup(item);
      wrap.appendChild(div);
    }
    const more = document.getElementById("more");
    if (more) more.style.display = (reviewPage + 1) * 40 < data.total ? "block" : "none";
    setStatus(`${t("review_queue")} ${data.total}`, false);
    if (data.total === 0) show(document.getElementById("empty"));
  } catch (err) {
    if (seq !== reviewSeq) return;
    setStatus(t("load_error"), false);
    show(document.getElementById("empty"));
  } finally {
    if (seq === reviewSeq) { setBusy(wrap, false); bootDone(); }
  }
}

function initReviewPage() {
  bindTheme();
  applyTheme();
  loadBuildInfo();
  loadSession();
  registerServiceWorker();
  initUploadPanel();
  const more = document.getElementById("more");
  if (more) more.addEventListener("click", () => { reviewPage += 1; loadReview(false); });
  applyI18n();
  loadLanguages().then(() => loadReview(true));
}

function reviewMarkup(item) {
  const crop = item.crop_path ? `<img class="crop" src="${mediaUrl(item.crop_path)}">` : "";
  const guess = item.original
    ? `<div class="guess"><div class="o">${esc(item.original)}</div><div class="t">${esc(item.translation || "")}</div></div>`
    : `<div class="guess">${t("no_guess")}</div>`;
  /* The combobox edits the language of an existing card; a frame with no guess has none. */
  const picker = item.card_id
    ? `<select class="lang-select" title="${esc(t("lang_label"))}">${languageOptions(item.language || "")}</select>`
    : "";
  return `<div class="path">${t("path")} <a href="${sourceUrl(item.path)}" target="_blank">${esc(item.path)}</a>
      <span style="opacity:.6">· ${esc(item.reason || "")}</span></div>
    ${crop}${guess}
    <div class="row">
      ${picker}
      <button class="btn ok" onclick="reviewAction(this, '${esc(item.path)}', 'accept')">${t("accept")}</button>
      <button class="btn bad" onclick="reviewAction(this, '${esc(item.path)}', 'reject')">${t("reject")}</button>
      <button class="btn" onclick="toggleEdit(this)">${t("edit")}</button>
    </div>
    <div class="edit-form">
      <input id="e-orig" value="${esc(item.original || "")}" placeholder="original">
      <input id="e-trans" value="${esc(item.translation || "")}" placeholder="translation">
      <div class="row">
        <button class="btn ok" onclick="editAction(this, '${esc(item.path)}')">${t("save")}</button>
        <button class="btn" onclick="toggleEdit(this)">${t("cancel")}</button>
      </div>
    </div>`;
}
function toggleEdit(btn) {
  const form = btn.closest(".review-item").querySelector(".edit-form");
  form.classList.toggle("open");
}
/* The language combobox, when the item has one: it feeds both accept and edit. */
function pickedLanguage(item) {
  const picker = item.querySelector(".lang-select");
  return picker ? picker.value : "";
}
async function reviewAction(btn, path, action) {
  const language = pickedLanguage(btn.closest(".review-item"));
  await timedFetch("/api/review", { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path, action, language }) });
  loadReview(true);
}
async function editAction(btn, path) {
  const item = btn.closest(".review-item");
  const original = item.querySelector("#e-orig").value.trim();
  const translation = item.querySelector("#e-trans").value.trim();
  const language = pickedLanguage(item);
  await timedFetch("/api/review", { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path, action: "edit", original, translation, language }) });
  loadReview(true);
}

/* ------------------------------- upload --------------------------------- */
const UPLOAD_ERRORS = {
  csrf: "upload_err_csrf", too_large: "upload_err_too_large",
  not_an_image: "upload_err_not_an_image", busy: "upload_err_busy",
};

function uploadErrorText(payload) {
  const code = (payload && payload.error) || "";
  const limit = payload && payload.limit_mb;
  if (code === "too_large" && !limit) return t("upload_err_too_large_no_limit");
  const text = t(UPLOAD_ERRORS[code] || "upload_err_generic");
  return limit ? text.replace("{mb}", limit) : text;
}

function uploadRow(name) {
  const results = document.getElementById("upload-results");
  if (!results) return null;
  const row = document.createElement("div");
  row.className = "upload-row";
  const label = document.createElement("span");
  label.className = "upload-name";
  label.textContent = name;
  const text = document.createElement("span");
  text.className = "upload-text";
  row.appendChild(label);
  row.appendChild(text);
  results.appendChild(row);
  return row;
}

function uploadText(row, text, href, linkText) {
  if (!row) return;
  const holder = row.querySelector(".upload-text");
  holder.textContent = text;
  if (!href) return;
  const link = document.createElement("a");
  link.className = "upload-open";
  link.href = href;
  link.textContent = linkText;
  holder.appendChild(document.createTextNode(" "));
  holder.appendChild(link);
}

function uploadOutcome(row, data) {
  if (!row) return;
  row.className = "upload-row done";
  if (data.outcome === "duplicate") {
    uploadText(row, t("upload_dup"), data.card_id ? "/?card=" + data.card_id : "", t("upload_open"));
    return;
  }
  if (data.status === "review") {
    uploadText(row, t("upload_review"), "/review", t("upload_open"));
    return;
  }
  if (data.status === "auto" && data.card_id) {
    const pair = (data.pairs && data.pairs[0]) || {};
    const text = t("upload_card").replace("{original}", pair.original || "")
      .replace("{translation}", pair.translation || "");
    uploadText(row, text, "/?card=" + data.card_id, t("upload_open"));
    return;
  }
  uploadText(row, data.path || "", "", ""); /* skipped: the frame is stored, no card */
}

/* One file at a time: raw bytes in the body, so vision calls never overlap. */
async function uploadFile(file) {
  const row = uploadRow(file.name);
  if (row) {
    row.className = "upload-row busy";
    uploadText(row, t("upload_busy"), "", "");
  }
  try {
    const res = await timedFetch("/api/upload", { method: "POST", headers: { "X-Duosave-Request": "1" }, body: file });
    const payload = await res.json().catch(() => null);
    if (!res.ok) {
      if (row) row.className = "upload-row error";
      uploadText(row, uploadErrorText(payload), "", "");
      return false;
    }
    uploadOutcome(row, payload);
    return true;
  } catch (err) {
    if (row) row.className = "upload-row error";
    uploadText(row, uploadErrorText(null), "", "");
    return false;
  }
}

async function uploadFiles(files) {
  const panel = document.getElementById("upload-panel");
  const results = document.getElementById("upload-results");
  if (!files.length) return;
  if (panel) panel.dataset.state = "busy";
  for (const file of files) await uploadFile(file);
  if (panel) panel.dataset.state = results && results.querySelector(".upload-row.error") ? "error" : "done";
  const btn = document.getElementById("upload-btn");
  if (btn) btn.focus(); /* focus returns to the toggle once the queue is done */
}

function initUploadPanel() {
  const btn = document.getElementById("upload-btn");
  const panel = document.getElementById("upload-panel");
  const zone = document.getElementById("drop-zone");
  const input = document.getElementById("upload-input");
  if (!btn || !panel || !zone || !input) return;
  panel.dataset.state = "idle";
  btn.addEventListener("click", () => {
    panel.hidden = !panel.hidden;
    btn.setAttribute("aria-expanded", String(!panel.hidden));
  });
  zone.addEventListener("dragover", (event) => { event.preventDefault(); zone.classList.add("dragover"); });
  zone.addEventListener("dragleave", (event) => {
    if (!zone.contains(event.relatedTarget)) zone.classList.remove("dragover");
  });
  zone.addEventListener("drop", (event) => {
    event.preventDefault();
    zone.classList.remove("dragover");
    uploadFiles(Array.from(event.dataTransfer.files || []));
  });
  input.addEventListener("change", () => {
    const files = Array.from(input.files || []);
    input.value = "";
    uploadFiles(files);
  });
}

/* -------------------------------- share ---------------------------------- */
/* The share outcome page: counts and links come from the URL, never from the database. */
const SHARE_COUNT_KEYS = ["new", "review", "skip", "dup"];
const SHARE_REDIRECT_MS = 3000; /* the status stays visible briefly, then the main page opens */
let shareTimer = null;

function shareCount(params, key) {
  const value = parseInt(params.get(key) || "0", 10);
  return Number.isFinite(value) && value > 0 ? value : 0;
}

function renderShare() {
  const wrap = document.getElementById("share");
  if (!wrap) return;
  const params = new URLSearchParams(location.search);
  const summary = document.getElementById("share-summary");
  if (summary) {
    let text = t("share_counts");
    for (const key of SHARE_COUNT_KEYS) text = text.replace(`{${key}}`, shareCount(params, key));
    summary.textContent = text;
  }
  const open = document.getElementById("share-open-card");
  if (open) {
    const card = shareCount(params, "card");
    open.href = "/?card=" + card;
    open.hidden = card === 0;
  }
  const error = params.get("error") || "";
  const note = document.getElementById("share-note");
  if (note) {
    if (error === "sw") note.textContent = t("share_sw_stale");
    else if (error === "empty") note.textContent = t("share_empty");
    else if (error) note.textContent = uploadErrorText({ error });
    note.hidden = !error;
  }
  /* A clean share opens the main page by itself; an error keeps this page in place. */
  clearTimeout(shareTimer);
  const redirect = document.getElementById("share-redirect");
  if (redirect) redirect.hidden = !!error;
  if (error) return;
  shareTimer = setTimeout(() => location.replace("/"), SHARE_REDIRECT_MS);
}

function initSharePage() {
  bindTheme();
  applyTheme();
  loadBuildInfo();
  loadSession();
  registerServiceWorker();
  if (new URLSearchParams(location.search).get("error") === "sw") {
    /* The service worker was not active: offer the usual file picker right away. */
    initUploadPanel();
    const panel = document.getElementById("upload-panel");
    const btn = document.getElementById("upload-btn");
    if (panel) panel.hidden = false;
    if (btn) {
      btn.hidden = false;
      btn.setAttribute("aria-expanded", "true");
    }
  }
  applyI18n();
  renderShare();
  bootDone(); /* the outcome comes from the URL: there is nothing to wait for */
}
