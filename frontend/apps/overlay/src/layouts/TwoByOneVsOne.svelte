<script lang="ts">
  // Two matches at once: slots 1 vs 2 on the left, 3 vs 4 on the right.
  import Board from "../components/Board.svelte";
  import DiffGraph from "../components/DiffGraph.svelte";
  import Header from "../components/Header.svelte";
  import Stats from "../components/Stats.svelte";
  import Versus from "../components/Versus.svelte";
  import type { Lang } from "../lib/format";
  import { scene } from "../lib/scene.svelte";
  import type { SceneState } from "../lib/types";
  import type { SlotView } from "../lib/view";

  let { state, views, lang }: { state: SceneState; views: SlotView[]; lang: Lang } = $props();
  const matches = $derived([
    [views[0], views[1]],
    [views[2], views[3]],
  ] as const);
</script>

<div class="wrap">
  <Header {state} {lang} />
  <div class="matches">
    {#each matches as [a, b], i (i)}
      {#if a && b}
        <section class="match">
          <div class="side">
            <Board view={a} cell={24} {lang} nextSide="right" />
            <Stats view={a} {lang} compact showPace={false} />
          </div>
          <div class="center">
            <Versus {a} {b} {lang} />
            <DiffGraph a={scene.history[String(a.slot)]} b={scene.history[String(b.slot)]} width={176} height={110} />
          </div>
          <div class="side">
            <Board view={b} cell={24} {lang} nextSide="left" />
            <Stats view={b} {lang} compact align="right" showPace={false} />
          </div>
        </section>
      {/if}
    {/each}
  </div>
</div>

<style>
  .wrap {
    position: absolute;
    inset: 16px 16px;
    display: grid;
    grid-template-rows: auto 1fr;
    gap: 14px;
  }
  .matches {
    display: flex;
    justify-content: space-between;
    gap: 24px;
  }
  .match {
    display: flex;
    gap: 10px;
    align-items: flex-start;
  }
  .side {
    width: 360px;
    display: grid;
    gap: 10px;
  }
  .center {
    width: 180px;
    display: grid;
    gap: 10px;
    padding-top: 60px;
  }
  .center :global(.diff) {
    font-size: 36px;
  }
</style>
