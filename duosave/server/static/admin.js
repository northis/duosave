/* Maintenance page: local-listener only. Extends the shared I18N and helpers from app.js. */
"use strict";

Object.assign(I18N.ru, {
  adm_patches: "Импорт патча",
  adm_backup: "Бэкап",
  adm_cards: "Карточки",
  adm_busy: "Выполняется другая операция…",
  adm_error: "Ошибка",
  adm_confirm: "Подтвердить?",
  cd_ph: "Поиск по оригиналу и переводу…",
  cd_search: "Найти",
  cd_delete: "Удалить",
  cd_confirm: "Удалить карточку вместе с её картинками? Действие необратимо.",
  cd_deleted: "Удалено: «{label}» (картинок: {n})",
  cd_hint: "Язык меняется прямо в строке; удаление убирает карточку, её источники и исходные картинки (включая кроп Drops) — ту же картинку можно загрузить заново и распознать ещё раз.",
  cd_found: "Найдено карточек: {n}",
  cd_col_card: "Карточка",
  cd_col_app: "Источник",
  cd_col_lang: "Язык",
  cd_lang_changed: "Язык изменён: «{label}» → {lang}",
  cd_lang_merged: "Карточка «{label}» объединена с #{id}",
  bk_db: "Скачать: только БД",
  bk_full: "Скачать: полный",
  bk_hint: "Восстановление — README, раздел «Бэкап и восстановление».",
  pt_known: "Скачать список известных картинок",
  pt_pick: "Выбрать патч (zip)",
  pt_known_hint: "Положите файл в outbox/known-hashes.txt клона на машине агента — scan пропустит эти картинки. Патчи загружаются по одному (zip).",
  pt_uploading: "загрузка…",
  pt_apply: "Применить",
  pt_discard: "Отменить",
  pt_new: "новых",
  pt_dup: "дубликатов",
  pt_renamed: "переименовано",
  pt_review: "на проверку",
  pt_new_cards: "новых карточек",
  pt_existing_cards: "существующих",
  pt_already: "Этот патч уже применён.",
  pt_errors: "Ошибки проверки",
  pt_reindex_idle: "Семантический индекс: без изменений",
  pt_reindex_running: "Семантический индекс: обновляется…",
  pt_reindex_done: "Семантический индекс: обновлён",
  pt_reindex_unavailable: "Семантический индекс недоступен",
  pt_reindex_failed: "Семантический индекс: ошибка",
  pt_staged: "Отложенные",
  pt_history: "История",
  pt_file: "Файл",
  pt_app: "Приложение",
  pt_pairs: "Пары",
  pt_outcome: "Исход",
  pt_apply_confirm: "Применить патч? Будут записаны картинки и карточки, снимок БД создаётся автоматически.",
  pt_discard_confirm: "Удалить отложенный патч?",
  pt_patch: "Патч",
  pt_when: "Когда",
  pt_who: "Кто",
  pt_files: "Файлов",
  adm_network: "Сеть: запрос не дошёл до сервера",
  adm_sec: "с",
  pt_known_busy: "Готовим список известных картинок…",
  pt_known_done: "Список скачан ({size})",
  pt_checking: "проверка и разбор на сервере…",
  pt_applying: "Применяется патч {id}…",
  pt_applied: "Патч {id} применён: файлов {files}, обновлено дат {touched}, заменено картинок {replaced}",
  cd_deleting: "удаление…",
  cd_missing: "Карточки уже нет",
});
Object.assign(I18N.en, {
  adm_patches: "Patch import",
  adm_backup: "Backup",
  adm_cards: "Cards",
  adm_busy: "Another operation is in progress…",
  adm_error: "Error",
  adm_confirm: "Confirm?",
  cd_ph: "Search by original and translation…",
  cd_search: "Search",
  cd_delete: "Delete",
  cd_confirm: "Delete the card together with its images? This cannot be undone.",
  cd_deleted: "Deleted “{label}” (images: {n})",
  cd_hint: "The language changes right in the row; deleting removes the card, its sources and the source images (the Drops crop included) — the same image can be uploaded and recognized again.",
  cd_found: "Cards found: {n}",
  cd_col_card: "Card",
  cd_col_app: "Source",
  cd_col_lang: "Language",
  cd_lang_changed: "Language changed: “{label}” → {lang}",
  cd_lang_merged: "Card “{label}” merged into #{id}",
  bk_db: "Download: DB only",
  bk_full: "Download: full",
  bk_hint: "Restore instructions — README, “Backup and restore”.",
  pt_known: "Download the known-images list",
  pt_pick: "Choose a patch (zip)",
  pt_known_hint: "Put the file into outbox/known-hashes.txt of the agent clone — scan will skip those images. Upload patches one zip at a time.",
  pt_uploading: "uploading…",
  pt_apply: "Apply",
  pt_discard: "Discard",
  pt_new: "new",
  pt_dup: "duplicates",
  pt_renamed: "renamed",
  pt_review: "to review",
  pt_new_cards: "new cards",
  pt_existing_cards: "existing",
  pt_already: "This patch is already applied.",
  pt_errors: "Validation errors",
  pt_reindex_idle: "Semantic index: idle",
  pt_reindex_running: "Semantic index: updating…",
  pt_reindex_done: "Semantic index: updated",
  pt_reindex_unavailable: "Semantic index unavailable",
  pt_reindex_failed: "Semantic index: failed",
  pt_staged: "Staged",
  pt_history: "History",
  pt_file: "File",
  pt_app: "App",
  pt_pairs: "Pairs",
  pt_outcome: "Outcome",
  pt_apply_confirm: "Apply the patch? Images and cards will be written; a DB snapshot is taken automatically.",
  pt_discard_confirm: "Delete the staged patch?",
  pt_patch: "Patch",
  pt_when: "When",
  pt_who: "Who",
  pt_files: "Files",
  adm_network: "Network: the request did not reach the server",
  adm_sec: "s",
  pt_known_busy: "Preparing the known-images list…",
  pt_known_done: "List downloaded ({size})",
  pt_checking: "validating and parsing on the server…",
  pt_applying: "Applying patch {id}…",
  pt_applied: "Patch {id} applied: files {files}, dates updated {touched}, images replaced {replaced}",
  cd_deleting: "deleting…",
  cd_missing: "The card is already gone",
});

