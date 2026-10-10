<script lang="ts">
  // Replay of a game's recording: playfield, values and transport controls.
  import { NextPiece, Playfield, Timeline, loadRecording, rowsFromCells, type NgfFrame } from "@nestris-ltm/nes";
  import { onMount } from "svelte";
  import { duration as fmtDuration, num } from "../lib/format";
  import { i18n, t } from "../lib/i18n.svelte";

  let { gameId }: { gameId: number } = $props();

  const SPEEDS = [0.25, 0.5, 1, 2, 4, 8];

  let timeline = $state<Timeline | null>(null);
  let frame = $state<NgfFrame | null>(null);
  let position = $state(0);
  let playing = $state(false);
  let speed = $state(1);
  let source = $state("");
  let error = $state<string | null>(null);
  let raf = 0;

  function loop(now: number): void {
    if (timeline) {
      const index = timeline.tick(now);
      frame = timeline.frames[index] ?? null;
      position = timeline.position;
      playing = timeline.playing;
    }
    raf = requestAnimationFrame(loop);
  }

  function toggle(): void {
    if (!timeline) return;
    if (timeline.playing) timeline.pause();
    else timeline.play(performance.now());
  }

  function seek(ms: number): void {
    timeline?.seek(ms);
  }

  function step(n: number): void {
    if (!timeline) return;
    timeline.pause();
    timeline.step(n);
  }

  function setSpeed(value: number): void {
    speed = value;
    if (timeline) timeline.speed = value;
  }

  function onKey(e: KeyboardEvent): void {
    if (!timeline || (e.target as HTMLElement).closest("input, textarea, select")) return;
    if (e.key === " ") {
      e.preventDefault();
      toggle();
    } else if (e.key === "ArrowRight") step(e.shiftKey ? 60 : 1);
    else if (e.key === "ArrowLeft") step(e.shiftKey ? -60 : -1);
  }

  onMount(() => {
    loadRecording(`/api/games/${gameId}/recording`)
      .then(({ frames, source: src }) => {
        source = src;
        if (!frames.length) {
          error = t("replay.none");
          return;
        }
        timeline = new Timeline(frames);
        frame = frames[0] ?? null;
      })
      .catch(() => (error = t("replay.none")));
    raf = requestAnimationFrame(loop);
    addEventListener("keydown", onKey);
    return () => {
      cancelAnimationFrame(raf);
      removeEventListener("keydown", onKey);
    };
  });
</script>

{#if error}
  <p class="muted small">{error}</p>
{:else if timeline && frame}
  <div class="replay">
    <div class="screen">
      <div class="well"><Playfield rows={rowsFromCells(frame.cells)} level={frame.level} cell={18} /></div>
      <div class="side">
        <div class="next"><NextPiece piece={frame.preview} level={frame.level} cell={14} /></div>
        <dl>
          <dt>{t("games.score")}</dt><dd>{num(frame.score, i18n.locale)}</dd>
          <dt>{t("games.lines")}</dt><dd>{num(frame.lines, i18n.locale)}</dd>
          <dt>{t("games.levels")}</dt><dd>{num(frame.level, i18n.locale)}</dd>
          <dt>{t("replay.time")}</dt><dd>{fmtDuration(position / 1000)} / {fmtDuration(timeline.duration / 1000)}</dd>
        </dl>
        <span class="badge {source === 'recording' ? 'ok' : 'warn'}">
          {source === "recording" ? t("replay.source_recording") : t("replay.source_live")}
        </span>
      </div>
    </div>
    <input
      class="scrub"
      type="range"
      min="0"
      max={timeline.duration}
      value={position}
      oninput={(e) => seek(Number(e.currentTarget.value))}
      aria-label={t("replay.time")}
    />
    <div class="row">
      <button onclick={() => step(-60)} title="Shift + ←">⏪</button>
      <button onclick={() => step(-1)} title="←">◀︎ 1</button>
      <button class="primary" onclick={toggle} title={t("replay.space")}>{playing ? "⏸" : "▶"}</button>
      <button onclick={() => step(1)} title="→">1 ▶︎</button>
      <button onclick={() => step(60)} title="Shift + →">⏩</button>
      <span class="spacer"></span>
      {#each SPEEDS as s (s)}
        <button class:on={speed === s} onclick={() => setSpeed(s)}>{s}×</button>
      {/each}
    </div>
    <p class="muted small">{t("replay.keys")}</p>
  </div>
{:else}
  <p class="muted small">{t("common.loading")}</p>
{/if}

<style>
  .replay {
    display: grid;
    gap: 10px;
    min-width: 0;
  }
  .screen {
    display: flex;
    flex-wrap: wrap;
    gap: 14px;
    align-items: flex-start;
  }
  .well {
    padding: 4px;
    background: #000;
    border: 2px solid var(--line);
    border-radius: 6px;
  }
  .side {
    display: grid;
    gap: 10px;
    justify-items: start;
  }
  .next {
    padding: 6px;
    background: #000;
    border: 1px solid var(--line);
    border-radius: 6px;
  }
  dl {
    display: grid;
    grid-template-columns: auto 1fr;
    gap: 4px 12px;
    margin: 0;
    font-variant-numeric: tabular-nums;
  }
  dt {
    color: var(--muted);
  }
  dd {
    margin: 0;
  }
  .scrub {
    width: 100%;
    accent-color: var(--accent);
    padding: 0;
  }
  button.on {
    border-color: var(--accent);
    color: var(--accent);
  }
</style>
