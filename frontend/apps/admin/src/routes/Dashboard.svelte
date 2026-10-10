<script lang="ts">
  import { onMount } from "svelte";
  import AttentionList from "../components/AttentionList.svelte";
  import PhaseBanner from "../components/PhaseBanner.svelte";
  import { api } from "../lib/api";
  import { dateTime, num } from "../lib/format";
  import { i18n, t, tDynamic } from "../lib/i18n.svelte";
  import { live } from "../lib/live.svelte";
  import { fmt, overallLevel, pct, type StationPerf } from "../lib/perf";
  import type { Diagnostics, LogEntry } from "../lib/types";

  interface ActiveEvent {
    id: number;
    name: string;
    starts_at: string;
    ends_at: string | null;
  }

  let diag = $state<Diagnostics | null>(null);
  let event = $state<ActiveEvent | null | undefined>(undefined);
  let logs = $state<LogEntry[]>([]);
  let lastLogId = 0;
  let logBox = $state<HTMLElement>();

  const stations = $derived(Object.values(live.stations).sort((a, b) => a.id.localeCompare(b.id)));

  async function refresh(): Promise<void> {
    try {
      diag = await api<Diagnostics>("/api/diagnostics");
    } catch {
      diag = null;
    }
  }

  async function refreshLogs(): Promise<void> {
    try {
      const { entries } = await api<{ entries: LogEntry[] }>("/api/diagnostics/logs", {
        query: { after_id: lastLogId, level: "INFO", limit: 200 },
      });
      if (!entries.length) return;
      const atBottom = logBox
        ? logBox.scrollTop + logBox.clientHeight >= logBox.scrollHeight - 4
        : true;
      lastLogId = entries[entries.length - 1]!.id;
      logs = [...logs, ...entries].slice(-400);
      if (atBottom) queueMicrotask(() => logBox && (logBox.scrollTop = logBox.scrollHeight));
    } catch {
      // keep the last log lines while the server restarts
    }
  }

  onMount(() => {
    const release = live.acquire();
    void refresh();
    void refreshLogs();
    api<ActiveEvent | null>("/api/events/active")
      .then((e) => (event = e))
      .catch(() => (event = null));
    const a = setInterval(refresh, 2000);
    const b = setInterval(refreshLogs, 2000);
    return () => {
      release();
      clearInterval(a);
      clearInterval(b);
    };
  });

  function stateClass(online: boolean, stale: boolean): string {
    return online && !stale ? "ok" : online ? "warn" : "bad";
  }
</script>

<h1>{t("nav.dashboard")}</h1>
<PhaseBanner compact />