/* fetch with the CSRF header on mutations; throws Error with .status/.payload on failures */
async function adminFetch(url, opts) {
  const options = Object.assign({}, opts || {});
  if (options.method && options.method !== "GET") {
    options.headers = Object.assign({}, options.headers, { "X-Duosave-Request": "1" });
  }
  const res = await timedFetch(url, options);
  const text = await res.text();
  let payload = null;
  try { payload = text ? JSON.parse(text) : null; } catch (err) { payload = null; }
  if (!res.ok) {
    const error = new Error((payload && (payload.detail || payload.error)) || "HTTP " + res.status);
    error.status = res.status;
    error.payload = payload;
    throw error;
  }
  return payload;
}

/* POST a file with upload progress (fetch has none): onProgress(sent, total), then the
   "server is processing" phase starts when the last byte is sent. Logged like timedFetch. */
function adminUpload(url, file, contentType, onProgress, onSent) {
  return new Promise((resolve, reject) => {
    const started = performance.now();
    const label = "POST " + url + " (" + fmtSize(file.size) + ")";
    perfLog("debug", "→", label);
    const xhr = new XMLHttpRequest();
    xhr.open("POST", url);
    xhr.setRequestHeader("X-Duosave-Request", "1");
    xhr.setRequestHeader("Content-Type", contentType);
    xhr.upload.onprogress = (event) => onProgress && onProgress(event.loaded, event.total || file.size);
    xhr.upload.onload = () => {
      perfLog("debug", "⇡ sent", label, Math.round(performance.now() - started) + " ms");
      if (onSent) onSent();
    };
    xhr.onload = () => {
      const ms = Math.round(performance.now() - started);
      const timing = /dur=([\d.]+)/.exec(xhr.getResponseHeader("server-timing") || "");
      perfLog(ms >= 1000 ? "warn" : "debug", "←", label, xhr.status, ms + " ms",
        timing ? `(server ${Math.round(parseFloat(timing[1]))} ms)` : "",
        "#" + (xhr.getResponseHeader("x-duosave-request") || "?"));
      let payload = null;
      try { payload = xhr.responseText ? JSON.parse(xhr.responseText) : null; } catch (err) { payload = null; }
      if (xhr.status >= 200 && xhr.status < 300) { resolve(payload); return; }
      const error = new Error((payload && (payload.detail || payload.error)) || "HTTP " + xhr.status);
      error.status = xhr.status;
      error.payload = payload;
      reject(error);
    };
    xhr.onerror = () => {
      perfLog("error", "✗", label, Math.round(performance.now() - started) + " ms");
      reject(new Error(t("adm_network")));
    };
    xhr.send(file);
  });
}

