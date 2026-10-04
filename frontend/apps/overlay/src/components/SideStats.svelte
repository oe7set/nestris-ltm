<script lang="ts">
  // Narrow stats column between camera and playfield (camera layouts):
  // score, lead over the opponent, lines/level/tetris rate, next piece, pace.
  import { NextPiece } from "@nestris-ltm/nes";
  import { fmt, pct, tetrises, text, type Lang } from "../lib/format";
  import type { SlotView } from "../lib/view";
  import Num from "./Num.svelte";

  interface Props {
    view: SlotView;
    lang?: Lang;
    align?: "left" | "right";
    compact?: boolean;
  }
  let { view, lang = "de", align = "left", compact = false }: Props = $props();

  const active = $derived(view.status === "playing" || view.status === "finished");
  // vs_partner.points > 0 = behind the opponent.
  const gap = $derived(active ? view.vs_partner : undefined);
  const droughtAlarm = $derived((view.drought ?? 0) >= 13 && view.status === "playing");
</script>

<div class="side {align}" class:compact>
  <div class="box score">
    <span class="label">SCORE</span>
    <b class="big"><Num value={view.score} /></b>
    {#if gap && gap.points !== 0}
      <span class="gap" class:ahead={gap.points < 0} class:behind={gap.points > 0}>
        {gap.points < 0 ? "+" : "−"}{fmt(Math.abs(gap.points))}
        <small>{tetrises(Math.abs(gap.tetrises))} {text(lang, "tetris")}</small>
      </span>
    {/if}
  </div>
  <div class="row">
    <div class="box"><span class="label">{text(lang, "lines")}</span><b>{fmt(view.lines)}</b></div>
    <div class="box"><span class="label">{text(lang, "level")}</span><b>{fmt(view.level)}</b></div>
  </div>
  <div class="box next">
    <span class="label">{text(lang, "next")}</span>
    <NextPiece piece={view.next_piece} level={view.level} cell={compact ? 16 : 24} />
  </div>
  <div class="row">
    <div class="box"><span class="label">TRT</span><b>{pct(view.tetris_rate)}</b></div>
    <div class="box" class:alarm={droughtAlarm}>
      <span class="label">DRT</span><b>{view.status === "playing" ? fmt(view.drought) : fmt(view.max_drought)}</b>
    </div>
  </div>
  {#if !compact}
    <div class="box"><span class="label">{text(lang, "pace")}</span><b>{fmt(view.pace)}</b></div>
    <div class="box"><span class="label">{text(lang, "burn")}</span><b>{fmt(view.burn)}</b></div>
  {/if}
</div>

<style>
  .side {
    display: grid;
    gap: 10px;
    align-content: start;
    min-width: 0;
  }
  .right {
    text-align: right;
  }
  .row {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 10px;
  }
  .box {
    display: grid;
    gap: 2px;
    padding: 8px 12px;
    background: var(--panel);
    border: 2px solid var(--frame);
    border-radius: 8px;
    min-width: 0;
  }
  .label {
    font-size: 13px;
    letter-spacing: 2px;
    color: var(--muted);
  }
  b {
    font-size: 30px;
    font-weight: 400;
    font-variant-numeric: tabular-nums;
  }
  .big {
    font-size: 40px;
    line-height: 1.05;
  }
  .gap {
    font-size: 20px;
  }
  .gap small {
    display: block;
    font-size: 14px;
    color: var(--muted);
  }
  .ahead {
    color: var(--good);
  }
  .behind {
    color: var(--bad);
  }
  .next {
    justify-items: center;
  }
  .right .next {
    justify-items: center;
  }
  .alarm b {
    color: var(--bad);
  }
  .compact {
    gap: 6px;
  }
  .compact .row {
    gap: 6px;
  }
  .compact .box {
    padding: 4px 8px;
  }
  .compact b {
    font-size: 22px;
  }
  .compact .big {
    font-size: 28px;
  }
  .compact .gap {
    font-size: 16px;
  }
  .compact .label {
    font-size: 11px;
  }
</style>
