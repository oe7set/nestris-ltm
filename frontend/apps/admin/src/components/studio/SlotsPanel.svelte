<script lang="ts">
  // Slots (players) and pairs (who plays against whom) of a layout, and
  // "mirror": copy one player's elements mirrored onto another slot.
  import { MAX_SLOTS, unpairedSlots } from "../../lib/editor/elements";
  import type { LayoutEditor } from "../../lib/editor/layoutEditor.svelte";
  import { t } from "../../lib/i18n.svelte";

  let { editor }: { editor: LayoutEditor } = $props();

  let mirrorFrom = $state(0);
  let mirrorTo = $state(1);
</script>

<section class="panel block">
  <h2>{t("studio.slots_pairs")}</h2>
  <label class="field">
    {t("builder.slots")}
    <select value={editor.def.slots} disabled={!editor.editable} onchange={(e) => editor.changeSlots(e.currentTarget.value)}>
      {#each Array.from({ length: MAX_SLOTS }, (_, i) => i + 1) as n (n)}<option value={n}>{n}</option>{/each}
    </select>
  </label>

  <div class="pairs">
    <span class="label">{t("builder.pairs")}</span>
    {#each editor.def.pairs as pair, i (i)}
      <div class="row pair">
        <span class="muted">P{i + 1}</span>
        <select value={pair[0]} disabled={!editor.editable} onchange={(e) => editor.setPairSlot(i, 0, Number(e.currentTarget.value))}>
          {#each editor.slotNumbers as s (s)}<option value={s}>S{s + 1}</option>{/each}
        </select>
        <span>vs</span>
        <select value={pair[1]} disabled={!editor.editable} onchange={(e) => editor.setPairSlot(i, 1, Number(e.currentTarget.value))}>
          {#each editor.slotNumbers as s (s)}<option value={s}>S{s + 1}</option>{/each}
        </select>
        {#if editor.editable}
          <button class="icon" aria-label={t("builder.delete")} onclick={() => editor.changePairs(editor.def.pairs.filter((_, j) => j !== i))}>✕</button>
        {/if}
      </div>
    {:else}
      <span class="muted small">{t("builder.no_pairs")}</span>
    {/each}
    {#if editor.editable && unpairedSlots(editor.def).length >= 2 && editor.def.pairs.length < 4}
      <button onclick={() => editor.addPair()}>{t("builder.add_pair")}</button>
    {/if}
    <span class="muted small">{t("builder.pairs_hint")}</span>
  </div>

  {#if editor.def.slots >= 2 && editor.editable}
    <div class="mirror">
      <span class="label">{t("builder.mirror")}</span>
      <div class="row">
        <select bind:value={mirrorFrom}>{#each editor.slotNumbers as s (s)}<option value={s}>{t("studio.slot_long", { n: s + 1 })}</option>{/each}</select>
        <span>→</span>
        <select bind:value={mirrorTo}>{#each editor.slotNumbers as s (s)}<option value={s}>{t("studio.slot_long", { n: s + 1 })}</option>{/each}</select>
      </div>
      <button disabled={mirrorFrom === mirrorTo} onclick={() => editor.mirror(mirrorFrom, mirrorTo)}>
        {t("builder.mirror_run", { from: mirrorFrom + 1, to: mirrorTo + 1 })}
      </button>
      <span class="muted small">{t("builder.mirror_hint")}</span>
    </div>
  {/if}
</section>

<style>
  .block {
    display: grid;
    gap: 10px;
  }
  h2 {
    margin: 0;
    font-size: 15px;
  }
  .label {
    font-size: 13px;
    color: var(--muted);
  }
  .pairs,
  .mirror {
    display: grid;
    gap: 6px;
  }
  .pair,
  .mirror .row {
    gap: 6px;
  }
  .pair select,
  .mirror select {
    flex: 1;
    min-width: 0;
  }
  .icon {
    min-width: 30px;
    padding: 2px 6px;
  }
</style>
