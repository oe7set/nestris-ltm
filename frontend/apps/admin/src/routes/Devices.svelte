<script lang="ts">
  // Devices: every station, terminal and reader with its version and the
  // newest release; stations (and their readers) update from here (U4).
  import { onMount } from "svelte";
  import Modal from "../components/Modal.svelte";
  import { api } from "../lib/api";
  import { dateTime } from "../lib/format";
  import { i18n, t, type MessageKey } from "../lib/i18n.svelte";
  import { toasts } from "../lib/toast.svelte";

  interface Offer {
    version: string;
    release: string;
    prerelease: boolean;
    published_at: string | null;
    notes: string;
    url: string;
  }
  interface UpdateProgress {
    target: "station" | "reader";
    version: string;
    state: string;
    detail: string | null;
    progress: number | null;
    ts: string | null;
  }
  interface StationRow {
    id: string;
    name: string | null;
    online: boolean;
    version: string | null;
    rfid: string | null;
    reader_fw: string | null;
    reader_serial: string | null;
    playing: boolean;
    update: UpdateProgress | null;
    station_update: boolean;
    reader_update: boolean;
  }
  interface TerminalRow {
    name: string;
    address: string | null;
    version: string | null;
    reader_fw: string | null;
    last_seen: string;
    update: boolean;
    reader_update: boolean;
  }
  interface DevicesState {
    stations: StationRow[];
    terminals: TerminalRow[];
    latest: { station: Offer | null; reader: Offer | null; terminal: Offer | null };
    station_versions: Offer[];
    reader_versions: Offer[];
    errors: Record<string, string | null>;
    last_check: string | null;
    channel: string;
    owner: string;
  }

  const RUNNING = new Set(["downloading", "verifying", "installing", "flashing", "waiting"]);

  let info = $state<DevicesState | null>(null);
  let checking = $state(false);
  let sending = $state(false);
  // The update dialog: station, target and the chosen version.
  let dialog = $state<{ station: StationRow; target: "station" | "reader"; version: string; factory: boolean } | null>(
    null,
  );

  async function load(): Promise<void> {
    try {
      info = await api<DevicesState>("/api/devices");
    } catch (e) {
      toasts.error(e);
    }
  }

  async function check(): Promise<void> {
    checking = true;
    try {
      info = await api<DevicesState>("/api/devices/check", { method: "POST" });
    } catch (e) {
      toasts.error(e);
    } finally {
      checking = false;
    }
  }

  function open(station: StationRow, target: "station" | "reader"): void {
    const latest = target === "station" ? info?.latest.station : info?.latest.reader;
    if (!latest) return;
    dialog = { station, target, version: latest.version, factory: target === "reader" && station.rfid === "outdated" };
  }

  async function send(): Promise<void> {
    if (!dialog) return;
    sending = true;
    try {
      await api(`/api/devices/stations/${encodeURIComponent(dialog.station.id)}/update`, {
        method: "POST",
        body: { target: dialog.target, version: dialog.version, factory: dialog.factory },
      });
      toasts.ok(t("devices.sent", { station: dialog.station.name ?? dialog.station.id }));
      dialog = null;
      void load();
    } catch (e) {
      toasts.error(e);
    } finally {
      sending = false;
    }
  }

  function running(s: StationRow): boolean {
    return s.update !== null && RUNNING.has(s.update.state);
  }

  function progressText(u: UpdateProgress): string {
    const what = t(u.target === "station" ? "devices.station" : "devices.reader");
    const state = t(`devices.state.${u.state}` as MessageKey);
    const pct = u.progress !== null && RUNNING.has(u.state) ? ` ${Math.round(u.progress * 100)} %` : "";
    return `${what} ${u.version}: ${state}${pct}${u.detail ? ` – ${u.detail}` : ""}`;
  }

  const versions = $derived(
    dialog ? (dialog.target === "station" ? info?.station_versions : info?.reader_versions) ?? [] : [],
  );
  const chosen = $derived(versions.find((v) => v.version === dialog?.version) ?? null);
  const errors = $derived(info ? Object.entries(info.errors).filter(([, e]) => e) : []);

  onMount(() => {
    void load();
    // Faster while a station reports progress.
    let timer: ReturnType<typeof setTimeout>;
    const tick = (): void => {
      const busy = info?.stations.some(running) ?? false;
      timer = setTimeout(() => void load().then(tick), busy ? 1000 : 4000);
    };
    tick();
    return () => clearTimeout(timer);
  });
</script>

