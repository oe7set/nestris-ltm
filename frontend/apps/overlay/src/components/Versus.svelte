<script lang="ts">
  // Head-to-head centre: score difference, lead in tetrises, pace, catch-up hint.
  import { fmt, signed, tetrises, hud, text, type Lang } from "../lib/format";
  import type { SlotView } from "../lib/view";
  import Num from "./Num.svelte";

  interface Props {
    a: SlotView;
    b: SlotView;
    lang?: Lang;
  }
  let { a, b, lang = "de" }: Props = $props();

  const active = $derived(
    (a.status === "playing" || a.status === "finished") && (b.status === "playing" || b.status === "finished"),
  );
  const diff = $derived((a.score ?? 0) - (b.score ?? 0)); // > 0: A leads
  const leader = $derived(diff > 0 ? a : diff < 0 ? b : null);
  const trailer = $derived(diff > 0 ? b : diff < 0 ? a : null);
  // Lead in tetrises at the trailing player's level (the usual broadcast metric).
  const leadTetrises = $derived(
    trailer ? Math.abs(diff) / (1200 * ((trailer.level ?? 0) + 1)) : 0,
  );
  const paceDiff = $derived((a.pace ?? 0) - (b.pace ?? 0));
  // Leader topped out, trailer still playing: what does the trailer need?
  const needs = $derived(
    leader && trailer && leader.status === "finished" && trailer.status === "playing"
      ? (trailer.slot === a.slot ? a.vs_partner : b.vs_partner)
      : undefined,
  );
</script>

{#if active}
  <div class="versus">
    <div class="label">{hud(lang, "diff")}</div>
    <div class="diff" class:a={diff > 0} class:b={diff < 0}>
      {#if diff === 0}{text(lang, "even")}{:else}<Num value={Math.abs(diff)} />{/if}
    </div>
    {#if leader}
      <div class="who">
        <span class="arrow">{leader.slot === a.slot ? "◀" : ""}</span>
        <span class="name">{leader.name}</span>
        <span class="arrow">{leader.slot === b.slot ? "▶" : ""}</span>
      </div>
      <div class="tetrises">
        <b>{tetrises(leadTetrises)}</b> {text(lang, "tetris")}
      </div>
    {/if}
    {#if needs}
      <div class="needs">
        {trailer?.name} {text(lang, "needs")}<br />
        <b>{needs.tetrises_needed}</b> {text(lang, "tetris")} {text(lang, "to_win")}
      </div>
    {/if}
    <div class="pace">
      <span>{hud(lang, "pace")}</span>
      <b class:a={paceDiff > 0} class:b={paceDiff < 0}>{signed(paceDiff)}</b>
      <small>{fmt(a.pace)} : {fmt(b.pace)}</small>
    </div>
  </div>
{/if}

<style>
  .versus {
    display: grid;
    gap: 8px;
    justify-items: center;
    text-align: center;
    padding: 16px 12px;
    background: var(--panel);
    border: 2px solid var(--frame);
    border-radius: 8px;
  }
  .label,
  .pace span {
    font-size: 13px;
    letter-spacing: 3px;
    color: var(--muted);
  }
  .diff {
    font-size: 54px;
    line-height: 1;
    font-variant-numeric: tabular-nums;
    color: var(--text);
    transition: color 0.3s;
  }
  .diff.a,
  .pace b.a {
    color: var(--side-a);
  }
  .diff.b,
  .pace b.b {
    color: var(--side-b);
  }
  .who {
    display: flex;
    gap: 6px;
    font-size: 20px;
    max-width: 100%;
  }
  .who .name {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .tetrises {
    font-size: 18px;
    color: var(--muted);
  }
  .tetrises b {
    font-size: 34px;
    color: var(--accent);
    font-weight: 400;
  }
  .needs {
    font-size: 16px;
    padding: 6px 10px;
    border: 2px dashed var(--accent);
    border-radius: 6px;
    animation: pulse 1.2s ease-in-out infinite;
  }
  .needs b {
    font-size: 30px;
    color: var(--accent);
    font-weight: 400;
  }
  .pace {
    display: grid;
    gap: 2px;
  }
  .pace b {
    font-size: 26px;
    font-weight: 400;
  }
  .pace small {
    color: var(--muted);
    font-size: 13px;
  }
  @keyframes pulse {
    50% { box-shadow: 0 0 18px var(--accent); }
  }
</style>
