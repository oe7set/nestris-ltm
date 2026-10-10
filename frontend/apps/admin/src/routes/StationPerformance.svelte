<script lang="ts">
  // How fast each station recognizes the picture and how well its live data
  // reaches this host: the station's `perf` status (0.3.0+) and the host's
  // own reception statistics, with a short history.
  import { onMount } from "svelte";
  import { poll } from "../lib/poll";
  import { api } from "../lib/api";
  import { t } from "../lib/i18n.svelte";
  import { live } from "../lib/live.svelte";
  import {
    captureLevel,
    cpuLevel,
    dropLevel,
    engineLevel,
    fmt,
    fpsLevel,
    linkLevel,
    overallLevel,
    pct,
    sparkline,
    type LinkStats,
    type PerfPoint,
    type StationPerf,
  } from "../lib/perf";

  const stations = $derived(Object.values(live.stations).sort((a, b) => a.id.localeCompare(b.id)));
  let history = $state<Record<string, PerfPoint[]>>({});

  async function loadHistory(): Promise<void> {
    const entries = await Promise.all(
      stations.map(async (s) => {
        try {
          const r = await api<{ points: PerfPoint[] }>(`/api/stations/${encodeURIComponent(s.id)}/metrics`);
          return [s.id, r.points] as const;
        } catch {
          return [s.id, history[s.id] ?? []] as const;
        }
      }),
    );
    history = Object.fromEntries(entries);
  }

  onMount(() => {
    const release = live.acquire();
    const first = setTimeout(loadHistory, 500);
    const stop = poll(loadHistory, 10_000);
    return () => {
      release();
      clearTimeout(first);
      stop();
    };
  });

  const perfOf = (status: Record<string, unknown> | null): StationPerf | null =>
    (status?.perf as StationPerf | undefined) ?? null;
  const linkOf = (s: { link?: LinkStats }): LinkStats | null => s.link ?? null;

  const W = 220;
  const H = 40;
</script>

<p class="hint">{t("perf.intro")}</p>

