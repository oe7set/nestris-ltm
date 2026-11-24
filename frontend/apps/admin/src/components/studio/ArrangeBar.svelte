<script lang="ts">
  // The arrange bar above the stage: align (to the selection, the stage, the
  // key element = the first one selected, or the frame around), distribute
  // with equal or fixed gaps, line up in a row/column/grid, same size, and
  // select or style alike. Every action is one undo step.
  import type { AlignMode, Arrangement } from "../../lib/editor/geometry";
  import type { AlignRef, LayoutEditor } from "../../lib/editor/layoutEditor.svelte";
  import { t, tDynamic } from "../../lib/i18n.svelte";

  let { editor }: { editor: LayoutEditor } = $props();

  const ALIGN: { mode: AlignMode; icon: string }[] = [
    { mode: "left", icon: "⇤" },
    { mode: "hcenter", icon: "↔" },
    { mode: "right", icon: "⇥" },
    { mode: "top", icon: "⤒" },
    { mode: "vcenter", icon: "↕" },
    { mode: "bottom", icon: "⤓" },
  ];
  const REFS: AlignRef[] = ["selection", "stage", "key", "frame"];
  const ARRANGE: { kind: Arrangement; icon: string }[] = [
    { kind: "row", icon: "▭▭▭" },
    { kind: "column", icon: "☰" },
    { kind: "grid", icon: "▦" },
  ];

  let ref = $state<AlignRef>("selection");
  /** Fixed gap in px; empty = equal gaps when distributing. */
  let gap = $state<number | null>(null);
  let columns = $state(2);

  const n = $derived(editor.sel.filter((e) => !e.locked).length);
  // With one element, "selection" means the stage (like before).
  const canAlign = $derived(n >= 1 && (ref !== "key" || n >= 2) && (ref !== "frame" || editor.frameAround() !== null));
  const gapPx = $derived(typeof gap === "number" && Number.isFinite(gap) ? Math.max(0, Math.round(gap)) : undefined);
</script>

<!-- Always there while editing (greyed out without a selection), so the stage never jumps. -->
{#if editor.editable}
  <div class="bar" role="toolbar" aria-label={t("studio.arrange")}>
    <label class="ref" title={t("studio.align_ref_hint")}>
      <span>{t("studio.align_ref")}</span>
      <select bind:value={ref} disabled={!n}>
        {#each REFS as r (r)}<option value={r}>{tDynamic(`studio.ref_${r}`, r)}</option>{/each}
      </select>
    </label>
    <div class="group">
      {#each ALIGN as a (a.mode)}
        <button class="icon" disabled={!canAlign} title={tDynamic(`studio.align_${a.mode}`, a.mode)} aria-label={tDynamic(`studio.align_${a.mode}`, a.mode)} onclick={() => editor.alignSelected(a.mode, ref)}>{a.icon}</button>
      {/each}
    </div>
    <span class="sep"></span>
    <div class="group">
      <button class="icon" disabled={n < (gapPx === undefined ? 3 : 2)} title={t("builder.distribute_h")} aria-label={t("builder.distribute_h")} onclick={() => editor.distributeSelected("x", gapPx)}>⇹</button>
      <button class="icon" disabled={n < (gapPx === undefined ? 3 : 2)} title={t("builder.distribute_v")} aria-label={t("builder.distribute_v")} onclick={() => editor.distributeSelected("y", gapPx)}>⇳</button>
      {#each ARRANGE as a (a.kind)}
        <button class="icon" disabled={n < 2} title={tDynamic(`studio.arrange_${a.kind}`, a.kind)} aria-label={tDynamic(`studio.arrange_${a.kind}`, a.kind)} onclick={() => editor.arrangeSelected(a.kind, gapPx ?? 8, columns)}>{a.icon}</button>
      {/each}
      <label class="num" title={t("studio.gap_hint")}>
        {t("studio.gap")}
        <input type="number" min="0" max="960" step="8" bind:value={gap} placeholder={t("studio.gap_equal")} />
      </label>
      <label class="num" title={t("studio.columns")}>
        ▦
        <input type="number" min="1" max="8" bind:value={columns} />
      </label>
    </div>
    <span class="sep"></span>
    <div class="group">
      <button class="small" disabled={n < 2} title={t("studio.same_hint")} onclick={() => editor.matchSizeSelected("w")}>{t("studio.same_w")}</button>
      <button class="small" disabled={n < 2} title={t("studio.same_hint")} onclick={() => editor.matchSizeSelected("h")}>{t("studio.same_h")}</button>
      <button class="small" disabled={n < 2} title={t("studio.same_hint")} onclick={() => editor.matchSizeSelected("both")}>{t("studio.same_both")}</button>
    </div>
    <span class="sep"></span>
    <div class="group">
      <button class="small" disabled={!editor.key} title={t("studio.select_type_hint")} onclick={() => editor.selectSimilar("type")}>{t("studio.select_type")}</button>
      {#if editor.key?.slot != null}
        <button class="small" title={t("studio.select_slot_hint")} onclick={() => editor.selectSimilar("slot")}>{t("studio.select_slot")}</button>
      {/if}
      <button class="small" disabled={!editor.key} title={t("studio.copy_style_hint")} onclick={() => editor.copyStyle()}>{t("studio.copy_style")}</button>
      <button class="small" disabled={!editor.canPasteStyle} title={t("studio.paste_style_hint")} onclick={() => editor.pasteStyle()}>{t("studio.paste_style")}</button>
    </div>
  </div>
{/if}

<style>
  .bar {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 6px 10px;
    padding: 6px 10px;
    background: var(--panel);
    border: 1px solid var(--line);
    border-bottom: 0;
    border-radius: 8px 8px 0 0;
    font-size: 13px;
  }
  .group {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 4px;
  }
  .sep {
    width: 1px;
    align-self: stretch;
    background: var(--line);
  }
  .ref,
  .num {
    display: flex;
    align-items: center;
    gap: 4px;
    color: var(--muted);
  }
  .ref select {
    padding: 2px 6px;
  }
  .num input {
    width: 64px;
    padding: 2px 6px;
  }
  .icon {
    min-width: 30px;
    padding: 2px 6px;
  }
  .small {
    padding: 2px 8px;
    font-size: 13px;
  }
</style>