<h1>{t("devices.title")}</h1>
{#if info}
  <p class="hint">{t("devices.intro", { owner: info.owner })}</p>
  <div class="row actions">
    <button onclick={check} disabled={checking}>{t("updates.check")}</button>
    <span class="muted small">
      {t("updates.last_check")}: {info.last_check ? dateTime(info.last_check, i18n.locale) : t("updates.never")}
      {#if info.channel === "beta"}· <span class="badge warn">Beta</span>{/if}
    </span>
  </div>
  {#each errors as [repo, error] (repo)}
    <p class="warn-text small">{repo}: {error}</p>
  {/each}

  <section class="panel block">
    <h2>{t("devices.stations")}</h2>
    <p class="muted small">
      {t("devices.latest")}: {t("devices.station")}
      <strong class="mono">{info.latest.station?.version ?? "–"}</strong>
      · {t("devices.reader")} <strong class="mono">{info.latest.reader?.version ?? "–"}</strong>
    </p>
    {#if info.stations.length === 0}
      <p class="muted">{t("devices.no_stations")}</p>
    {:else}
      <table>
        <thead>
          <tr>
            <th>{t("devices.col.station")}</th>
            <th>{t("devices.col.version")}</th>
            <th>{t("devices.col.reader")}</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {#each info.stations as s (s.id)}
            <tr>
              <td>
                <span class="dot" class:on={s.online}></span>
                <strong>{s.name ?? s.id}</strong>
                <span class="muted small mono">{s.id}</span>
                {#if s.playing}<span class="badge warn">{t("devices.playing")}</span>{/if}
              </td>
              <td class="mono">
                {s.version ?? "–"}
                {#if s.station_update}<span class="badge ok">{t("devices.update")}</span>{/if}
              </td>
              <td class="mono">
                {#if s.rfid === "outdated"}
                  <span class="badge warn">{t("devices.reader_old")}</span>
                {:else}
                  {s.reader_fw ?? (s.rfid === "disabled" ? t("devices.reader_disabled") : "–")}
                {/if}
                {#if s.reader_update && s.rfid !== "outdated"}<span class="badge ok">{t("devices.update")}</span>{/if}
                {#if s.reader_serial}<div class="muted small">{s.reader_serial}</div>{/if}
              </td>
              <td class="right">
                <button disabled={!s.online || s.playing || running(s) || !info.latest.station} onclick={() => open(s, "station")}>
                  {t("devices.update_station")}
                </button>
                <button
                  disabled={!s.online || s.playing || running(s) || !info.latest.reader || s.rfid === "disabled"}
                  onclick={() => open(s, "reader")}>{t("devices.update_reader")}</button
                >
              </td>
            </tr>
            {#if s.update}
              <tr class="progress-row">
                <td colspan="4">
                  <div class={s.update.state === "failed" ? "error-box" : "info-box"}>
                    {progressText(s.update)}
                    {#if s.update.ts}<span class="muted small"> · {dateTime(s.update.ts, i18n.locale)}</span>{/if}
                    {#if running(s) && s.update.progress !== null}
                      <div class="bar"><div style="width: {Math.round(s.update.progress * 100)}%"></div></div>
                    {/if}
                  </div>
                </td>
              </tr>
            {/if}
          {/each}
        </tbody>
      </table>
    {/if}
  </section>

  <section class="panel block">
    <h2>{t("devices.terminals")}</h2>
    <p class="muted small">
      {t("devices.latest")}: <strong class="mono">{info.latest.terminal?.version ?? "–"}</strong> · {t("devices.terminal_hint")}
    </p>
    {#if info.terminals.length === 0}
      <p class="muted">{t("devices.no_terminals")}</p>
    {:else}
      <table>
        <thead>
          <tr>
            <th>{t("devices.col.terminal")}</th>
            <th>{t("devices.col.version")}</th>
            <th>{t("devices.col.reader")}</th>
            <th>{t("devices.col.seen")}</th>
          </tr>
        </thead>
        <tbody>
          {#each info.terminals as term (term.name)}
            <tr>
              <td><strong>{term.name}</strong> <span class="muted small mono">{term.address ?? ""}</span></td>
              <td class="mono">
                {term.version ?? "–"}
                {#if term.update}<span class="badge ok">{t("devices.update")}</span>{/if}
              </td>
              <td class="mono">
                {term.reader_fw ?? "–"}
                {#if term.reader_update}<span class="badge ok">{t("devices.update")}</span>{/if}
              </td>
              <td class="muted small">{dateTime(term.last_seen, i18n.locale)}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    {/if}
  </section>
{/if}

{#if dialog}
  <Modal
    title={t(dialog.target === "station" ? "devices.confirm_station" : "devices.confirm_reader", {
      station: dialog.station.name ?? dialog.station.id,
    })}
    onclose={() => (dialog = null)}
  >
    <label class="field">
      <span>{t("devices.col.version")}</span>
      <select bind:value={dialog.version}>
        {#each versions as v (v.version)}
          <option value={v.version}>{v.version}{v.prerelease ? " (beta)" : ""} · {v.release}</option>
        {/each}
      </select>
    </label>
    {#if dialog.target === "station"}
      <p>{t("devices.confirm_station_text")}</p>
    {:else}
      <p>{t("devices.confirm_reader_text")}</p>
      <label class="check">
        <input type="checkbox" bind:checked={dialog.factory} />
        {t("devices.factory")}
      </label>
    {/if}
    {#if chosen?.notes.trim()}<pre class="notes">{chosen.notes}</pre>{/if}
    {#snippet footer()}
      <button onclick={() => (dialog = null)}>{t("common.cancel")}</button>
      <button class="primary" disabled={sending} onclick={send}>{t("devices.start")}</button>
    {/snippet}
  </Modal>
{/if}

<style>
  .dot {
    display: inline-block;
    width: 9px;
    height: 9px;
    border-radius: 50%;
    background: var(--bad, #d55);
    margin-right: 6px;
  }
  .dot.on {
    background: var(--ok, #4c4);
  }
  .progress-row td {
    padding-top: 0;
  }
  .bar {
    height: 8px;
    margin-top: 6px;
    border-radius: 4px;
    background: rgb(0 0 0 / 0.25);
    overflow: hidden;
  }
  .bar div {
    height: 100%;
    background: var(--accent, #fc4);
    transition: width 0.4s;
  }
  .notes {
    max-height: 200px;
    overflow: auto;
    white-space: pre-wrap;
    font-size: 13px;
  }
  td.right button + button {
    margin-left: 6px;
  }
</style>
