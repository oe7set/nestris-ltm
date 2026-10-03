<script lang="ts">
  // Four players, everyone against everyone, with the round mode's cut line.
  import Board from "../components/Board.svelte";
  import Header from "../components/Header.svelte";
  import Stats from "../components/Stats.svelte";
  import { fmt, text, type Lang } from "../lib/format";
  import type { SceneState } from "../lib/types";
  import type { SlotView } from "../lib/view";

  let { state, views, lang }: { state: SceneState; views: SlotView[]; lang: Lang } = $props();

  const ranked = $derived(
    views
      .filter((v) => v.status === "playing" || v.status === "finished")
      .sort((x, y) => (y.score ?? 0) - (x.score ?? 0)),
  );
</script>

<div class="wrap">
  <Header {state} {lang} />
  <div class="players">
    {#each views as v (v.slot)}
      <div class="player" class:out={v.outcome === "eliminated"}>
        <Board view={v} cell={28} {lang} />
        <Stats view={v} {lang} compact />
        {#if v.to_advance && v.to_advance.points >= 0}
          <div class="need">
            {text(lang, "needs")} <b>{v.to_advance.tetrises_needed}</b> {text(lang, "tetris")}
            {text(lang, "to_advance")}
          </div>
        {:else if v.to_leader && v.to_leader.points > 0 && v.status === "playing"}
          <div class="gap">{text(lang, "behind")} {fmt(v.to_leader.points)} · {v.to_leader.tetrises.toFixed(1)} {text(lang, "tetris")}</div>
        {/if}
      </div>
    {/each}
  </div>
  {#if ranked.length}
    <div class="ranking">
      {#each ranked as v, i (v.slot)}
        <span class="entry {v.outcome ?? ''}">
          <b>{i + 1}.</b> {v.name} <span class="pts">{fmt(v.score)}</span>
        </span>
      {/each}
    </div>
  {/if}
</div>

<style>
  .wrap {
    position: absolute;
    inset: 12px 20px;
    display: grid;
    grid-template-rows: auto 1fr auto;
    gap: 12px;
  }
  .players {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 18px;
  }
  .player {
    display: grid;
    gap: 10px;
    align-content: start;
    transition: opacity 0.6s;
  }
  .player.out {
    opacity: 0.6;
  }
  .need,
  .gap {
    text-align: center;
    padding: 6px 8px;
    border-radius: 6px;
    background: var(--panel);
    border: 2px solid var(--frame);
    font-size: 17px;
  }
  .need {
    border-color: var(--accent);
  }
  .need b {
    color: var(--accent);
    font-size: 24px;
    font-weight: 400;
  }
  .ranking {
    display: flex;
    justify-content: center;
    gap: 14px;
  }
  .entry {
    padding: 6px 16px;
    background: var(--panel);
    border: 2px solid var(--frame);
    border-radius: 8px;
    font-size: 20px;
  }
  .entry.advanced,
  .entry.winner {
    border-color: var(--good);
  }
  .entry.eliminated {
    border-color: var(--bad);
    opacity: 0.7;
  }
  .pts {
    color: var(--muted);
    margin-left: 6px;
  }
</style>
