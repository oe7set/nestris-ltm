<script lang="ts" generics="T extends string">
  // Tab bar used by every page with tabs: roles for screen readers, arrow
  // keys move between tabs, the bar wraps on narrow screens. The page keeps
  // the active tab (usually in the ?tab= query, see lib/tabs.ts).
  import type { Snippet } from "svelte";

  interface Props {
    tabs: { id: T; label: string }[];
    active: T;
    onchange: (id: T) => void;
    /** Extra controls on the right end of the bar. */
    children?: Snippet;
  }
  let { tabs, active, onchange, children }: Props = $props();

  let bar = $state<HTMLElement>();

  function onkeydown(e: KeyboardEvent, index: number): void {
    const step = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
    if (!step) return;
    e.preventDefault();
    const next = tabs[(index + step + tabs.length) % tabs.length]!;
    onchange(next.id);
    queueMicrotask(() => bar?.querySelector<HTMLElement>(`[data-tab="${next.id}"]`)?.focus());
  }
</script>

<div class="tabs" role="tablist" bind:this={bar}>
  {#each tabs as tab, i (tab.id)}
    <button
      role="tab"
      data-tab={tab.id}
      aria-selected={tab.id === active}
      tabindex={tab.id === active ? 0 : -1}
      class:on={tab.id === active}
      onclick={() => onchange(tab.id)}
      onkeydown={(e) => onkeydown(e, i)}>{tab.label}</button
    >
  {/each}
  {#if children}
    <span class="spacer"></span>
    {@render children()}
  {/if}
</div>

<style>
  .tabs {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 6px;
    margin-bottom: 12px;
  }
  .tabs button.on {
    border-color: var(--accent);
    color: var(--accent);
  }
</style>
