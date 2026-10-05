/* Duosave frontend: search + review, RU/EN, light/dark theme. */
"use strict";

const I18N = {
  ru: {
    nav_cards: "Карточки", nav_review: "Проверка",
    search_ph: "Поиск по оригиналу и переводу…",
    all: "Все",
    sort_new: "Сначала новые", sort_old: "Сначала старые",
    empty: "Ничего не найдено",
    more: "Показать ещё",
    loading: "Загрузка…",
    load_error: "Не удалось загрузить",
    review_empty: "Очередь пуста",
    cards: "карточек", sources: "источники", source: "источник",
    accept: "Принять", reject: "Отклонить", edit: "Изменить", save: "Сохранить", cancel: "Отмена",
    status_auto: "авто", status_review: "проверка", status_manual: "подтверждено",
    review_queue: "На проверке:", no_guess: "Пары не найдено — посмотрите скриншот",
    path: "Путь:",
  },
  en: {
    nav_cards: "Cards", nav_review: "Review",
    search_ph: "Search by original and translation…",
    all: "All",
    sort_new: "Newest first", sort_old: "Oldest first",
    empty: "Nothing found",
    more: "Show more",
    loading: "Loading…",
    load_error: "Failed to load",
    review_empty: "Queue is empty",
    cards: "cards", sources: "sources", source: "source",
    accept: "Accept", reject: "Reject", edit: "Edit", save: "Save", cancel: "Cancel",
    status_auto: "auto", status_review: "review", status_manual: "verified",
    review_queue: "To review:", no_guess: "No pair found — check the screenshot",
    path: "Path:",
  },
};
let lang = localStorage.getItem("duosave_lang") || "ru";
function t(key) { return (I18N[lang] || I18N.ru)[key] || key; }
function applyI18n() {
  document.documentElement.lang = lang;
  document.querySelectorAll("[data-i18n]").forEach((el) => { el.textContent = t(el.dataset.i18n); });
  document.querySelectorAll("[data-i18n-ph]").forEach((el) => { el.placeholder = t(el.dataset.i18nPh); });
  document.querySelectorAll(".lang a").forEach((a) => a.classList.toggle("active", a.dataset.lang === lang));
}
document.querySelectorAll(".lang a").forEach((a) =>
  a.addEventListener("click", (e) => {
    e.preventDefault();
    lang = a.dataset.lang;
    localStorage.setItem("duosave_lang", lang);
    applyI18n();
    if (document.getElementById("cards")) render(true);
    else if (document.getElementById("review-list")) loadReview(true);
  }));

/* theme */
let theme = localStorage.getItem("duosave_theme")
  || (window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
function applyTheme() {
  document.documentElement.dataset.theme = theme;
  const btn = document.getElementById("theme-btn");
  if (btn) btn.textContent = theme === "dark" ? "☀️" : "🌙";
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

async function fetchJson(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error("HTTP " + res.status);
  return res.json();
}

/* ------------------------------- search --------------------------------- */
const state = { q: "", lang: "", app: "", sort: "new", page: 0, total: 0, loaded: 0, card: 0 };
let reqSeq = 0;
let searchTimer = null;
let openCardId = null;

function readUrlState() {
  const p = new URLSearchParams(location.search);
  state.q = (p.get("q") || "").trim();
  state.lang = p.get("lang") || "";
  state.app = p.get("app") || "";
  state.sort = p.get("sort") === "old" ? "old" : "new";
  const page = parseInt(p.get("page") || "0", 10);
  state.page = Number.isFinite(page) && page > 0 ? page : 0;
  const card = parseInt(p.get("card") || "0", 10);
  state.card = Number.isFinite(card) && card > 0 ? card : 0;
}
function syncUrl(mode) {
  const p = new URLSearchParams();
  if (state.q) p.set("q", state.q);
  if (state.lang) p.set("lang", state.lang);
  if (state.app) p.set("app", state.app);
  if (state.sort && state.sort !== "new") p.set("sort", state.sort);
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
  const groups = [["lang-chips", state.lang], ["app-chips", state.app], ["sort-chips", state.sort]];
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
    q: state.q, lang: state.lang, app: state.app, page, limit: 60, sort: state.sort,
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
    setStatus(`${data.total} ${t("cards")}`, false);
    if (state.loaded === 0) show(document.getElementById("empty"));
  } catch (err) {
    if (seq !== reqSeq) return;
    setStatus(t("load_error"), false);
    show(document.getElementById("empty"));
  } finally {
    if (seq === reqSeq) setBusy(wrap, false);
  }
}

function initIndex() {
  readUrlState();
  applyStateToUi();
  bindTheme();
  applyTheme();
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
  const more = document.getElementById("more");
  if (more) more.addEventListener("click", () => { state.page += 1; syncUrl("push"); render(false); });
  window.addEventListener("popstate", () => {
    const prev = { q: state.q, lang: state.lang, app: state.app, sort: state.sort, page: state.page };
    readUrlState();
    applyStateToUi();
    if (prev.q !== state.q || prev.lang !== state.lang || prev.app !== state.app
        || prev.sort !== state.sort || prev.page !== state.page) {
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
    if (seq === reviewSeq) setBusy(wrap, false);
  }
}

function initReviewPage() {
  bindTheme();
  applyTheme();
  const more = document.getElementById("more");
  if (more) more.addEventListener("click", () => { reviewPage += 1; loadReview(false); });
  applyI18n();
  loadReview(true);
}

function reviewMarkup(item) {
  const crop = item.crop_path ? `<img class="crop" src="${mediaUrl(item.crop_path)}">` : "";
  const guess = item.original
    ? `<div class="guess"><div class="o">${esc(item.original)}</div><div class="t">${esc(item.translation || "")}</div></div>`
    : `<div class="guess">${t("no_guess")}</div>`;
  return `<div class="path">${t("path")} <a href="${sourceUrl(item.path)}" target="_blank">${esc(item.path)}</a>
      <span style="opacity:.6">· ${esc(item.reason || "")}</span></div>
    ${crop}${guess}
    <div class="row">
      <button class="btn ok" onclick="reviewAction('${esc(item.path)}','accept')">${t("accept")}</button>
      <button class="btn bad" onclick="reviewAction('${esc(item.path)}','reject')">${t("reject")}</button>
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
async function reviewAction(path, action) {
  await fetch("/api/review", { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path, action }) });
  loadReview(true);
}
async function editAction(btn, path) {
  const item = btn.closest(".review-item");
  const original = item.querySelector("#e-orig").value.trim();
  const translation = item.querySelector("#e-trans").value.trim();
  await fetch("/api/review", { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path, action: "edit", original, translation }) });
  loadReview(true);
}
