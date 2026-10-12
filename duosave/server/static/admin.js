/* Maintenance page: local-listener only. Extends the shared I18N and helpers from app.js. */
"use strict";

Object.assign(I18N.ru, {
  adm_update: "Версия и обновление",
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
  up_site: "Сайт",
  up_remote: "GitHub",
  up_worktree: "Рабочая копия",
  up_runner: "Исполнитель",
  up_runner_ok: "работает",
  up_runner_off: "не отвечает — см. README, «Обновление по кнопке»",
  up_behind: "опережает на {n}",
  up_uptodate: "актуально",
  up_checked: "проверено {time}",
  up_dirty: "есть незакоммиченные правки",
  up_clean: "чисто",
  up_check: "Проверить обновления",
  up_update: "Обновить",
  up_confirm: "Обновить сайт? Будет выполнен git pull, сборка образа и перезапуск контейнера.",
  up_restarting: "Перезапуск…",
  up_last: "Последнее задание",
  up_state_queued: "в очереди",
  up_state_running: "выполняется",
  up_state_succeeded: "успешно",
  up_state_noop: "уже актуально",
  up_state_failed: "ошибка",
  up_state_rolled_back: "откат выполнен",
  up_state_rollback_failed: "откат не удался",
  up_reason_fetch_failed: "нет связи с GitHub",
  up_reason_wrong_branch: "рабочая копия не на целевой ветке",
  up_reason_not_fast_forward: "история разошлась или есть конфликтующие правки",
  up_reason_unpushed_commits: "есть неотправленные коммиты",
  up_reason_docker_unavailable: "Docker Desktop не запущен",
  up_reason_build_failed: "сборка образа упала",
  up_reason_compose_failed: "контейнер не пересоздался",
  up_reason_unhealthy: "новый контейнер не прошёл проверку здоровья",
  up_reason_rollback_failed: "откат не удался — проверьте README",
  up_reason_interrupted: "задание прервано",
  up_step_fetch: "git fetch",
  up_step_verify: "проверка ветки",
  up_step_merge: "git merge --ff-only",
  up_step_compare: "сравнение с контейнером",
  up_step_snapshot: "снимок БД",
  up_step_worktree: "чистое дерево сборки",
  up_step_build: "сборка образа",
  up_step_restart: "перезапуск контейнера",
  up_step_health: "проверка здоровья",
  up_step_rollback: "откат",
  up_step_cleanup: "уборка",
  up_log: "Журнал",
});
Object.assign(I18N.en, {
  adm_update: "Version and update",
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
  up_site: "Site",
  up_remote: "GitHub",
  up_worktree: "Working copy",
  up_runner: "Updater",
  up_runner_ok: "running",
  up_runner_off: "not responding — see README, “Update by button”",
  up_behind: "{n} commit(s) ahead",
  up_uptodate: "up to date",
  up_checked: "checked {time}",
  up_dirty: "uncommitted changes",
  up_clean: "clean",
  up_check: "Check for updates",
  up_update: "Update",
  up_confirm: "Update the site? This runs git pull, builds the image and restarts the container.",
  up_restarting: "Restarting…",
  up_last: "Last job",
  up_state_queued: "queued",
  up_state_running: "running",
  up_state_succeeded: "succeeded",
  up_state_noop: "already up to date",
  up_state_failed: "failed",
  up_state_rolled_back: "rolled back",
  up_state_rollback_failed: "rollback failed",
  up_reason_fetch_failed: "GitHub is unreachable",
  up_reason_wrong_branch: "the working copy is not on the target branch",
  up_reason_not_fast_forward: "diverged history or conflicting local changes",
  up_reason_unpushed_commits: "there are unpushed commits",
  up_reason_docker_unavailable: "Docker Desktop is not running",
  up_reason_build_failed: "the image build failed",
  up_reason_compose_failed: "the container was not recreated",
  up_reason_unhealthy: "the new container did not become healthy",
  up_reason_rollback_failed: "rollback failed — see README",
  up_reason_interrupted: "the job was interrupted",
  up_step_fetch: "git fetch",
  up_step_verify: "branch check",
  up_step_merge: "git merge --ff-only",
  up_step_compare: "compare with the container",
  up_step_snapshot: "DB snapshot",
  up_step_worktree: "clean build tree",
  up_step_build: "image build",
  up_step_restart: "container restart",
  up_step_health: "health check",
  up_step_rollback: "rollback",
  up_step_cleanup: "cleanup",
  up_log: "Log",
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

/* --------------------------------- update -------------------------------- */
const updateSection = {
  data: null,
  busy: false,
  restarting: false,
  before: null,
  timer: null,
  init() { this.refresh(); },
  render() { this.paint(); },

  async refresh() {
    if (this.restarting) return this.pollRestart();
    try {
      this.data = await adminFetch("/api/admin/update");
    } catch (err) {
      if (this.busy) this.restarting = true;
    }
    this.paint();
    this.schedule();
  },

  async pollRestart() {
    try {
      const info = await fetchJson("/api/version");
      if (this.before && info.commit && info.commit !== this.before) {
        window.location.reload();
        return;
      }
    } catch (err) { /* the container is still restarting */ }
    this.paint();
    this.schedule();
  },

  schedule() {
    clearTimeout(this.timer);
    const job = this.data && this.data.status && this.data.status.job;
    const running = this.restarting || this.busy || (this.data && this.data.pending)
      || (job && job.state === "running");
    this.timer = setTimeout(() => this.refresh(), running ? 2000 : 15000);
  },

  async request(action) {
    if (action === "update" && !window.confirm(t("up_confirm"))) return;
    this.before = this.data && this.data.site ? this.data.site.commit : null;
    this.busy = true;
    this.paint();
    try {
      await adminFetch("/api/admin/update", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action }),
      });
    } catch (err) {
      window.alert(err.message);
    }
    this.busy = false;
    this.refresh();
  },

  remoteText(repo) {
    if (!repo || !repo.remote) return "—";
    const checked = repo.fetched_at ? " · " + esc(t("up_checked").replace("{time}", fmtTime(repo.fetched_at))) : "";
    if (repo.fetch_error) return `<span class="state-bad">${esc(repo.fetch_error)}</span>`;
    if (repo.behind > 0) {
      return `<span class="state-warn">${esc(t("up_behind").replace("{n}", repo.behind))}</span>${checked}`;
    }
    return `<span class="state-ok">${esc(t("up_uptodate"))}</span>${checked}`;
  },

  worktreeText(repo) {
    if (!repo || !repo.head) return "—";
    const dirty = repo.dirty ? t("up_dirty") : t("up_clean");
    return `${esc(repo.head.slice(0, 7))} · ${esc(dirty)}`;
  },

  jobText(job) {
    if (!job) return "";
    const state = t("up_state_" + job.state) || job.state;
    const reason = job.reason ? ` · ${esc(t("up_reason_" + job.reason) || job.reason)}` : "";
    const step = job.state === "running" && job.step
      ? ` · ${esc(t("up_step_" + job.step) || job.step)}` : "";
    const cls = job.state === "succeeded" || job.state === "noop" ? "state-ok"
      : (job.state === "running" || job.state === "queued" ? "state-warn" : "state-bad");
    const when = job.finished_at || job.started_at || "";
    return `<p class="${cls}">${esc(state)}${reason}${step}
      <span class="muted">· ${esc(when)}</span></p>`;
  },

  paint() {
    const body = document.getElementById("update-body");
    if (!body) return;
    if (this.restarting) {
      body.innerHTML = `<p class="state-warn">${esc(t("up_restarting"))}</p>`;
      return;
    }
    if (!this.data) {
      body.innerHTML = `<p class="state-bad">${esc(t("up_runner_off"))}</p>`;
      return;
    }
    const status = this.data.status || {};
    const repo = status.repo || {};
    const deployed = status.deployed || {};
    const job = status.job || null;
    const alive = this.data.runner_alive;
    const busy = this.busy || (job && job.state === "running") || this.data.pending;
    const upToDate = Boolean(repo.remote && deployed.commit === repo.remote);
    const rows = [
      [t("up_site"), `v${esc(this.data.site.version)} · ${esc((this.data.site.commit || "").slice(0, 7))}`],
      [t("up_remote"), this.remoteText(repo)],
      [t("up_worktree"), this.worktreeText(repo)],
      [t("up_runner"), alive ? esc(t("up_runner_ok")) : `<span class="state-bad">${esc(t("up_runner_off"))}</span>`],
    ].map(([key, value]) => `<dt>${esc(key)}</dt><dd>${value}</dd>`).join("");
    const check = `<button class="btn" ${busy ? "disabled" : ""}
      onclick="updateSection.request('check')">${esc(t("up_check"))}</button>`;
    const update = `<button class="btn accent" ${(busy || !alive || upToDate) ? "disabled" : ""}
      onclick="updateSection.request('update')">${esc(t("up_update"))}</button>`;
    const log = (this.data.log_tail || []).slice(-40).join("\n");
    body.innerHTML = `<dl class="kv">${rows}</dl>
      <p class="row">${check}${update}</p>
      ${job ? `<div class="path">${esc(t("up_last"))}:</div>${this.jobText(job)}` : ""}
      ${log ? `<div class="path">${esc(t("up_log"))}:</div><pre class="log">${esc(log)}</pre>` : ""}`;
  },
};
ADMIN_SECTIONS.push(updateSection);

function fmtTime(iso) {
  const date = new Date(iso);
  if (isNaN(date.getTime())) return iso;
  const pad = (n) => String(n).padStart(2, "0");
  return `${pad(date.getHours())}:${pad(date.getMinutes())}`;
}
