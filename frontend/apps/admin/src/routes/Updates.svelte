<script lang="ts">
  // Updates from GitHub releases: check, read notes, install with a click
  // (database backup first), or pick another (older) version.
  import { onMount } from "svelte";
  import Modal from "../components/Modal.svelte";
  import { api, ApiError } from "../lib/api";
  import { dateTime } from "../lib/format";
  import { i18n, t, type MessageKey } from "../lib/i18n.svelte";
  import { toasts } from "../lib/toast.svelte";

  interface ReleaseInfo {
    version: string;
    tag: string;
    prerelease: boolean;
    published_at: string | null;
    notes: string;
    url: string;
    installable: boolean;
    is_current?: boolean;
    is_downgrade?: boolean;
  }
  interface UpdateState {
    current: string;
    latest: ReleaseInfo | null;
    update_available: boolean;
    last_check: string | null;
    check_error: string | null;
    status: string;
    status_detail: string | null;
    progress: number | null;
    last_backup: string | null;
    can_install: boolean;
    enabled: boolean;
    channel: string;
    source: string;
    live_games: number;
  }

  const BUSY = new Set(["checking", "downloading", "verifying", "backing_up", "installing"]);

  let info = $state<UpdateState | null>(null);
  let releases = $state<ReleaseInfo[] | null>(null);
  let showOther = $state(false);
  let checking = $state(false);
  // Install dialog: the release, then (if games run) the second question.
  let target = $state<ReleaseInfo | null>(null);
  let skipBackup = $state(false);
  let askRunning = $state<number | null>(null);
  let installing = $state(false);
  let poll: ReturnType<typeof setInterval> | null = null;

  async function load(): Promise<void> {
    try {
      info = await api<UpdateState>("/api/updates");
    } catch (e) {
      // While the installer replaces the app the server goes away: expected.
      if (info?.status !== "installing") toasts.error(e);
    }
    const busy = info ? BUSY.has(info.status) : false;
    if (busy && !poll) poll = setInterval(() => void load(), 1500);
    if (!busy && poll) {
      clearInterval(poll);
      poll = null;
    }
  }

  async function check(): Promise<void> {
    checking = true;
    try {
      info = await api<UpdateState>("/api/updates/check", { method: "POST" });
      if (showOther) releases = await api<ReleaseInfo[]>("/api/updates/releases");
    } catch (e) {
      toasts.error(e);
    } finally {
      checking = false;
    }
  }

  async function saveSettings(change: { channel?: string; enabled?: boolean }): Promise<void> {
    try {
      info = await api<UpdateState>("/api/updates/settings", { method: "PUT", body: change });
      if (showOther) releases = await api<ReleaseInfo[]>("/api/updates/releases");
    } catch (e) {
      toasts.error(e);
      void load();
    }
  }

  async function toggleOther(): Promise<void> {
    showOther = !showOther;
    if (showOther && releases === null) {
      try {
        releases = await api<ReleaseInfo[]>("/api/updates/releases");
      } catch (e) {
        toasts.error(e);
      }
    }
  }

  function ask(release: ReleaseInfo): void {
    target = release;
    skipBackup = false;
    askRunning = null;
  }

  async function install(confirmRunning: boolean): Promise<void> {
    if (!target) return;
    installing = true;
    try {
      info = await api<UpdateState>("/api/updates/install", {
        method: "POST",
        body: { version: target.version, confirm_running: confirmRunning, skip_backup: skipBackup },
      });
      target = null;
      askRunning = null;
    } catch (e) {
      if (e instanceof ApiError && e.code === "games_running") {
        askRunning = info?.live_games || 1;
      } else {
        toasts.error(e);
        target = null;
      }
    } finally {
      installing = false;
      void load();
    }
  }

  function statusText(s: UpdateState): string {
    if (s.status === "error") return t("updates.status.error", { detail: s.status_detail ?? "" });
    const text = t(`updates.status.${s.status}` as MessageKey);
    return s.progress !== null && s.status === "downloading" ? `${text} ${Math.round(s.progress * 100)} %` : text;
  }

  onMount(() => {
    void load();
    return () => {
      if (poll) clearInterval(poll);
    };
  });
</script>

