<script lang="ts">
  // One player, large: camera space on the left (filled in OBS), board and
  // stats side by side on the right.
  import Board from "../components/Board.svelte";
  import Camera from "../components/Camera.svelte";
  import Stats from "../components/Stats.svelte";
  import type { Lang } from "../lib/format";
  import type { SceneState } from "../lib/types";
  import type { SlotView } from "../lib/view";

  let { state, views, lang }: { state: SceneState; views: SlotView[]; lang: Lang } = $props();
  const v = $derived(views[0]);
</script>

{#if v}
  <div class="single">
    <div class="camera"><Camera width={860} height={484} framed={state.scene.settings.camera_frames} /></div>
    <Board view={v} cell={44} {lang} />
    <div class="side"><Stats view={v} {lang} /></div>
  </div>
{/if}

<style>
  .single {
    position: absolute;
    inset: 40px;
    display: flex;
    gap: 24px;
    align-items: flex-start;
  }
  .camera {
    flex: 1;
  }
  .side {
    width: 330px;
    margin-top: 180px;
  }
</style>
