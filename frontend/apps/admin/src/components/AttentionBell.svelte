<script lang="ts">
  // Bell with the number of open problems; opens the list.
  import AttentionList from "./AttentionList.svelte";
  import { attention } from "../lib/attention.svelte";
  import { t } from "../lib/i18n.svelte";
  import { uiPrefs } from "../lib/uiPrefs.svelte";

  let open = $state(false);
  let box = $state<HTMLElement>();

  function onwindowclick(e: MouseEvent): void {
    if (open && box && !box.contains(e.target as Node)) open = false;
  }
</script>

<svelte:window onclick={onwindowclick} onkeydown={(e) => e.key === "Escape" && (open = false)} />

<div class="bell" bind:this={box}>
  <button
    class="btn {attention.worst ?? ''}"
    aria-expanded={open}
    aria-label={t("attention.bell", { n: attention.count })}
    title={t("attention.title")}
    onclick={() => (open = !open)}
  >
    <span aria-hidden="true">🔔</span>
    {#if attention.count}<span class="count">{attention.count}</span>{/if}
  </button>
  {#if open}
    <div class="pop" role="dialog" aria-label={t("attention.title")}>
      <strong>{t("attention.title")}</strong>
      <AttentionList onpick={() => (open = false)} />
      <label class="check small">
        <input type="checkbox" checked={uiPrefs.alertSound} onchange={() => uiPrefs.toggle("alertSound")} />
        {t("attention.sound")}
      </label>
    </div>
  {/if}
</div>

<style>
  .bell {
    position: relative;
  }
  .btn {
    position: relative;
    padding: 4px 8px;
    min-height: 32px;
  }
  .btn.error {
    border-color: var(--bad);
  }
  .btn.warn {
    border-color: var(--warn);
  }
  .count {
    min-width: 18px;
    height: 18px;
    padding: 0 5px;
    border-radius: 9px;
    background: var(--bad);
    color: #fff;
    font-size: 11px;
    font-weight: 700;
    display: inline-grid;
    place-items: center;
  }
  .btn.warn .count {
    background: var(--warn);
    color: #1a1300;
  }
  .pop {
    position: absolute;
    z-index: 50;
    top: calc(100% + 6px);
    left: 0;
    width: min(340px, calc(100vw - 24px));
    background: var(--panel);
    border: 1px solid var(--line);
    border-radius: var(--radius);
    padding: 12px;
    display: grid;
    gap: 10px;
    box-shadow: 0 10px 30px rgba(0, 0, 0, 0.5);
  }
  @media (max-width: 760px) {
    .pop {
      position: fixed;
      top: 56px;
      left: 12px;
      right: 12px;
      width: auto;
    }
  }
</style>
