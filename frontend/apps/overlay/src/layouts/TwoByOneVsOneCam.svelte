<script lang="ts">
  // Two separate 1-vs-1 matches for 16:9, one quadrant per player: the top
  // pair (slots 1/2) and the bottom pair (slots 3/4) play their own rounds.
  // Quadrant: camera | stats | board, mirrored on the right so both boards of
  // a pair meet in the middle. Camera areas are transparent (OBS behind).
  import Board from "../components/Board.svelte";
  import Camera from "../components/Camera.svelte";
  import NameTag from "../components/NameTag.svelte";
  import SideStats from "../components/SideStats.svelte";
  import type { Lang } from "../lib/format";
  import { look } from "../lib/look.svelte";
  import type { SceneState } from "../lib/types";
  import type { SlotView } from "../lib/view";

  let { state, views, lang }: { state: SceneState; views: SlotView[]; lang: Lang } = $props();
  const framed = $derived(state.scene.settings.camera_frames ?? false);
  const quadrants = $derived([
    { view: views[0], align: "left" as const },
    { view: views[1], align: "right" as const },
    { view: views[2], align: "left" as const },
    { view: views[3], align: "right" as const },
  ]);
  const CELL = 22;
</script>

<div class="grid">
  {#each quadrants as q, i (i)}
    {#if q.view}
      <section class="quad {q.align}" class:nes={look.nes}>
        <div class="cam">
          <NameTag view={q.view} {lang} align={q.align} compact showRound={!state.scene.qualifying} />
          <Camera width={look.nes ? 460 : 500} height={look.nes ? 430 : 452} {framed} />
        </div>
        <SideStats view={q.view} {lang} align={q.align} compact />
        <Board view={q.view} cell={CELL} {lang} showNext={false} />
      </section>
    {/if}
  {/each}
</div>

<style>
  .grid {
    position: absolute;
    inset: 8px;
    display: grid;
    grid-template-columns: 1fr 1fr;
    grid-template-rows: 1fr 1fr;
    gap: 16px 6px;
  }
  .quad {
    display: grid;
    grid-template-columns: 1fr 160px auto;
    gap: 8px;
    align-items: start;
    min-width: 0;
  }
  .quad.right {
    grid-template-columns: auto 160px 1fr;
  }
  .quad.nes {
    grid-template-columns: minmax(0, 1fr) 200px auto;
  }
  .quad.nes.right {
    grid-template-columns: auto 200px minmax(0, 1fr);
  }
  /* Mirror the order on the right: board | stats | camera. */
  .quad.right .cam {
    order: 3;
  }
  .quad.right :global(.board) {
    order: 1;
  }
  .quad.right :global(.side) {
    order: 2;
  }
  .cam {
    display: grid;
    gap: 8px;
    min-width: 0;
  }
</style>
