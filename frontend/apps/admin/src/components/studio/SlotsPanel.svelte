<script lang="ts">
  // Slots (players) and pairs (who plays against whom) of a layout, and
  // "mirror": copy one player's elements mirrored onto another slot, and
  // links: slots that follow a master slot live (lib/editor/links.ts).
  import { MAX_SLOTS, unpairedSlots } from "../../lib/editor/elements";
  import type { LayoutEditor } from "../../lib/editor/layoutEditor.svelte";
  import { LINK_PRESETS, MAX_LINKS } from "../../lib/editor/links";
  import { t, tDynamic } from "../../lib/i18n.svelte";
  import type { SlotLink } from "../../lib/studio";

  let { editor }: { editor: LayoutEditor } = $props();

  let mirrorFrom = $state(0);
  let mirrorTo = $state(1);
  // The link being set up by hand.
  let draft = $state<SlotLink>({ from: 0, to: 1 });

  const presets = $derived(LINK_PRESETS.filter((p) => p.slots <= editor.def.slots));
  const draftMax = $derived(draft.pair ? editor.def.pairs.length : editor.def.slots);

  function describe(l: SlotLink): string {
    const name = (n: number): string => (l.pair ? `P${n + 1}` : t("studio.slot_short", { n: n + 1 }));
    const parts = [`${name(l.from)} → ${name(l.to)}`];
    if (l.flip_x) parts.push(t("studio.link_flip_x"));
    if (l.flip_y) parts.push(t("studio.link_flip_y"));
    if (l.dx) parts.push(`x ${l.dx > 0 ? "+" : ""}${l.dx}`);
    if (l.dy) parts.push(`y ${l.dy > 0 ? "+" : ""}${l.dy}`);
    return parts.join(" · ");
  }
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
    <div class="links">
      <span class="label">{t("studio.links")}</span>
      <span class="muted small">{t("studio.links_hint")}</span>
      <div class="row wrap">
        {#each presets as p (p.id)}
          <button class="small" title={tDynamic(`studio.preset_${p.id}_hint`, "")} onclick={() => editor.linkPreset(p)}>{tDynamic(`studio.preset_${p.id}`, p.id)}</button>
        {/each}
      </div>
      {#each editor.def.links ?? [] as l, i (i)}
        <div class="row link">
          <span>⛓ {describe(l)}</span>
          <span class="spacer"></span>
          <button class="small" title={t("studio.unlink_hint")} onclick={() => editor.unlink(i)}>{t("studio.unlink")}</button>
        </div>
      {/each}
      <details>
        <summary>{t("studio.link_custom")}</summary>
        <div class="custom">
          {#if editor.def.pairs.length >= 2}
            <label class="check"><input type="checkbox" checked={!!draft.pair} onchange={(e) => (draft = { from: 0, to: 1, pair: e.currentTarget.checked })} /> {t("studio.link_pairs")}</label>
          {/if}
          <div class="row">
            <select bind:value={draft.from}>{#each Array.from({ length: draftMax }, (_, i) => i) as n (n)}<option value={n}>{draft.pair ? `P${n + 1}` : t("studio.slot_long", { n: n + 1 })}</option>{/each}</select>
            <span>→</span>
            <select bind:value={draft.to}>{#each Array.from({ length: draftMax }, (_, i) => i) as n (n)}<option value={n}>{draft.pair ? `P${n + 1}` : t("studio.slot_long", { n: n + 1 })}</option>{/each}</select>
          </div>
          <div class="row wrap">
            <label class="check"><input type="checkbox" bind:checked={draft.flip_x} /> {t("studio.link_flip_x")}</label>
            <label class="check"><input type="checkbox" bind:checked={draft.flip_y} /> {t("studio.link_flip_y")}</label>
          </div>
          <div class="row">
            <label class="offset">x <input type="number" step="8" bind:value={draft.dx} placeholder="0" /></label>
            <label class="offset">y <input type="number" step="8" bind:value={draft.dy} placeholder="0" /></label>
          </div>
          <button disabled={draft.from === draft.to || (editor.def.links?.length ?? 0) >= MAX_LINKS} onclick={() => editor.link({ ...draft })}>{t("studio.link_add")}</button>
        </div>
      </details>
    </div>

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
  .links,
  .custom,
  .mirror {
    display: grid;
    gap: 6px;
  }
  .pair,
  .mirror .row {
    gap: 6px;
  }
  .link {
    gap: 6px;
    font-size: 13px;
  }
  .wrap {
    flex-wrap: wrap;
    gap: 6px;
  }
  .small {
    padding: 3px 10px;
    font-size: 13px;
  }
  .offset {
    display: flex;
    gap: 4px;
    align-items: center;
    flex: 1;
  }
  .offset input {
    min-width: 0;
    width: 100%;
  }
  details summary {
    cursor: pointer;
    font-size: 13px;
  }
  .custom {
    margin-top: 6px;
  }
  .custom select {
    flex: 1;
    min-width: 0;
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
