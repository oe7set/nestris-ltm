<script lang="ts">
  import type { Snippet } from "svelte";
  import { t } from "../lib/i18n.svelte";

  interface Props {
    title: string;
    onclose: () => void;
    children: Snippet;
    footer?: Snippet;
    /** Wider dialog (tables, previews). */
    wide?: boolean;
    /** Unsaved input: Esc and ✕ ask before closing. */
    dirty?: boolean;
  }
  let { title, onclose, children, footer, wide = false, dirty = false }: Props = $props();

  const titleId = `dlg-${Math.random().toString(36).slice(2, 8)}`;

  async function requestClose(): Promise<void> {
    if (dirty) {
      const { confirmAsync } = await import("../lib/confirm.svelte");
      const ok = await confirmAsync({ title: t("common.unsaved_confirm"), danger: true, confirmLabel: t("common.discard") });
      if (!ok) return;
    }
    onclose();
  }

  let dialog: HTMLDialogElement;

  $effect(() => {
    dialog.showModal();
    return () => dialog.close();
  });
</script>

<dialog bind:this={dialog} class:wide aria-labelledby={titleId} oncancel={(e) => { e.preventDefault(); void requestClose(); }}>
  <header>
    <strong id={titleId}>{title}</strong>
    <button class="link" onclick={() => void requestClose()} aria-label={t("common.close")}>✕</button>
  </header>
  <div class="body">{@render children()}</div>
  {#if footer}
    <footer>{@render footer()}</footer>
  {/if}
</dialog>

<style>
  dialog {
    background: var(--panel);
    color: var(--text);
    border: 1px solid var(--line);
    border-radius: var(--radius);
    padding: 0;
    width: min(560px, calc(100vw - 32px));
  }
  dialog.wide {
    width: min(1100px, calc(100vw - 32px));
  }
  dialog::backdrop {
    background: rgba(3, 6, 15, 0.7);
  }
  header,
  footer {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 12px 16px;
  }
  header {
    justify-content: space-between;
    border-bottom: 1px solid var(--line);
  }
  footer {
    justify-content: flex-end;
    border-top: 1px solid var(--line);
  }
  .body {
    padding: 16px;
    display: grid;
    gap: 12px;
  }
</style>
