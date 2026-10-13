/* Maintenance page: local-listener only. Extends the shared I18N and helpers from app.js. */
"use strict";

Object.assign(I18N.ru, {
  adm_patches: "Импорт патча",
  adm_backup: "Бэкап",
  adm_busy: "Выполняется другая операция…",
  adm_error: "Ошибка",
  adm_confirm: "Подтвердить?",
  bk_db: "Скачать: только БД",
  bk_full: "Скачать: полный",
  bk_hint: "Восстановление — README, раздел «Бэкап и восстановление».",
  pt_known: "Скачать список известных картинок",
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
});
Object.assign(I18N.en, {
  adm_patches: "Patch import",
  adm_backup: "Backup",
  adm_busy: "Another operation is in progress…",
  adm_error: "Error",
  adm_confirm: "Confirm?",
  bk_db: "Download: DB only",
  bk_full: "Download: full",
  bk_hint: "Restore instructions — README, “Backup and restore”.",
  pt_known: "Download the known-images list",
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
});

/* fetch with the CSRF header on mutations; throws Error with .status/.payload on failures */
async function adminFetch(url, opts) {
  const options = Object.assign({}, opts || {});
  if (options.method && options.method !== "GET") {
    options.headers = Object.assign({}, options.headers, { "X-Duosave-Request": "1" });
  }
  const res = await fetch(url, options);
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
  init() { this.refresh(); },
  render() { this.paint(); },
  async refresh() {
    try {
      this.estimate = await adminFetch("/api/admin/backup/estimate");
    } catch (err) {
      this.estimate = null;
    }
    this.paint();
  },
  paint() {
    const body = document.getElementById("backup-body");
    if (!body) return;
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
  init() { this.refresh(); },
  render() { this.paint(); },

  async refresh() {
    try {
      const data = await adminFetch("/api/admin/patches");
      this.staged = data.staged || [];
      this.applied = data.applied || [];
      this.reindex = data.reindex || null;
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
    const entry = { name: file.name, status: "uploading", payload: null, errors: [] };
    this.uploads.unshift(entry);
    this.paint();
    try {
      entry.payload = await adminFetch("/api/admin/patches", {
        method: "POST", body: file, headers: { "Content-Type": "application/zip" },
      });
      entry.status = "preview";
    } catch (err) {
      entry.status = "error";
      entry.errors = (err.payload && err.payload.errors) || [err.message];
    }
    this.paint();
    this.refresh();
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
    if (!window.confirm(t("pt_apply_confirm"))) return;
    try {
      await adminFetch("/api/admin/patches/" + patchId + "/apply", { method: "POST" });
      this.uploads = this.uploads.filter((item) => !item.payload || item.payload.patch_id !== patchId);
    } catch (err) {
      window.alert(err.message);
    }
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
    const chunks = [this.controlsMarkup()];
    chunks.push(...this.uploads.map((entry) => this.uploadMarkup(entry)));
    if (this.reindex) chunks.push(this.reindexMarkup());
    if (this.staged.length) chunks.push(this.stagedMarkup());
    if (this.applied.length) chunks.push(this.historyMarkup());
    body.innerHTML = chunks.join("");
  },

  controlsMarkup() {
    return `<p class="row">
        <a class="btn" href="/api/admin/known-hashes">${esc(t("pt_known"))}</a>
        <input id="patch-file" type="file" accept=".zip" multiple
               onchange="patchSection.uploadAll(this)">
      </p>
      <p class="hint">${esc(t("pt_known_hint"))}</p>`;
  },

  uploadMarkup(entry) {
    if (entry.status === "uploading") {
      return `<div class="patch-card"><div class="path">${esc(entry.name)} · ${esc(t("pt_uploading"))}</div></div>`;
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
    const disabled = payload.already_applied ? "disabled" : "";
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
