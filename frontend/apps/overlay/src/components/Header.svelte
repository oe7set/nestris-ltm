<script lang="ts">
  import { text, type Lang } from "../lib/format";
  import type { SceneState } from "../lib/types";

  let { state, lang = "de" }: { state: SceneState; lang?: Lang } = $props();
  const mode = $derived(text(lang, `mode_${state.scene.mode}`));
</script>

<header>
  <span class="title">{state.scene.settings.title ?? state.scene.name}</span>
  <span class="round">{text(lang, "round")} {state.round}</span>
  {#if mode}<span class="mode">{mode}</span>{/if}
</header>

<style>
  header {
    display: flex;
    justify-content: center;
    align-items: center;
    gap: 18px;
    height: 56px;
    font-size: 24px;
    letter-spacing: 4px;
  }
  .title {
    color: var(--accent);
    padding: 6px 18px;
    background: var(--panel);
    border: 2px solid var(--frame);
    border-radius: 8px;
  }
  .round,
  .mode {
    font-size: 18px;
    color: var(--text);
    padding: 6px 14px;
    background: var(--panel);
    border: 2px solid var(--frame);
    border-radius: 8px;
  }
  .mode {
    color: var(--cyan);
  }
</style>
