<script lang="ts">
  // What is wrong with the database and how to fix it: shown instead of the
  // app while the server answers "database unavailable", and as the
  // "#/database" page. The fixing parts (connection, restore) only work on the
  // host itself or for a signed-in admin; remote viewers get the explanation.
  import { onMount } from "svelte";
  import Modal from "./Modal.svelte";
  import { api, ApiError } from "../lib/api";
  import { dateTime } from "../lib/format";
  import { i18n, t, tDynamic } from "../lib/i18n.svelte";
  import { session } from "../lib/session.svelte";
  import { toasts } from "../lib/toast.svelte";
  import type { DbBackup, DbStatus, DbTestResult } from "../lib/types";

  interface Props {
    /** Called once the database is ready (the gate then loads the app). */
    onready?: () => void;
  }
  let { onready }: Props = $props();

  const POLL_MS = 2000;
  // States in which the server answers, so backups can be listed and restored.
  const SERVER_UP = ["schema_too_new", "migration_failed", "no_create_permission", "unknown"];
  const CONNECTION_STATES = [
    "connecting",
    "unreachable",
    "auth_failed",
    "auth_rejected",
    "no_create_permission",
    "unknown",
  ];

  let status = $state<DbStatus | null>(null);
  let healthState = $state<string | null>(null);
  let remote = $state(false);
  let serverDown = $state(false);
  let now = $state(Date.now());

  let form = $state({ host: "", port: 5432, user: "", password: "", name: "" });
  let formLoaded = false;
  let testResult = $state<DbTestResult | null>(null);
  let busy = $state(false);
  let failedSave = $state(false);

  let backups = $state<DbBackup[] | null>(null);
  let backupDir = $state("");
  let pgRestore = $state<string | null>(null);
  let restoreTarget = $state<DbBackup | null>(null);
  let restoreConfirm = $state("");
  let restoring = $state(false);

  const dbState = $derived(status?.state ?? healthState ?? "connecting");
  const ready = $derived(dbState === "ready");
  const steps = $derived(
    tDynamic(`db.state.${dbState}.steps`, "")
      .split("\n")
      .filter((s) => s.trim()),
  );
  const retryIn = $derived(
    status?.next_retry_at
      ? Math.max(0, Math.round((Date.parse(status.next_retry_at) - now) / 1000))
      : null,
  );
  const showConnection = $derived(
    !!status && status.can_reconfigure && CONNECTION_STATES.includes(dbState),
  );
  const showBackups = $derived(!!status && (ready || SERVER_UP.includes(dbState)));

  function title(s: string): string {
    return tDynamic(`db.state.${s}.title`, s);
  }

  async function poll(): Promise<void> {
    try {
      if (!remote) {
        status = await api<DbStatus>("/api/db/status");
        if (!formLoaded) {
          const c = status.connection;
          form = { host: c.host, port: c.port, user: c.user, password: "", name: c.name };
          formLoaded = true;
        }
      } else {
        const health = await api<{ database: { state: string } }>("/api/health");
        healthState = health.database.state;
      }
      serverDown = false;
    } catch (e) {
      if (e instanceof ApiError && (e.status === 401 || e.status === 403)) {
        remote = true;
        return poll();
      }
      serverDown = e instanceof ApiError && e.status === 0;
    }
    if (ready && onready) {
      session.dbRecovered();
      onready();
    }
  }

  async function loadBackups(): Promise<void> {
    try {
      const res = await api<{ directory: string; pg_restore: string | null; items: DbBackup[] }>(
        "/api/db/backups",
      );
      backups = res.items;
      backupDir = res.directory;
      pgRestore = res.pg_restore;
    } catch (e) {
      toasts.error(e);
    }
  }

  onMount(() => {
    void poll();
    const timer = setInterval(() => void poll(), POLL_MS);
    const clock = setInterval(() => (now = Date.now()), 1000);
    return () => {
      clearInterval(timer);
      clearInterval(clock);
    };
  });

  // Backups need the server; load them once it answers.
  $effect(() => {
    if (showBackups && backups === null) void loadBackups();
  });

  async function retry(): Promise<void> {
    try {
      await api("/api/db/retry", { method: "POST" });
      setTimeout(() => void poll(), 400);
    } catch (e) {
      toasts.error(e);
    }
  }

  function connectionBody(force = false) {
    return {
      host: form.host,
      port: Number(form.port),
      user: form.user,
      password: form.password === "" ? null : form.password,
      name: form.name,
      force,
    };
  }

  async function testConnection(): Promise<void> {
    busy = true;
    try {
      testResult = await api<DbTestResult>("/api/db/test-connection", {
        method: "POST",
        body: connectionBody(),
      });
    } catch (e) {
      toasts.error(e);
    } finally {
      busy = false;
    }
  }

  async function saveConnection(force = false): Promise<void> {
    busy = true;
    try {
      const res = await api<{ saved: boolean; test: DbTestResult; env_overrides?: string[] }>(
        "/api/db/connection",
        { method: "PUT", body: connectionBody(force) },
      );
      testResult = res.test;
      failedSave = !res.saved;
      if (res.saved) {
        form.password = "";
        toasts.ok(t("db.conn.saved", { path: status?.config_file ?? "config.toml" }));
        setTimeout(() => void poll(), 500);
      }
    } catch (e) {
      toasts.error(e);
    } finally {
      busy = false;
    }
  }

  async function createBackup(): Promise<void> {
    busy = true;
    try {
      const res = await api<{ file: string }>("/api/db/backups", { method: "POST" });
      toasts.ok(t("db.backups.created", { file: res.file }));
      await loadBackups();
    } catch (e) {
      toasts.error(e);
    } finally {
      busy = false;
    }
  }

  async function restore(): Promise<void> {
    if (!restoreTarget) return;
    restoring = true;
    try {
      await api("/api/db/restore", {
        method: "POST",
        body: { file: restoreTarget.file, confirm: restoreConfirm },
      });
      toasts.ok(t("db.restore.done", { file: restoreTarget.file }));
      restoreTarget = null;
      restoreConfirm = "";
      await poll();
    } catch (e) {
      toasts.error(e);
    } finally {
      restoring = false;
    }
  }

  function size(bytes: number): string {
    if (bytes >= 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
    return `${Math.max(1, Math.round(bytes / 1024))} kB`;
  }

  function kind(b: DbBackup): string {
    if (b.kind === "update") return t("db.backups.kind.update", { version: b.before_version ?? "?" });
    return tDynamic(`db.backups.kind.${b.kind}`, b.kind);
  }
</script>

<div class="db">
  <header class="panel head" class:ok={ready} class:blocking={dbState === "schema_too_new" || dbState === "migration_failed"}>
    <div class="row">
      <span class="dot {ready ? 'ok' : dbState === 'connecting' || dbState === 'restoring' ? 'warn' : 'bad'}"></span>
      <h1>{serverDown ? t("db.server_down") : title(dbState)}</h1>
    </div>
    {#if !ready}
      <p class="muted">{t("db.subtitle")}</p>
    {/if}
    {#if tDynamic(`db.state.${dbState}.hint`, "")}
      <p>{tDynamic(`db.state.${dbState}.hint`, "")}</p>
    {/if}
    {#if dbState === "schema_too_new" && status?.extra.db_revision}
      <p class="mono small">
        {t("db.versions", { db: status.extra.db_revision, app: status.extra.app_head ?? "?" })}
        {#if status.extra.migrated_by}· {t("db.migrated_by", { version: status.extra.migrated_by })}{/if}
      </p>
    {/if}
    {#if !ready && status}
      <div class="row small muted">
        <span>{t("db.attempts", { n: status.attempts })}</span>
        {#if retryIn !== null}<span>· {t("db.next_retry", { s: retryIn })}</span>{/if}
        <span class="spacer"></span>
        <button onclick={retry}>{t("db.retry")}</button>
      </div>
    {/if}
  </header>

  {#if remote && !ready}
    <p class="panel">{t("db.remote")}</p>
  {/if}

  {#if steps.length && !remote}
    <section class="panel">
      <h2>{t("db.steps")}</h2>
      <ol class="steps">
        {#each steps as step (step)}<li>{step}</li>{/each}
      </ol>
      {#if dbState === "schema_too_new" || dbState === "migration_failed"}
        <a class="button" href="#/updates">{t("db.open_updates")}</a>
      {/if}
    </section>
  {/if}

  {#if status?.detail}
    <details class="panel">
      <summary>{t("db.details")}</summary>
      <pre class="mono small">{status.detail}</pre>
      <p class="small muted mono">{status.connection.user}@{status.connection.host}:{status.connection.port}/{status.connection.name} · {status.config_file}</p>
    </details>
  {/if}

  {#if showConnection}
    <section class="panel">
      <h2>{t("db.conn.title")}</h2>
      {#if status?.env_overrides.length}
        <p class="error-box small">{t("db.conn.env", { keys: status.env_overrides.join(", ") })}</p>
      {/if}
      <form
        class="form-grid"
        onsubmit={(e) => {
          e.preventDefault();
          void saveConnection();
        }}
      >
        <label class="field">{t("db.conn.host")}<input bind:value={form.host} required autocomplete="off" /></label>
        <label class="field">{t("db.conn.port")}<input type="number" min="1" max="65535" bind:value={form.port} required /></label>
        <label class="field">{t("db.conn.user")}<input bind:value={form.user} required autocomplete="off" /></label>
        <label class="field">
          {t("db.conn.password")}
          <input
            type="password"
            bind:value={form.password}
            placeholder={status?.connection.has_password ? t("db.conn.password_keep") : ""}
            autocomplete="new-password"
          />
        </label>
        <label class="field">{t("db.conn.name")}<input bind:value={form.name} required autocomplete="off" /></label>
        <div class="row actions">
          <button type="button" disabled={busy} onclick={testConnection}>{t("db.conn.test")}</button>
          <button type="submit" class="primary" disabled={busy}>{t("db.conn.save")}</button>
          {#if failedSave}
            <button type="button" class="danger" disabled={busy} onclick={() => saveConnection(true)}>{t("db.conn.force")}</button>
          {/if}
        </div>
      </form>
      {#if testResult}
        <p class={testResult.ok ? "ok-box small" : "error-box small"}>
          {#if testResult.ok}
            {t(testResult.database_exists === false ? "db.conn.ok_missing" : "db.conn.ok", { detail: testResult.detail })}
          {:else}
            {t("db.conn.failed", { title: title(testResult.state) })}
            <br /><span class="mono">{testResult.detail}</span>
          {/if}
        </p>
      {/if}
    </section>
  {/if}

  {#if showBackups && backups !== null}
    <section class="panel">
      <div class="row">
        <h2>{t("db.backups.title")}</h2>
        <span class="spacer"></span>
        <button disabled={busy} onclick={createBackup}>{t("db.backups.create")}</button>
      </div>
      {#if status?.can_restore}
        <p class="hint">{t("db.backups.intro")}</p>
        {#if !pgRestore}<p class="error-box small">{t("db.backups.no_tool")}</p>{/if}
      {/if}
      {#if backups.length === 0}
        <p class="muted">{t("db.backups.none", { dir: backupDir })}</p>
      {:else}
        <div class="table-wrap">
          <table class="table-cards">
            <thead>
              <tr>
                <th>{t("db.backups.date")}</th>
                <th>{t("db.backups.kind")}</th>
                <th>{t("db.backups.schema")}</th>
                <th class="num">{t("db.backups.size")}</th>
                {#if status?.can_restore}<th></th>{/if}
              </tr>
            </thead>
            <tbody>
              {#each backups as b (b.file)}
                <tr>
                  <td data-label={t("db.backups.date")} title={b.file}>{dateTime(b.created_at, i18n.locale)}</td>
                  <td data-label={t("db.backups.kind")}>{kind(b)}</td>
                  <td data-label={t("db.backups.schema")}>
                    <span class="mono">{b.revision ?? "–"}</span>
                    {#if b.compatible === true}
                      <span class="badge ok">{t("db.backups.compatible")}</span>
                    {:else if b.compatible === false}
                      <span class="badge bad">{t("db.backups.incompatible")}</span>
                    {:else}
                      <span class="badge">{t("db.backups.unknown")}</span>
                    {/if}
                  </td>
                  <td class="num" data-label={t("db.backups.size")}>{size(b.size)}</td>
                  {#if status?.can_restore}
                    <td class="num">
                      <button
                        class="danger"
                        disabled={!pgRestore || b.compatible === false}
                        title={b.compatible === false ? t("db.restore.incompatible") : ""}
                        onclick={() => {
                          restoreTarget = b;
                          restoreConfirm = "";
                        }}>{t("db.backups.restore")}</button
                      >
                    </td>
                  {/if}
                </tr>
              {/each}
            </tbody>
          </table>
        </div>
      {/if}
      {#if status?.aside_databases.length}
        <h2 class="aside-title">{t("db.aside.title")}</h2>
        <ul class="mono small">
          {#each status.aside_databases as name (name)}<li>{name}</li>{/each}
        </ul>
        <p class="hint">{t("db.aside.hint")}</p>
      {/if}
    </section>
  {/if}
</div>

{#if restoreTarget && status}
  <Modal title={t("db.restore.title")} onclose={() => !restoring && (restoreTarget = null)}>
    <p>{t("db.restore.text", { name: status.connection.name, file: restoreTarget.file })}</p>
    <label class="field">
      {t("db.restore.confirm_label", { name: status.connection.name })}
      <input bind:value={restoreConfirm} autocomplete="off" disabled={restoring} />
    </label>
    {#if restoring}<p class="muted">{t("db.restore.running")}</p>{/if}
    {#snippet footer()}
      <button disabled={restoring} onclick={() => (restoreTarget = null)}>{t("common.cancel")}</button>
      <button
        class="danger"
        disabled={restoring || restoreConfirm.trim() !== status?.connection.name}
        onclick={restore}>{t("db.backups.restore")}</button
      >
    {/snippet}
  </Modal>
{/if}

<style>
  .db {
    display: grid;
    gap: 12px;
    max-width: 920px;
  }
  .head h1 {
    margin: 0;
  }
  .head p {
    margin: 8px 0 0;
  }
  .head .row.small {
    margin-top: 10px;
  }
  .head.blocking {
    border-color: #7f1d1d;
  }
  .head.ok {
    border-color: #14532d;
  }
  .steps {
    margin: 0 0 12px;
    padding-left: 20px;
    display: grid;
    gap: 6px;
  }
  summary {
    cursor: pointer;
    color: var(--muted);
  }
  pre {
    white-space: pre-wrap;
    word-break: break-word;
    margin: 10px 0 6px;
  }
  .actions {
    grid-column: 1 / -1;
  }
  .ok-box {
    border: 1px solid #14532d;
    background: #0f2417;
    color: #bbf7d0;
    border-radius: 8px;
    padding: 8px 12px;
  }
  .aside-title {
    margin-top: 16px;
  }
</style>