{#if event === null}
  <p class="error-box">{t("dash.no_event")} <a href="#/events">{t("nav.events")} ›</a></p>
{:else if event}
  <p class="hint">
    {t("dash.active_event")}: <strong>{event.name}</strong>
    ({dateTime(event.starts_at, i18n.locale)} – {event.ends_at ? dateTime(event.ends_at, i18n.locale) : t("events.open_end")})
  </p>
{/if}

<section class="panel attention">
  <h2>{t("attention.title")}</h2>
  <AttentionList />
</section>

<section class="cards">
  <div class="panel">
    <h2>{t("dash.database")}</h2>
    <div class="big">
      <span class="dot {diag?.database.ready ? 'ok' : 'bad'}"></span>
      {!diag ? "–" : diag.database.ready ? t("dash.connected") : tDynamic(`db.state.${diag.database.state}.title`, t("dash.disconnected"))}
    </div>
    {#if diag && !diag.database.ready}
      <div class="muted small">{diag.database.error ?? ""}</div>
      <a class="small" href="#/database">{t("dash.db_problem")}</a>
    {:else}
      <div class="muted small">{diag ? `${diag.database.name} @ ${diag.database.host}` : ""}</div>
    {/if}
  </div>
  <div class="panel">
    <h2>{t("dash.broker")}</h2>
    <div class="big">
      <span class="dot {!diag?.mqtt.enabled ? '' : diag.mqtt.connected ? 'ok' : 'bad'}"></span>
      {!diag ? "–" : !diag.mqtt.enabled ? t("dash.disabled") : diag.mqtt.connected ? t("dash.connected") : t("dash.disconnected")}
    </div>
    <div class="muted small">
      {diag?.mqtt.last_error ?? (diag ? `${diag.mqtt.broker} · ${diag.mqtt.topic_prefix}/#` : "")}
    </div>
  </div>
  <div class="panel">
    <h2>{t("dash.results")}</h2>
    <div class="big">{t("dash.stored", { n: num(diag?.ingest.events_stored, i18n.locale) })}</div>
    <div class="muted small">
      {t("dash.queue", { pending: diag?.ingest.spool_pending ?? "–", failed: diag?.ingest.spool_failed ?? "–" })}
    </div>
  </div>
  <div class="panel">
    <h2>{t("dash.frames")}</h2>
    <div class="big">{num(diag?.ingest.frames_written, i18n.locale)}</div>
    <div class="muted small">
      {t("dash.frames_sub", {
        pending: num(diag?.ingest.frames_pending, i18n.locale),
        dropped: num(diag?.ingest.frames_dropped, i18n.locale),
        errors: num(diag?.ingest.parse_errors, i18n.locale),
      })}
    </div>
  </div>
</section>

<div class="row head">
  <h2>{t("dash.stations")}</h2>
  <span class="spacer"></span>
  <span class="muted small"><span class="dot {live.connected ? 'ok' : 'bad'}"></span> {t("dash.live")}</span>
</div>
<div class="table-wrap">
  <table>
    <thead>
      <tr>
        <th>{t("games.station")}</th>
        <th>{t("games.status")}</th>
        <th>Capture</th>
        <th>RFID</th>
        <th>{t("games.player")}</th>
        <th>{t("dash.game_state")}</th>
        <th class="num">{t("games.score")}</th>
        <th class="num">{t("games.lines")}</th>
        <th class="num">{t("games.levels")}</th>
        <th class="num">FPS</th>
      </tr>
    </thead>
    <tbody>
      {#each stations as s (s.id)}
        {@const st = s.status ?? {}}
        {@const perf = (st.perf as StationPerf | undefined) ?? null}
        <tr>
          <td>{s.name ?? s.id} {#if s.name}<span class="muted small">{s.id}</span>{/if}</td>
          <td>
            <span class="dot {stateClass(s.online, s.stale)}"></span>
            {s.online ? (s.stale ? t("dash.stale") : t("dash.online")) : t("dash.offline")}
          </td>
          <td>{String(st.capture ?? "–")}</td>
          <td>
            <span class:warn-text={st.rfid === "outdated"}>{String(st.rfid ?? "–")}</span>
            {#if st.reader_fw}<span class="muted small">fw {String(st.reader_fw)}</span>{/if}
          </td>
          <td>
            {s.player_nickname ?? s.card?.name ?? (s.card_present ? t("dash.blank_card") : t("dash.no_card"))}
          </td>
          <td>{s.live?.game_state ?? String(st.game_state ?? "–")}</td>
          <td class="num">{num(s.live?.score, i18n.locale)}</td>
          <td class="num">{num(s.live?.lines, i18n.locale)}</td>
          <td class="num">{num(s.live?.level, i18n.locale)}</td>
          <td class="num">
            {#if perf}
              <a href="#/stations?tab=perf" title={`${t("perf.dropped")} ${pct(perf.drop_rate)}`}>
                <span class="dot {overallLevel(perf, s.link)}"></span>{fmt(perf.fps)}
              </a>
            {:else}
              {typeof st.fps === "number" ? st.fps.toFixed(1) : "–"}
            {/if}
          </td>
        </tr>
      {:else}
        <tr><td colspan="10" class="empty">{t("dash.no_stations")}</td></tr>
      {/each}
    </tbody>
  </table>
</div>

<div class="two">
  <section>
    <h2>{t("dash.events_feed")}</h2>
    <div class="panel feed">
      {#each live.events as e (e.at.getTime() + e.station + e.kind)}
        <div class="row">
          <span class="muted small mono">{e.at.toLocaleTimeString()}</span>
          <span class="badge {e.kind === 'cheat' ? 'bad' : e.kind === 'game_end' ? 'ok' : ''}">
            {tDynamic(`dash.kind.${e.kind}`, e.kind)}
          </span>
          <span>{e.station}</span>
          {#if typeof e.data.score === "number"}<strong>{num(e.data.score, i18n.locale)}</strong>{/if}
        </div>
      {:else}
        <p class="muted small">{t("dash.no_events")}</p>
      {/each}
    </div>
  </section>
  <section>
    <h2>{t("dash.log")}</h2>
    <pre bind:this={logBox}>{#each logs as l (l.id)}<div class="lvl-{l.level}">{l.message}</div>{/each}</pre>
  </section>
</div>

<style>
  .attention {
    margin-bottom: 12px;
  }
  .warn-text {
    color: var(--warn);
    font-weight: 600;
  }
  .big {
    font-size: 18px;
    font-weight: 600;
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 4px;
  }
  .head {
    margin: 22px 0 8px;
  }
  .head h2 {
    margin: 0;
  }
  .two {
    display: grid;
    gap: 16px;
    grid-template-columns: minmax(260px, 1fr) 2fr;
    margin-top: 22px;
  }
  .feed {
    display: grid;
    gap: 6px;
    max-height: 300px;
    overflow: auto;
  }
  pre {
    margin: 0;
    height: 300px;
    overflow: auto;
    background: #070b16;
    border: 1px solid var(--line);
    border-radius: var(--radius);
    padding: 10px;
    font: 12px/1.4 Consolas, monospace;
    color: #cbd5e1;
    white-space: pre-wrap;
    word-break: break-word;
  }
  .lvl-WARNING {
    color: var(--warn);
  }
  .lvl-ERROR,
  .lvl-CRITICAL {
    color: var(--bad);
  }
  @media (max-width: 900px) {
    .two {
      grid-template-columns: 1fr;
    }
  }
</style>
