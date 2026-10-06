<script lang="ts">
  // Switches for the guide lines (see GuideOverlay.svelte).
  import { guides } from "../lib/guides.svelte";
  import { t } from "../lib/i18n.svelte";
</script>

<div class="guide-tools row">
  <button class:on={guides.visible} onclick={() => guides.toggle("visible")} title={t("guides.hint")}>
    ┼ {t("guides.title")}
  </button>
  {#if guides.visible}
    <div class="seg">
      <button class:on={guides.center} onclick={() => guides.toggle("center")}>{t("guides.center")}</button>
      <button class:on={guides.thirds} onclick={() => guides.toggle("thirds")}>{t("guides.thirds")}</button>
      <button class:on={guides.safe} onclick={() => guides.toggle("safe")} title={t("guides.safe_hint")}>{t("guides.safe")}</button>
    </div>
    {#if guides.custom.length}
      <button onclick={() => guides.setCustom([])}>{t("guides.clear", { n: guides.custom.length })}</button>
    {/if}
  {/if}
</div>

<style>
  .guide-tools {
    gap: 6px;
    align-items: center;
  }
  .guide-tools > button.on {
    border-color: #00e5ff;
    color: #00e5ff;
  }
  .seg {
    display: inline-flex;
    border: 1px solid var(--line);
    border-radius: 8px;
    overflow: hidden;
  }
  .seg button {
    border: 0;
    border-radius: 0;
  }
  .seg button.on {
    background: #00e5ff;
    color: #000;
  }
</style>
