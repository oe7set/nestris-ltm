<script lang="ts">
  // Name, score and the per-player numbers.
  import { fmt, pct, text, type Lang } from "../lib/format";
  import type { SlotView } from "../lib/view";
  import Num from "./Num.svelte";

  interface Props {
    view: SlotView;
    lang?: Lang;
    align?: "left" | "right";
    compact?: boolean;
    showPace?: boolean;
  }
  let { view, lang = "de", align = "left", compact = false, showPace = true }: Props = $props();

  const droughtAlarm = $derived((view.drought ?? 0) >= 13 && view.status === "playing");
</script>

<div class="stats {align}" class:compact>
  <div class="name" class:leader={view.rank === 1 && view.status !== "waiting"}>
    {#if view.rank}<span class="rank">{view.rank}</span>{/if}
    <span class="nick">{view.name ?? "—"}</span>
  </div>
  <div class="score"><Num value={view.score} /></div>
  <div class="grid">
    <div class="cell"><span>{text(lang, "lines")}</span><b>{fmt(view.lines)}</b></div>
    <div class="cell"><span>{text(lang, "level")}</span><b>{fmt(view.level)}</b></div>
    <div class="cell"><span>{text(lang, "trt")}</span><b>{pct(view.tetris_rate)}</b></div>
    {#if !compact}
      <div class="cell"><span>{text(lang, "burn")}</span><b>{fmt(view.burn)}</b></div>
    {/if}
    <div class="cell" class:alarm={droughtAlarm}>
      <span>{text(lang, "drought")}</span><b>{view.status === "playing" ? fmt(view.drought) : fmt(view.max_drought)}</b>
    </div>
    {#if showPace && !compact}
      <div class="cell pace"><span>{text(lang, "pace")}</span><b>{fmt(view.pace)}</b></div>
    {/if}
  </div>
</div>

<style>
  .stats {
    display: grid;
    gap: 10px;
    padding: 14px 18px;
    background: var(--panel);
    border: 2px solid var(--frame);
    border-radius: 8px;
    min-width: 0;
  }
  .stats.right {
    text-align: right;
  }
  .name {
    display: flex;
    align-items: center;
    gap: 10px;
    font-size: 30px;
    color: var(--text);
    min-width: 0;
  }
  .right .name {
    flex-direction: row-reverse;
  }
  .nick {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .name.leader .nick {
    color: var(--accent);
  }
  .rank {
    flex: none;
    display: grid;
    place-items: center;
    width: 38px;
    height: 38px;
    border-radius: 6px;
    background: var(--frame);
    font-size: 22px;
  }
  .leader .rank {
    background: var(--accent);
    color: #1a1300;
  }
  .score {
    font-size: 58px;
    line-height: 1;
    color: var(--text);
    font-variant-numeric: tabular-nums;
    letter-spacing: 1px;
  }
  .grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 6px 16px;
  }
  .cell {
    display: grid;
    gap: 0;
  }
  .cell span {
    font-size: 13px;
    letter-spacing: 2px;
    color: var(--muted);
  }
  .cell b {
    font-weight: 400;
    font-size: 28px;
    font-variant-numeric: tabular-nums;
  }
  .cell.alarm b {
    color: var(--bad);
    animation: blink 0.8s steps(2) infinite;
  }
  .cell.pace {
    grid-column: span 2;
  }
  .cell.pace b {
    color: var(--cyan);
  }
  .compact .score {
    font-size: 44px;
  }
  .compact .name {
    font-size: 24px;
  }
  .compact .cell b {
    font-size: 22px;
  }
  @keyframes blink {
    50% { opacity: 0.35; }
  }
</style>
