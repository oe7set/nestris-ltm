<script lang="ts">
  // Two players head to head: boards outside, stats inside, versus centre.
  import Board from "../components/Board.svelte";
  import Camera from "../components/Camera.svelte";
  import DiffGraph from "../components/DiffGraph.svelte";
  import Header from "../components/Header.svelte";
  import Stats from "../components/Stats.svelte";
  import Versus from "../components/Versus.svelte";
  import type { Lang } from "../lib/format";
  import { scene } from "../lib/scene.svelte";
  import type { SceneState } from "../lib/types";
  import type { SlotView } from "../lib/view";

  let { state, views, lang }: { state: SceneState; views: SlotView[]; lang: Lang } = $props();
  const a = $derived(views[0]);
  const b = $derived(views[1]);
  const framed = $derived(state.scene.settings.camera_frames ?? false);
</script>

{#if a && b}
  <div class="vs">
    <Header {state} {lang} />
    <div class="row">
      <Board view={a} cell={34} {lang} nextSide="right" />
      <div class="col">
        <Camera width={290} height={163} {framed} />
        <Stats view={a} {lang} />
      </div>
      <div class="center">
        <Versus {a} {b} {lang} />
        <DiffGraph a={scene.history["0"]} b={scene.history["1"]} width={240} height={150} />
      </div>
      <div class="col">
        <Camera width={290} height={163} {framed} />
        <Stats view={b} {lang} align="right" />
      </div>
      <Board view={b} cell={34} {lang} nextSide="left" />
    </div>
  </div>
{/if}

<style>
  .vs {
    position: absolute;
    inset: 16px 20px;
    display: grid;
    grid-template-rows: auto 1fr;
    gap: 14px;
  }
  .row {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 14px;
  }
  .col {
    width: 290px;
    display: grid;
    gap: 14px;
  }
  .center {
    width: 244px;
    display: grid;
    gap: 14px;
    align-content: start;
    padding-top: 40px;
  }
</style>
