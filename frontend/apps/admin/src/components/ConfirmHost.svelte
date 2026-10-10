<script lang="ts">
  // The single confirmation dialog of the app (see lib/confirm.svelte.ts).
  import Modal from "./Modal.svelte";
  import { confirmState } from "../lib/confirm.svelte";
  import { t } from "../lib/i18n.svelte";

  let typed = $state("");
  const pending = $derived(confirmState.current);
  const locked = $derived(!!pending?.typeToConfirm && typed.trim() !== pending.typeToConfirm);

  $effect(() => {
    void pending;
    typed = "";
  });
</script>

{#if pending}
  <Modal title={pending.title} onclose={() => confirmState.answer(false)}>
    {#if pending.text}<p class="text">{pending.text}</p>{/if}
    {#if pending.typeToConfirm}
      <label class="field">
        {t("confirm.type", { text: pending.typeToConfirm })}
        <!-- svelte-ignore a11y_autofocus -->
        <input bind:value={typed} autocomplete="off" autofocus />
      </label>
    {/if}
    {#snippet footer()}
      <button onclick={() => confirmState.answer(false)}>{t("common.cancel")}</button>
      <!-- svelte-ignore a11y_autofocus -->
      <button
        class={pending.danger ? "danger" : "primary"}
        disabled={locked}
        autofocus={!pending.typeToConfirm}
        onclick={() => confirmState.answer(true)}
      >
        {pending.confirmLabel ?? t("common.confirm")}
      </button>
    {/snippet}
  </Modal>
{/if}

<style>
  .text {
    margin: 0;
    white-space: pre-line;
  }
</style>
