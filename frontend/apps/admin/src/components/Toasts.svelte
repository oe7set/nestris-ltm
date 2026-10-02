<script lang="ts">
  import { toasts } from "../lib/toast.svelte";
</script>

<div class="toasts" aria-live="polite">
  {#each toasts.items as toast (toast.id)}
    <button class="toast {toast.kind}" onclick={() => toasts.dismiss(toast.id)}>{toast.text}</button>
  {/each}
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
  .toast {
    text-align: left;
    padding: 10px 14px;
    border-radius: 8px;
    box-shadow: 0 6px 20px rgba(0, 0, 0, 0.4);
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
</style>