/* Download through fetch so the page can show progress and errors instead of a silent link. */
async function adminDownload(url, fallbackName, onProgress) {
  const res = await timedFetch(url);
  if (!res.ok) {
    let detail = "HTTP " + res.status;
    try { const data = await res.json(); detail = data.detail || data.error || detail; } catch (err) { /* text */ }
    throw new Error(detail);
  }
  const total = parseInt(res.headers.get("content-length") || "0", 10);
  const reader = res.body.getReader();
  const parts = [];
  let received = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    parts.push(value);
    received += value.length;
    if (onProgress) onProgress(received, total);
  }
  const match = /filename="([^"]+)"/.exec(res.headers.get("content-disposition") || "");
  const link = document.createElement("a");
  link.href = URL.createObjectURL(new Blob(parts));
  link.download = match ? match[1] : fallbackName;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(link.href), 10000);
  return received;
}

/* Seconds since `since`, for "working… 12 s" labels; a ticker repaints busy sections. */
function elapsed(since) { return Math.max(0, Math.round((Date.now() - since) / 1000)) + " " + t("adm_sec"); }
let busyTicker = null;
function tickWhileBusy() {
  if (busyTicker) return;
  busyTicker = setInterval(() => {
    const busy = ADMIN_SECTIONS.filter((section) => section.isBusy && section.isBusy());
    busy.forEach((section) => section.paint());
    if (!busy.length) { clearInterval(busyTicker); busyTicker = null; }
  }, 1000);
}

const CARD_DELETE_TIMEOUT_MS = 20000;
const ADMIN_SECTIONS = [];

function renderAdmin() {
  ADMIN_SECTIONS.forEach((section) => section.render());
}

function initAdminPage() {
  bindTheme();
  applyTheme();
  applyI18n();
  loadBuildInfo();
  loadSession();
  ADMIN_SECTIONS.forEach((section) => section.init());
  bootDone(); /* every panel has painted its loader: the page is readable while it waits */
}

function fmtSize(bytes) {
  if (bytes == null) return "";
  if (bytes >= 1024 * 1024 * 1024) return (bytes / (1024 * 1024 * 1024)).toFixed(1) + " GB";
  if (bytes >= 1024 * 1024) return Math.round(bytes / (1024 * 1024)) + " MB";
  if (bytes >= 1024) return Math.round(bytes / 1024) + " KB";
  return bytes + " B";
}

