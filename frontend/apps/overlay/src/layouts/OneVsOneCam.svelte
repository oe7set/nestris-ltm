<script lang="ts">
  // 1 vs 1 for 16:9 with cameras outside: camera A | stats A | board A ‖
  // board B | stats B | camera B. The camera areas are transparent: put the
  // camera sources behind the overlay in OBS. Name + hearts above each camera.
  import Board from "../components/Board.svelte";
  import Camera from "../components/Camera.svelte";
  import DiffGraph from "../components/DiffGraph.svelte";
  import NameTag from "../components/NameTag.svelte";
  import SideStats from "../components/SideStats.svelte";
  import Versus from "../components/Versus.svelte";
  import { text, type Lang } from "../lib/format";
  import { look } from "../lib/look.svelte";
  import { scene } from "../lib/scene.svelte";
  import type { SceneState } from "../lib/types";
  import type { SlotView } from "../lib/view";

  let { state, views, lang }: { state: SceneState; views: SlotView[]; lang: Lang } = $props();
  const a = $derived(views[0]);
  const b = $derived(views[1]);
  const framed = $derived(state.scene.settings.camera_frames ?? false);
  const match = $derived(state.matches?.[0]);
  // The pixel font of the NES style needs wider stats columns.
  const camW = $derived(look.nes ? 290 : 340);
  const cell = $derived(look.nes ? 32 : 34);
</script>

{#if a && b}
  <div class="stage" class:nes={look.nes}>
    <div class="cam left">
      <NameTag view={a} {lang} />
      <Camera width={camW} height={880} {framed} />
    </div>
    <SideStats view={a} {lang} />
    <div class="center">
      <div class="title">
        <span class="name">{state.scene.settings.title ?? match?.round_name ?? state.scene.name}</span>
        <span class="round">{text(lang, "round")} {a.round ?? state.round}</span>
      </div>
      <div class="boards">
        <Board view={a} {cell} {lang} showNext={false} />
        <span class="vs">VS</span>
        <Board view={b} {cell} {lang} showNext={false} />
      </div>
      <div class="bottom">
        <Versus {a} {b} {lang} />
        <DiffGraph a={scene.history["0"]} b={scene.history["1"]} width={420} height={170} />
      </div>
    </div>
    <SideStats view={b} {lang} align="right" />
    <div class="cam right">
      <NameTag view={b} {lang} align="right" />
      <Camera width={camW} height={880} {framed} />
    </div>
  </div>
{/if}

<style>
  .stage {
    position: absolute;
    inset: 20px;
    display: grid;
    grid-template-columns: 340px 200px minmax(0, 1fr) 200px 340px;
    gap: 12px;
    align-items: start;
  }
  .stage.nes {
    grid-template-columns: 290px 260px minmax(0, 1fr) 260px 290px;
  }
  .cam {
    display: grid;
    gap: 12px;
    min-width: 0;
  }
  .center {
    display: grid;
    gap: 12px;
    justify-items: center;
  }
  .title {
    display: flex;
    gap: 14px;
    align-items: center;
    font-size: 22px;
    letter-spacing: 3px;
  }
  .title .name {
    color: var(--accent);
    padding: 4px 14px;
    background: var(--panel);
    border: 2px solid var(--frame);
    border-radius: 8px;
  }
  .title .round {
    font-size: 16px;
    padding: 4px 12px;
    background: var(--panel);
    border: 2px solid var(--frame);
    border-radius: 8px;
  }
  .boards {
    display: flex;
    align-items: center;
    gap: 6px;
  }
  .vs {
    writing-mode: vertical-rl;
    font-size: 18px;
    letter-spacing: 6px;
    color: var(--accent);
  }
  .bottom {
    display: grid;
    grid-template-columns: 300px 420px;
    gap: 12px;
    align-items: start;
  }
</style>