<div class="cards">
  {#each stations as s (s.id)}
    {@const p = perfOf(s.status)}
    {@const l = linkOf(s)}
    {@const points = history[s.id] ?? []}
    {@const target = p?.target_fps ?? p?.capture_fps ?? null}
    <section class="panel card">
      <header>
        <span class="dot {s.online ? overallLevel(p, l) : 'bad'}"></span>
        <strong>{s.name ?? s.id}</strong>
        {#if s.name}<span class="muted small mono">{s.id}</span>{/if}
        <span class="muted small right">{String(s.status?.version ?? "")}</span>
      </header>
      {#if !s.online}
        <p class="muted small">{t("dash.offline")}</p>
      {:else if !p}
        <p class="muted small">
          {t("perf.no_perf")}
          {#if typeof s.status?.fps === "number"}<br />{t("perf.fps")}: {fmt(s.status.fps as number)}{/if}
        </p>
      {:else}
        <table class="kv">
          <tbody>
            <tr>
              <th>{t("perf.fps")}</th>
              <td><span class="dot {fpsLevel(p)}"></span>{fmt(p.fps)} / {fmt(target, 0)}</td>
            </tr>
            <tr>
              <th>{t("perf.capture")}</th>
              <td>
                <span class="dot {captureLevel(p)}"></span>{fmt(p.capture_fps)} fps
                <span class="muted small">{t("perf.missing", { n: p.missing ?? 0, total: p.missing_total ?? 0 })}</span>
              </td>
            </tr>
            <tr>
              <th>{t("perf.dropped")}</th>
              <td>
                <span class="dot {dropLevel(p)}"></span>{pct(p.drop_rate)}
                <span class="muted small">({p.dropped_total ?? 0})</span>
              </td>
            </tr>
            <tr>
              <th>{t("perf.engine")}</th>
              <td><span class="dot {engineLevel(p)}"></span>{fmt(p.engine_ms_p50, 1)} / {fmt(p.engine_ms_p95, 1)} ms</td>
            </tr>
            <tr>
              <th>{t("perf.age")}</th>
              <td>{fmt(p.frame_age_ms_p95, 1, " ms")}</td>
            </tr>
            <tr>
              <th>{t("perf.cpu")}</th>
              <td>
                <span class="dot {cpuLevel(p)}"></span>{fmt(p.cpu_pct, 0, " %")}
                <span class="muted small">load {fmt(p.load1, 2)}</span>
              </td>
            </tr>
            <tr>
              <th>{t("perf.size")}</th>
              <td class="mono">{p.size ?? "–"}</td>
            </tr>
            <tr>
              <th>{t("perf.live")}</th>
              <td>
                {#if l?.sequenced}
                  <span class="dot {linkLevel(l)}"></span>{fmt(l.rx_hz)} / {fmt(p.live_hz)} Hz,
                  {t("perf.lost", { n: l.lost, rate: pct(l.loss_rate) })}
                {:else}
                  {fmt(l?.rx_hz)} Hz <span class="muted small">{t("perf.no_seq")}</span>
                {/if}
              </td>
            </tr>
            <tr>
              <th>{t("perf.latency")}</th>
              <td>
                {fmt(l?.frame_age_ms, 1, " ms")}
                {#if l?.transport_ms != null}+ {fmt(l.transport_ms, 1, " ms")} {t("perf.transport")}{/if}
                {#if l?.clock_skew}<span class="warn-text small">{t("perf.clock_skew")}</span>{/if}
              </td>
            </tr>
          </tbody>
        </table>
      {/if}
      {#if points.length > 1}
        {@const top = Math.max(target ?? 0, ...points.map((x) => x.capture_fps ?? x.fps ?? 0))}
        <svg viewBox="0 0 {W} {H}" width={W} height={H} role="img" aria-label={t("perf.history")}>
          {#if target}
            <line x1="0" x2={W} y1={H - (target / top) * H} y2={H - (target / top) * H} class="target" />
          {/if}
          <polyline points={sparkline(points.map((x) => x.capture_fps), W, H, top)} class="capture" />
          <polyline points={sparkline(points.map((x) => x.fps), W, H, top)} class="fps" />
        </svg>
        <p class="muted small legend">
          <span class="swatch fps"></span>{t("perf.fps")}
          <span class="swatch capture"></span>{t("perf.capture")}
          · {t("perf.history_span", { n: points.length })}
        </p>
      {/if}
    </section>
  {:else}
    <p class="muted">{t("dash.no_stations")}</p>
  {/each}
</div>

<style>
  .cards {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
    gap: 12px;
  }
  .card header {
    display: flex;
    align-items: baseline;
    gap: 8px;
    margin-bottom: 8px;
  }
  .right {
    margin-left: auto;
  }
  .kv th {
    text-align: left;
    font-weight: 500;
    color: var(--muted);
    padding-right: 10px;
    white-space: nowrap;
  }
  .kv td,
  .kv th {
    padding-top: 2px;
    padding-bottom: 2px;
  }
  .kv .dot {
    margin-right: 6px;
  }
  svg {
    display: block;
    margin-top: 8px;
    max-width: 100%;
  }
  polyline {
    fill: none;
    stroke-width: 1.5;
  }
  polyline.fps {
    stroke: var(--accent);
  }
  polyline.capture {
    stroke: var(--muted);
    stroke-dasharray: 3 2;
  }
  line.target {
    stroke: var(--ok);
    stroke-width: 1;
    opacity: 0.5;
  }
  .legend {
    display: flex;
    align-items: center;
    gap: 6px;
    margin: 4px 0 0;
  }
  .swatch {
    display: inline-block;
    width: 12px;
    height: 2px;
  }
  .swatch.fps {
    background: var(--accent);
  }
  .swatch.capture {
    background: var(--muted);
  }
  .warn-text {
    color: var(--warn);
    margin-left: 6px;
  }
</style>