/* --------------------------------- backup -------------------------------- */
const backupSection = {
  estimate: null,
  loading: true,
  init() { this.paint(); this.refresh(); },
  render() { this.paint(); },
  async refresh() {
    this.loading = true;
    try {
      this.estimate = await adminFetch("/api/admin/backup/estimate");
    } catch (err) {
      this.estimate = null;
    }
    this.loading = false;
    this.paint();
  },
  paint() {
    const body = document.getElementById("backup-body");
    if (!body) return;
    if (this.loading && this.estimate === null) {
      body.innerHTML = `<p class="hint"><span class="loader"></span>${esc(t("loading"))}</p>`;
      return;
    }
    const size = (value) => (value == null ? "" : " (~" + fmtSize(value) + ")");
    body.innerHTML = `
      <p class="row">
        <a class="btn" href="/api/admin/backup?kind=db">${esc(t("bk_db"))}${size(this.estimate && this.estimate.db)}</a>
        <a class="btn" href="/api/admin/backup?kind=full">${esc(t("bk_full"))}${size(this.estimate && this.estimate.full)}</a>
      </p>
      <p class="hint">${esc(t("bk_hint"))}</p>`;
  },
};
ADMIN_SECTIONS.push(backupSection);

/* -------------------------------- patches -------------------------------- */
const OUTCOME_CLASS = { new: "out-new", renamed: "out-renamed", duplicate: "out-dup" };

