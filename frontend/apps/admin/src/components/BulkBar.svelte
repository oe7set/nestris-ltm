<script lang="ts">
  // Action bar for a multi-select list: sticks to the bottom of the screen
  // while rows are selected.
  import type { Snippet } from "svelte";
  import { t } from "../lib/i18n.svelte";

  interface Props {
    count: number;
    onclear: () => void;
    /** The action buttons. */
    children: Snippet;
  }
  let { count, onclear, children }: Props = $props();
</script>

{#if count > 0}
  <div class="bulk" role="toolbar" aria-label={t("bulk.selected", { n: count })}>
    <strong>{t("bulk.selected", { n: count })}</strong>
    <div class="actions">{@render children()}</div>
    <button class="link" onclick={onclear}>{t("bulk.clear")}</button>
  </div>
{/if}

<style>
  .bulk {
    position: sticky;
    bottom: 12px;
    z-index: 20;
    margin-top: 12px;
    display: flex;
    gap: 12px;
    align-items: center;
    flex-wrap: wrap;
    background: var(--panel-2);
    border: 1px solid var(--accent);
    border-radius: var(--radius);
    padding: 10px 14px;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.45);
  }
  .actions {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
    flex: 1;
  }
  @media (max-width: 640px) {
    .bulk {
      position: fixed;
      left: 8px;
      right: 8px;
      bottom: 8px;
      margin: 0;
    }
    .actions {
      order: 3;
      flex-basis: 100%;
    }
    .actions :global(button) {
      flex: 1 1 auto;
      justify-content: center;
      min-height: 40px;
    }
  }
</style>