<h1>{t("updates.title")}</h1>
{#if info}
  <p class="hint">{t("updates.intro", { source: info.source })}</p>

  <section class="panel block">
    <div class="facts">
      <div>
        <span class="label">{t("updates.current")}</span>
        <strong class="mono">{info.current}</strong>
      </div>
      <div>
        <span class="label">{t("updates.latest")}</span>
        <strong class="mono">{info.latest?.version ?? "–"}</strong>
        {#if info.latest?.prerelease}<span class="badge warn">{t("updates.prerelease")}</span>{/if}
      </div>
      <div>
        <span class="label">{t("updates.last_check")}</span>
        <span>{info.last_check ? dateTime(info.last_check, i18n.locale) : t("updates.never")}</span>
      </div>
      <div class="status">
        {#if info.update_available}
          <span class="badge ok big-badge">{t("updates.available")}</span>
        {:else if info.latest}
          <span class="badge">{t("updates.up_to_date")}</span>
        {/if}
      </div>
    </div>
    <div class="row actions">
      <button onclick={check} disabled={checking || BUSY.has(info.status)}>{t("updates.check")}</button>
      {#if info.update_available && info.latest}
        <button
          class="primary"
          disabled={!info.can_install || BUSY.has(info.status) || !info.latest.installable}
          onclick={() => info?.latest && ask(info.latest)}
        >
          {t("updates.install_version", { version: info.latest.version })}
        </button>
      {/if}
      <span class="spacer"></span>
      <label class="check small">
        <input type="checkbox" checked={info.channel === "beta"} onchange={(e) => saveSettings({ channel: e.currentTarget.checked ? "beta" : "stable" })} />
        {t("updates.beta")}
      </label>
      <label class="check small">
        <input type="checkbox" checked={info.enabled} onchange={(e) => saveSettings({ enabled: e.currentTarget.checked })} />
        {t("updates.auto")}
      </label>
    </div>
    {#if info.check_error}<p class="warn-text small">{t("updates.offline", { error: info.check_error })}</p>{/if}
    {#if !info.can_install}<p class="muted small">{t("updates.dev_mode")}</p>{/if}
    {#if info.status !== "idle"}
      <p class={info.status === "error" ? "error-box" : "info-box"}>{statusText(info)}</p>
    {/if}
    {#if info.last_backup}<p class="muted small mono">{t("updates.last_backup", { path: info.last_backup })}</p>{/if}
  </section>

  {#if info.update_available && info.latest}
    <section class="panel block">
      <h2>{t("updates.notes")} – {info.latest.version}</h2>
      {#if info.latest.notes.trim()}
        <pre class="notes">{info.latest.notes}</pre>
      {:else}
        <p class="muted">{t("updates.no_notes")}</p>
      {/if}
      <a class="small" href={info.latest.url} target="_blank" rel="noopener">GitHub ↗</a>
    </section>
  {/if}

  <section class="panel block">
    <button class="link" onclick={toggleOther}>{showOther ? t("updates.hide_other") : t("updates.other")}</button>
    {#if showOther && releases}
      <table>
        <tbody>
          {#each releases as r (r.version)}
            <tr>
              <td class="mono">{r.version}</td>
              <td>
                {#if r.is_current}<span class="badge ok">{t("updates.installed_badge")}</span>{/if}
                {#if r.prerelease}<span class="badge warn">{t("updates.prerelease")}</span>{/if}
                {#if r.is_downgrade}<span class="badge">{t("updates.downgrade")}</span>{/if}
                {#if !r.installable}<span class="badge">{t("updates.not_installable")}</span>{/if}
              </td>
              <td class="muted small">{r.published_at ? dateTime(r.published_at, i18n.locale) : ""}</td>
              <td class="right">
                <button
                  disabled={!info.can_install || r.is_current || !r.installable || BUSY.has(info.status)}
                  onclick={() => ask(r)}>{t("updates.install")}</button
                >
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    {/if}
  </section>
{:else}
  <p class="muted">{t("common.loading")}</p>
{/if}

{#if target && askRunning === null}
  <Modal title={t("updates.confirm_title", { version: target.version })} onclose={() => (target = null)}>
    <p>{t("updates.confirm_text")}</p>
    {#if target.is_downgrade}<p class="warn-text">{t("updates.confirm_downgrade")}</p>{/if}
    <label class="check"><input type="checkbox" bind:checked={skipBackup} /> {t("updates.skip_backup")}</label>
    {#snippet footer()}
      <button onclick={() => (target = null)}>{t("common.cancel")}</button>
      <button class="primary" disabled={installing} onclick={() => install(false)}>{t("updates.install")}</button>
    {/snippet}
  </Modal>
{/if}

{#if target && askRunning !== null}
  <Modal title={t("updates.running_title", { n: askRunning })} onclose={() => (target = null)}>
    <p>{t("updates.running_text")}</p>
    {#snippet footer()}
      <button onclick={() => (target = null)}>{t("common.cancel")}</button>
      <button class="danger" disabled={installing} onclick={() => install(true)}>{t("updates.running_confirm")}</button>
    {/snippet}
  </Modal>
{/if}

<style>
  .facts {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
    gap: 14px;
    align-items: end;
  }
  .label {
    display: block;
    color: var(--muted);
    font-size: 12px;
  }
  .facts strong {
    font-size: 20px;
  }
  .actions {
    margin-top: 14px;
  }
  .big-badge {
    font-size: 14px;
    padding: 4px 10px;
  }
  .notes {
    white-space: pre-wrap;
    font-family: inherit;
    margin: 8px 0;
    max-height: 360px;
    overflow: auto;
  }
  .warn-text {
    color: var(--warn);
  }
  .info-box {
    padding: 8px 12px;
    border: 1px solid var(--line);
    border-radius: var(--radius);
  }
  table {
    width: 100%;
    margin-top: 10px;
    border-collapse: collapse;
  }
  td {
    padding: 6px 8px;
    border-top: 1px solid var(--line);
  }
  .right {
    text-align: right;
  }
</style>