const patchSection = {
  uploads: [],
  staged: [],
  applied: [],
  reindex: null,
  timer: null,
  loadedOnce: false,
  init() { this.paint(); this.refresh(); },
  render() { this.paint(); },

  async refresh() {
    try {
      const data = await adminFetch("/api/admin/patches");
      this.staged = data.staged || [];
      this.applied = data.applied || [];
      this.reindex = data.reindex || null;
      this.loadedOnce = true;
    } catch (err) { /* keep the current view */ }
    this.paint();
    this.schedulePoll();
  },

  schedulePoll() {
    clearTimeout(this.timer);
    if (this.reindex && this.reindex.state === "running") {
      this.timer = setTimeout(() => this.refresh(), 2000);
    }
  },

  async uploadAll(input) {
    const files = Array.from(input.files || []);
    input.value = "";
    for (const file of files) await this.upload(file);
  },

  async upload(file) {
    const entry = { name: file.name, status: "uploading", payload: null, errors: [],
                    sent: 0, total: file.size, since: Date.now() };
    this.uploads.unshift(entry);
    this.paint();
    tickWhileBusy();
    try {
      entry.payload = await adminUpload("/api/admin/patches", file, "application/zip",
        (sent, total) => { entry.sent = sent; entry.total = total; this.paint(); },
        () => { entry.status = "checking"; entry.since = Date.now(); this.paint(); });
      entry.status = "preview";
    } catch (err) {
      entry.status = "error";
      entry.errors = (err.payload && err.payload.errors) || [err.message];
    }
    this.paint();
    this.refresh();
  },

  isBusy() {
    return !!this.applying || !!this.known
      || this.uploads.some((entry) => entry.status === "uploading" || entry.status === "checking");
  },

  async downloadKnown() {
    if (this.known) return;
    this.known = { since: Date.now(), received: 0, error: "", done: "" };
    this.paint();
    tickWhileBusy();
    let note = "";
    let error = "";
    try {
      const size = await adminDownload("/api/admin/known-hashes", "duosave-known-hashes.txt",
        (received) => { this.known.received = received; });
      note = t("pt_known_done").replace("{size}", fmtSize(size));
    } catch (err) {
      error = err.message;
    }
    this.known = null;
    this.knownNote = { text: error || note, ok: !error };
    this.paint();
  },

  async open(patchId) {
    try {
      const payload = await adminFetch("/api/admin/patches/" + patchId);
      this.uploads = this.uploads.filter((item) => !item.payload || item.payload.patch_id !== patchId);
      this.uploads.unshift({ name: patchId, status: "preview", payload, errors: [] });
    } catch (err) {
      window.alert(err.message);
    }
    this.paint();
  },

  async apply(patchId) {
    if (this.applying || !window.confirm(t("pt_apply_confirm"))) return;
    this.applying = { patchId, since: Date.now() };
    this.paint();
    tickWhileBusy();
    try {
      const result = await adminFetch("/api/admin/patches/" + patchId + "/apply", { method: "POST" });
      this.uploads = this.uploads.filter((item) => !item.payload || item.payload.patch_id !== patchId);
      const report = (result && result.report) || {};
      this.applyNote = { ok: true, text: t("pt_applied").replace("{id}", patchId)
        .replace("{files}", report.files_written || 0).replace("{touched}", report.touched || 0)
        .replace("{replaced}", (report.superseded || []).length) };
    } catch (err) {
      this.applyNote = { ok: false, text: patchId + ": " + err.message };
    }
    this.applying = null;
    this.refresh();
  },

  async discard(patchId) {
    if (!window.confirm(t("pt_discard_confirm"))) return;
    try {
      await adminFetch("/api/admin/patches/" + patchId, { method: "DELETE" });
      this.uploads = this.uploads.filter((item) => !item.payload || item.payload.patch_id !== patchId);
    } catch (err) {
      window.alert(err.message);
    }
    this.refresh();
  },

  paint() {
    const body = document.getElementById("patch-body");
    if (!body) return;
    if (!this.loadedOnce && !this.uploads.length) {
      body.innerHTML = `<p class="hint"><span class="loader"></span>${esc(t("loading"))}</p>`;
      return;
    }
    const chunks = [this.controlsMarkup()];
    if (this.applying) {
      chunks.push(`<p class="state-warn"><span class="loader"></span>${esc(t("pt_applying").replace("{id}", this.applying.patchId))} · ${esc(elapsed(this.applying.since))}</p>`);
    } else if (this.applyNote) {
      chunks.push(`<p class="${this.applyNote.ok ? "state-ok" : "state-bad"}">${esc(this.applyNote.text)}</p>`);
    }
    chunks.push(...this.uploads.map((entry) => this.uploadMarkup(entry)));
    if (this.reindex) chunks.push(this.reindexMarkup());
    if (this.staged.length) chunks.push(this.stagedMarkup());
    if (this.applied.length) chunks.push(this.historyMarkup());
    body.innerHTML = chunks.join("");
  },

  controlsMarkup() {
    const known = this.known
      ? `<p class="hint"><span class="loader"></span>${esc(t("pt_known_busy"))} · ${esc(elapsed(this.known.since))}${this.known.received ? " · " + esc(fmtSize(this.known.received)) : ""}</p>`
      : (this.knownNote ? `<p class="${this.knownNote.ok ? "state-ok" : "state-bad"}">${esc(this.knownNote.text)}</p>` : "");
    return `<p class="row">
        <button class="btn" ${this.known ? "disabled" : ""} onclick="patchSection.downloadKnown()">${esc(t("pt_known"))}</button>
        <label class="btn upload-pick" for="patch-file">${esc(t("pt_pick"))}</label>
        <input id="patch-file" type="file" accept=".zip" multiple hidden
               onchange="patchSection.uploadAll(this)">
      </p>
      ${known}
      <p class="hint">${esc(t("pt_known_hint"))}</p>`;
  },

  uploadMarkup(entry) {
    if (entry.status === "uploading") {
      const pct = entry.total ? Math.min(100, Math.round((entry.sent / entry.total) * 100)) : 0;
      return `<div class="patch-card"><div class="path"><span class="loader"></span>${esc(entry.name)} · ${esc(t("pt_uploading"))} ${pct}% (${esc(fmtSize(entry.sent))} / ${esc(fmtSize(entry.total))}) · ${esc(elapsed(entry.since))}</div>
        <div class="progress"><span style="width:${pct}%"></span></div></div>`;
    }
    if (entry.status === "checking") {
      return `<div class="patch-card"><div class="path"><span class="loader"></span>${esc(entry.name)} · ${esc(t("pt_checking"))} · ${esc(elapsed(entry.since))}</div>
        <div class="progress indeterminate"><span></span></div></div>`;
    }
    if (entry.status === "error") {
      const items = entry.errors.map((error) => `<li>${esc(error)}</li>`).join("");
      return `<div class="patch-card"><div class="path">${esc(entry.name)}</div>
        <div class="state-bad">${esc(t("pt_errors"))}:</div><ul class="errors">${items}</ul></div>`;
    }
    const payload = entry.payload;
    const summary = payload.summary || {};
    const chips = [
      [summary.new_files, "pt_new"], [summary.duplicates, "pt_dup"], [summary.renamed, "pt_renamed"],
      [summary.new_cards, "pt_new_cards"], [summary.existing_cards, "pt_existing_cards"],
      [summary.review, "pt_review"],
    ].map(([count, key]) => `<span class="badge">${count || 0} ${esc(t(key))}</span>`).join("");
    const rows = (payload.items || []).map((item) => this.itemRow(payload.patch_id, item)).join("");
    const already = payload.already_applied
      ? `<p class="state-warn">${esc(t("pt_already"))}</p>` : "";
    const disabled = payload.already_applied || this.applying ? "disabled" : "";
    return `<div class="patch-card">
      <div class="path">${esc(entry.name)} · <strong>${esc(payload.patch_id)}</strong></div>
      ${already}
      <div class="badges">${chips}</div>
      <table class="table">
        <thead><tr><th></th><th>${esc(t("pt_file"))}</th><th>${esc(t("pt_app"))}</th>
          <th>${esc(t("pt_pairs"))}</th><th>${esc(t("pt_outcome"))}</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
      <div class="row">
        <button class="btn ok" ${disabled} onclick="patchSection.apply('${esc(payload.patch_id)}')">${esc(t("pt_apply"))}</button>
        <button class="btn" onclick="patchSection.discard('${esc(payload.patch_id)}')">${esc(t("pt_discard"))}</button>
      </div></div>`;
  },

  itemRow(patchId, item) {
    const outcome = item.outcome;
    const label = { new: t("pt_new"), renamed: t("pt_renamed"), duplicate: t("pt_dup") }[outcome] || outcome;
    const thumb = outcome === "duplicate" ? ""
      : `<img class="thumb" loading="lazy" alt=""
             src="/api/admin/patches/${esc(patchId)}/files/${esc(item.file)}">`;
    const app = outcome === "duplicate" ? "" : `${esc(item.app || "")} · ${esc(item.language || "")}`;
    const pairs = (item.pairs || []).map((pair) =>
      `${esc(pair.original)} → ${esc(pair.translation)}${pair.card === "existing" ? " *" : ""}`
    ).join("<br>");
    const target = item.target && item.target !== item.file
      ? `<br><span class="muted">→ ${esc(item.target)}</span>` : "";
    return `<tr><td>${thumb}</td><td>${esc(item.file)}${target}</td><td>${app}</td>
      <td>${pairs}</td>
      <td><span class="badge ${OUTCOME_CLASS[outcome] || ""}">${esc(label)}</span></td></tr>`;
  },

  reindexMarkup() {
    const state = this.reindex.state;
    const label = t("pt_reindex_" + state);
    const detail = this.reindex.detail ? ": " + esc(this.reindex.detail) : "";
    const cls = state === "failed" ? "state-bad"
      : (state === "unavailable" ? "state-warn" : "state-ok");
    return `<p class="${cls}">${esc(label)}${detail}</p>`;
  },

  stagedMarkup() {
    const links = this.staged.map((item) =>
      `<a href="#" onclick="event.preventDefault(); patchSection.open('${esc(item.patch_id)}')">${esc(item.patch_id)}</a>`
    ).join(", ");
    return `<p class="path"><strong>${esc(t("pt_staged"))}:</strong> ${links}</p>`;
  },

  historyMarkup() {
    const rows = this.applied.map((item) => `<tr>
        <td>${esc(item.patch_id)}</td><td>${esc(item.applied_at || "")}</td>
        <td>${esc(item.applied_by || "—")}</td>
        <td>${esc(String((item.report && item.report.files_written) || 0))}</td></tr>`).join("");
    return `<table class="table"><thead><tr><th>${esc(t("pt_patch"))}</th><th>${esc(t("pt_when"))}</th>
      <th>${esc(t("pt_who"))}</th><th>${esc(t("pt_files"))}</th></tr></thead><tbody>${rows}</tbody></table>`;
  },
};
ADMIN_SECTIONS.push(patchSection);

