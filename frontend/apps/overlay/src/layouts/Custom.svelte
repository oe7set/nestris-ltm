<script lang="ts">
  // An own layout from the layout builder: every element absolutely placed on
  // the 1920x1080 stage. In the builder (mode "edit") hidden elements show
  // faintly so they can still be selected and moved.
  import Widget from "../components/Widget.svelte";
  import type { Lang } from "../lib/format";
  import { paintOrder, type LayoutDefinition } from "../lib/layoutdef";
  import type { SceneState } from "../lib/types";
  import type { SlotView } from "../lib/view";

  interface Props {
    state: SceneState;
    views: SlotView[];
    lang: Lang;
    definition: LayoutDefinition | null;
    editing?: boolean;
  }
  let { state, views, lang, definition, editing = false }: Props = $props();
  const elements = $derived(definition ? paintOrder(definition, editing) : []);
</script>

{#if definition}
  {#each elements as el (el.id)}
    <div
      class="el"
      class:ghost={el.hidden}
      data-element-id={el.id}
      style:left="{el.x}px"
      style:top="{el.y}px"
      style:width="{el.w}px"
      style:height="{el.h}px"
      style:z-index={el.z ?? 0}
    >
      <Widget {el} {state} {views} {lang} />
    </div>
  {/each}
{/if}

<style>
  .el {
    position: absolute;
    box-sizing: border-box;
  }
  .ghost {
    opacity: 0.3;
  }
</style>
