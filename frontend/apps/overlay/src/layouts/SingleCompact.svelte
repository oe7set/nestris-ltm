<script lang="ts">
  // Narrow strip on the right edge, e.g. beside a full-screen camera.
  import Board from "../components/Board.svelte";
  import Stats from "../components/Stats.svelte";
  import type { Lang } from "../lib/format";
  import type { SceneState } from "../lib/types";
  import type { SlotView } from "../lib/view";

  let { views, lang }: { state: SceneState; views: SlotView[]; lang: Lang } = $props();
  const v = $derived(views[0]);
</script>

{#if v}
  <div class="strip">
    <Stats view={v} {lang} compact />
    <Board view={v} cell={28} {lang} />
  </div>
{/if}

<style>
  .strip {
    position: absolute;
    right: 30px;
    top: 30px;
    width: 420px;
    display: grid;
    gap: 16px;
  }
</style>
