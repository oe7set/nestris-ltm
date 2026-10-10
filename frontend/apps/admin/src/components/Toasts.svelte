<script lang="ts">
  import { t } from "../lib/i18n.svelte";
  import { toasts, type Toast } from "../lib/toast.svelte";

  async function act(toast: Toast): Promise<void> {
    toasts.dismiss(toast.id);
    try {
      await toast.action?.run();
    } catch (e) {
      toasts.error(e);
    }
  }
</script>

<div class="toasts">
  <div aria-live="polite" class="stack">
    {#each toasts.items.filter((x) => x.kind === "ok") as toast (toast.id)}
      <div class="toast ok">
        <span>{toast.text}</span>
        {#if toast.action}
          <button class="act" onclick={() => act(toast)}>{toast.action.label}</button>
        {/if}
        <button class="close" onclick={() => toasts.dismiss(toast.id)} aria-label={t("common.close")}>✕</button>
      </div>
    {/each}
  </div>
  <div role="alert" class="stack">
    {#each toasts.items.filter((x) => x.kind === "error") as toast (toast.id)}
      <div class="toast error">
        <span>{toast.text}</span>
        <button class="close" onclick={() => toasts.dismiss(toast.id)} aria-label={t("common.close")}>✕</button>
      </div>
    {/each}
  </div>
</div>

<style>
  .toasts {
    position: fixed;
    right: 16px;
    bottom: 16px;
    display: grid;
    gap: 8px;
    z-index: 100;
    max-width: min(420px, calc(100vw - 32px));
  }
  .stack {
    display: grid;
    gap: 8px;
  }
  /* Phones: the bottom edge belongs to the bulk action bar. */
  @media (max-width: 640px) {
    .toasts {
      top: 64px;
      bottom: auto;
      left: 16px;
    }
  }
  .toast {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 10px 10px 10px 14px;
    border: 1px solid var(--line);
    border-radius: 8px;
    box-shadow: 0 6px 20px rgba(0, 0, 0, 0.4);
  }
  .toast span {
    flex: 1;
  }
  .toast.ok {
    background: #0f2a1a;
    border-color: #14532d;
    color: #bbf7d0;
  }
  .toast.error {
    background: #2a1215;
    border-color: #7f1d1d;
    color: #fecaca;
  }
  .act {
    font-weight: 600;
    color: var(--accent);
    background: transparent;
    border-color: currentColor;
    padding: 2px 10px;
  }
  .close {
    background: none;
    border: none;
    color: inherit;
    opacity: 0.7;
    padding: 2px 6px;
  }
</style>