/* ---------------------------------- cards --------------------------------- */

/* Options for the language picker of one card row; "unk" is a real target too. */
function cardLanguageOptions(selected) {
  const options = cardsSection.languages.map((language) => {
    const mark = language.code === selected ? " selected" : "";
    if (language.code === "unk") {
      return `<option value="unk"${mark}>${esc(t("lang_unknown"))}</option>`;
    }
    return `<option value="${esc(language.code)}"${mark}>${esc(language.code.toUpperCase())} — ${esc(language.name)}</option>`;
  });
  if (!options.length) {
    options.push(`<option value="${esc(selected)}" selected>${esc((selected || "").toUpperCase())}</option>`);
  }
  return options.join("");
}

const cardsSection = {
  query: "",
  items: [],
  languages: [],
  total: 0,
  note: "",
  noteOk: true,
  loadedOnce: false,
  init() { this.paint(); this.search(""); },
  render() { this.paint(); },

  async search(query) {
    this.query = (query || "").trim();
    try {
      const data = await adminFetch("/api/admin/cards?limit=20&q=" + encodeURIComponent(this.query));
      this.items = data.items || [];
      this.languages = data.languages || [];
      this.total = data.total || 0;
      this.note = "";
      this.loadedOnce = true;
    } catch (err) {
      this.items = [];
      this.total = 0;
      this.note = err.message;
      this.noteOk = false;
    }
    this.paint();
  },

  /* A delete that got no answer is retried once; 404 on the retry means the first one worked. */
  async deleteRequest(cardId) {
    const url = "/api/admin/cards/" + cardId;
    try {
      return await adminFetch(url, { method: "DELETE", timeoutMs: CARD_DELETE_TIMEOUT_MS });
    } catch (err) {
      if (!err.timeout) throw err;
      perfLog("warn", "retrying", "DELETE " + url);
      try {
        return await adminFetch(url, { method: "DELETE", timeoutMs: CARD_DELETE_TIMEOUT_MS });
      } catch (retryErr) {
        if (retryErr.status === 404) return { removed: [] };
        throw retryErr;
      }
    }
  },

  async remove(cardId) {
    const card = this.items.find((item) => item.id === cardId);
    if (!card || card.deleting || !window.confirm(t("cd_confirm"))) return;
    card.deleting = true;
    card.error = "";
    this.paintRow(card);
    try {
      const report = await this.deleteRequest(cardId);
      this.items = this.items.filter((item) => item.id !== cardId);
      this.total = Math.max(0, this.total - 1);
      this.note = t("cd_deleted").replace("{label}", card.original || String(cardId))
        .replace("{n}", (report.removed || []).length);
      this.noteOk = true;
      const row = document.getElementById("card-row-" + cardId);
      if (row) {
        row.classList.add("gone");
        setTimeout(() => this.paint(), 250);
      } else {
        this.paint();
      }
    } catch (err) {
      card.deleting = false;
      card.error = err.status === 404 ? t("cd_missing") : err.message;
      if (err.status === 404) this.items = this.items.filter((item) => item.id !== cardId);
      this.paint();
    }
  },

  /* Change one card's language; merging into the card that owns the pair drops the row. */
  async changeLanguage(cardId, language) {
    const card = this.items.find((item) => item.id === cardId);
    if (!card || card.saving || card.deleting || language === card.language) return;
    card.saving = true;
    card.error = "";
    this.paintRow(card);
    try {
      const report = await adminFetch("/api/admin/cards/" + cardId, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ language }),
      });
      card.saving = false;
      if (report.merged_into) {
        this.items = this.items.filter((item) => item.id !== cardId);
        this.total = Math.max(0, this.total - 1);
        this.note = t("cd_lang_merged").replace("{label}", card.original || String(cardId))
          .replace("{id}", String(report.merged_into));
      } else {
        card.language = report.language;
        this.note = t("cd_lang_changed").replace("{label}", card.original || String(cardId))
          .replace("{lang}", report.language.toUpperCase());
      }
      this.noteOk = true;
    } catch (err) {
      card.saving = false;
      card.error = err.status === 404 ? t("cd_missing") : err.message;
      if (err.status === 404) this.items = this.items.filter((item) => item.id !== cardId);
    }
    this.paint();
  },

  rowMarkup(card) {
    const action = card.deleting
      ? `<span class="muted"><span class="loader"></span>${esc(t("cd_deleting"))}</span>`
      : `<button class="btn bad" onclick="cardsSection.remove(${card.id})">${esc(t("cd_delete"))}</button>`;
    const picker = card.saving
      ? `<span class="muted"><span class="loader"></span></span>`
      : `<select class="lang-select" title="${esc(t("lang_label"))}"
                 onchange="cardsSection.changeLanguage(${card.id}, this.value)">${cardLanguageOptions(card.language)}</select>`;
    const error = card.error ? `<div class="state-bad">${esc(card.error)}</div>` : "";
    return `<tr id="card-row-${card.id}" class="${card.deleting ? "deleting" : ""}">
        <td>${picker}</td>
        <td>${esc(card.original)}<div class="muted">${esc(card.translation)}</div></td>
        <td>${esc(card.app || "")} · ${esc(card.status || "")}</td>
        <td>${action}${error}</td>
      </tr>`;
  },

  paintRow(card) {
    const row = document.getElementById("card-row-" + card.id);
    if (row) row.outerHTML = this.rowMarkup(card);
    else this.paint();
  },

  paint() {
    const body = document.getElementById("cards-body");
    if (!body) return;
    const rows = this.items.map((card) => this.rowMarkup(card)).join("");
    const table = rows
      ? `<table class="table"><thead><tr><th>${esc(t("cd_col_lang"))}</th><th>${esc(t("cd_col_card"))}</th>
           <th>${esc(t("cd_col_app"))}</th><th></th></tr></thead><tbody>${rows}</tbody></table>`
      : "";
    const found = this.items.length
      ? `<p class="hint">${esc(t("cd_found").replace("{n}", this.total))}</p>` : "";
    const note = this.note
      ? `<p class="${this.noteOk ? "state-ok" : "state-bad"}">${esc(this.note)}</p>` : "";
    const loading = this.loadedOnce ? "" : `<p class="hint"><span class="loader"></span>${esc(t("loading"))}</p>`;
    body.innerHTML = `
      <p class="row">
        <input id="cards-q" type="search" data-i18n-ph="cd_ph" placeholder="${esc(t("cd_ph"))}"
               value="${esc(this.query)}"
               onkeydown="if (event.key === 'Enter') cardsSection.search(this.value)">
        <button class="btn" onclick="cardsSection.search(document.getElementById('cards-q').value)">${esc(t("cd_search"))}</button>
      </p>
      <p class="hint">${esc(t("cd_hint"))}</p>
      ${loading}${note}${found}${table}`;
  },
};
ADMIN_SECTIONS.push(cardsSection);
