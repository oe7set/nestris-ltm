<script lang="ts">
  // Replays a recorded game, started from the admin UI (scene setting "replay").
  import { NextPiece, Playfield, Timeline, loadRecording, rowsFromCells, type NgfFrame } from "@nestris-ltm/nes";
  import { onMount } from "svelte";
  import Num from "../components/Num.svelte";
  import { fmt, text, type Lang } from "../lib/format";
  import type { SceneState } from "../lib/types";
  import type { SlotView } from "../lib/view";

  interface ReplaySetting {
    game_id: number;
    speed: number;
    loop: boolean;
    token: string;
    player: string | null;
    score: number | null;
    start_level: number | null;
    started_at: string;
  }

  let { state: scene, lang }: { state: SceneState; views: SlotView[]; lang: Lang } = $props();

  const replay = $derived((scene.scene.settings as { replay?: ReplaySetting }).replay ?? null);

  let timeline: Timeline | null = null;
  let frame = $state<NgfFrame | null>(null);
  let loadedToken = "";
  let raf = 0;

  $effect(() => {
    const r = replay;
    if (!r) {
      timeline = null;
      frame = null;
      loadedToken = "";
      return;
    }
    if (r.token === loadedToken) return;
    loadedToken = r.token;
    loadRecording(`/api/games/${r.game_id}/recording`)
      .then(({ frames }) => {
        if (loadedToken !== r.token) return; // superseded meanwhile
        timeline = new Timeline(frames);
        timeline.speed = r.speed;
        timeline.loop = r.loop;
        timeline.play(performance.now());
      })
      .catch(() => (frame = null));
  });

  onMount(() => {
    const loop = (now: number) => {
      if (timeline) frame = timeline.frames[timeline.tick(now)] ?? null;
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  });

  const date = $derived(
    replay ? new Date(replay.started_at).toLocaleString(lang === "en" ? "en-GB" : "de-AT", { dateStyle: "medium", timeStyle: "short" }) : "",
  );
</script>

{#if replay && frame}
  <div class="replay">
    <div class="well">
      <Playfield rows={rowsFromCells(frame.cells)} level={frame.level} cell={42} />
    </div>
    <div class="side">
      <div class="tag">REPLAY{replay.speed !== 1 ? ` · ${replay.speed}×` : ""}</div>
      <div class="name">{replay.player ?? "—"}</div>
      <div class="date">{date}</div>
      <div class="score"><Num value={frame.score} duration={150} /></div>
      <div class="grid">
        <div><span>{text(lang, "lines")}</span><b>{fmt(frame.lines)}</b></div>
        <div><span>{text(lang, "level")}</span><b>{fmt(frame.level)}</b></div>
      </div>
      <div class="next">
        <span>{text(lang, "next")}</span>
        <NextPiece piece={frame.preview} level={frame.level} cell={30} />
      </div>
      {#if replay.score !== null}
        <div class="final">{lang === "en" ? "FINAL" : "ENDSTAND"} {fmt(replay.score)}</div>
      {/if}
    </div>
  </div>
{/if}

<style>
  .replay {
    position: absolute;
    right: 60px;
    top: 50px;
    display: flex;
    gap: 24px;
    align-items: flex-start;
  }
  .well {
    padding: 10px;
    background: var(--well-bg);
    border: 3px solid var(--frame);
    border-radius: 6px;
    box-shadow: 0 10px 30px #0008;
  }
  .side {
    width: 380px;
    display: grid;
    gap: 12px;
    padding: 18px 22px;
    background: var(--panel);
    border: 2px solid var(--frame);
    border-radius: 8px;
  }
  .tag {
    justify-self: start;
    padding: 4px 12px;
    border-radius: 6px;
    background: var(--bad);
    color: #fff;
    letter-spacing: 4px;
    font-size: 18px;
    animation: rec 1.6s steps(2) infinite;
  }
  .name {
    font-size: 40px;
    color: var(--accent);
  }
  .date {
    color: var(--muted);
    font-size: 18px;
  }
  .score {
    font-size: 64px;
    line-height: 1;
    font-variant-numeric: tabular-nums;
  }
  .grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
  }
  .grid span,
  .next span {
    display: block;
    font-size: 14px;
    letter-spacing: 2px;
    color: var(--muted);
  }
  .grid b {
    font-weight: 400;
    font-size: 32px;
  }
  .next {
    display: grid;
    gap: 6px;
  }
  .final {
    color: var(--muted);
    font-size: 20px;
    letter-spacing: 2px;
  }
  @keyframes rec {
    50% { opacity: 0.6; }
  }
</style>
