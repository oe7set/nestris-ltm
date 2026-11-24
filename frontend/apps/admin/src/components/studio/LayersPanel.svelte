<script lang="ts">
  // Left column of the studio: add elements (grouped palette, drag onto the
  // stage or click) and the layer list (top first), with eye and lock.
  import { CATALOGUE, PAIR_TYPES, placeable, SLOT_TYPES } from "../../lib/editor/elements";
  import { DRAG_TYPE, slotColor, type LayoutEditor } from "../../lib/editor/layoutEditor.svelte";
  import { t, tDynamic } from "../../lib/i18n.svelte";
  import type { ElementType, LayoutElement } from "../../lib/studio";

  let { editor }: { editor: LayoutEditor } = $props();

  let adding = $state(false);
  const groups: { id: string; types: ElementType[] }[] = [
    { id: "player", types: CATALOGUE.map((c) => c.type).filter((x) => SLOT_TYPES.has(x)) },
    { id: "pair", types: CATALOGUE.map((c) => c.type).filter((x) => PAIR_TYPES.has(x)) },
    { id: "general", types: CATALOGUE.map((c) => c.type).filter((x) => !SLOT_TYPES.has(x) && !PAIR_TYPES.has(x)) },
  ];

  function label(e: LayoutElement): string {
    let text = tDynamic(`builder.type_${e.type}`, e.type);
    if (e.type === "stat") text = tDynamic(`builder.field_${String(e.props?.field ?? "score")}`, text);
    if (e.slot !== undefined && e.slot !== null) text += ` · ${t("studio.slot_short", { n: e.slot + 1 })}`;
    if (e.pair !== undefined && e.pair !== null) text += ` · P${e.pair + 1}`;
    return text;
  }

  const layers = $derived([...editor.ordered].reverse());
</script>

<section class="panel block">
  <div class="row head">
    <h2>{t("builder.layers")} <span class="muted">({editor.def.elements.length})</span></h2>
    <span class="spacer"></span>
    {#if editor.editable}
      <button class="small" class:primary={!adding} aria-expanded={adding} onclick={() => (adding = !adding)}>
        {adding ? t("common.close") : `+ ${t("studio.add_element")}`}
      </button>
    {/if}
  </div>

  {#if adding && editor.editable}
    <div class="add">
      <label class="row inline">
        {t("builder.add_to")}
        <select bind:value={editor.addSlot}>
          {#each editor.slotNumbers as s (s)}<option value={s}>{t("studio.slot_long", { n: s + 1 })}</option>{/each}
        </select>
      </label>
      {#each groups as g (g.id)}
        <span class="group">{tDynamic(`studio.group_${g.id}`, g.id)}</span>
        <div class="palette">
          {#each g.types as type (type)}
            {@const ok = placeable(editor.def, type)}
            <button
              class="tile"
              disabled={!ok}
              title={ok ? t("builder.palette_hint") : t("builder.needs_pair")}
              draggable={ok}
              ondragstart={(e) => e.dataTransfer?.setData(DRAG_TYPE, type)}
              onclick={() => editor.add(type)}
            >
              {tDynamic(`builder.type_${type}`, type)}
            </button>
          {/each}
        </div>
      {/each}
    </div>
  {/if}

  <ul class="layers">
    {#each layers as el (el.id)}
      <li class:on={editor.selected.includes(el.id)} class:err={editor.errorIds.includes(el.id) || editor.problems.has(el.id)}>
        <button class="layer-name" style:--c={slotColor(el)} class:dim={el.hidden} onclick={(e) => editor.select(el.id, e.shiftKey || e.ctrlKey)}>
          <span class="dot"></span>{#if editor.origins.has(el.id)}<span class="chain" title={t("studio.linked_copy")}>⛓</span>{/if}{label(el)}
        </button>
        {#if editor.editable && !editor.origins.has(el.id)}
          <button class="icon" class:off={!el.hidden} title={t("builder.hidden")} aria-label={t("builder.hidden")} aria-pressed={!!el.hidden} onclick={() => editor.patch(el.id, { hidden: !el.hidden })}>
            <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true"><path d="M1 8s2.5-5 7-5 7 5 7 5-2.5 5-7 5-7-5-7-5Z" fill="none" stroke="currentColor" stroke-width="1.4" /><circle cx="8" cy="8" r="2.2" fill="currentColor" />{#if el.hidden}<path d="M2 14 14 2" stroke="currentColor" stroke-width="1.6" />{/if}</svg>
          </button>
          <button class="icon" class:off={!el.locked} title={t("builder.locked")} aria-label={t("builder.locked")} aria-pressed={!!el.locked} onclick={() => editor.patch(el.id, { locked: !el.locked })}>
            <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true"><rect x="3" y="7" width="10" height="7" rx="1.5" fill="currentColor" /><path d={el.locked ? "M5 7V5a3 3 0 0 1 6 0v2" : "M5 7V5a3 3 0 0 1 5.8-1"} fill="none" stroke="currentColor" stroke-width="1.6" /></svg>
          </button>
        {/if}
      </li>
    {:else}
      <li class="muted small empty">{t("studio.no_elements")}</li>
    {/each}
  </ul>
</section>

<style>
  .block {
    display: grid;
    gap: 8px;
    min-height: 0;
    grid-template-rows: auto auto minmax(0, 1fr);
  }
  .head h2 {
    margin: 0;
    font-size: 15px;
  }
  .head .small {
    padding: 3px 10px;
  }
  .add {
    display: grid;
    gap: 6px;
    padding: 8px;
    background: var(--panel-2);
    border-radius: 8px;
  }
  .inline {
    gap: 6px;
    font-size: 13px;
  }
  .inline select {
    flex: 1;
    min-width: 0;
  }
  .chain {
    margin-right: 4px;
    opacity: 0.8;
  }
  .group {
    margin-top: 4px;
    font-size: 11px;
    letter-spacing: 1px;
    text-transform: uppercase;
    color: var(--muted);
  }
  .palette {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 4px;
  }
  .tile {
    text-align: left;
    cursor: grab;
    font-size: 13px;
    padding: 4px 8px;
  }
  .layers {
    list-style: none;
    margin: 0;
    padding: 0;
    display: grid;
    gap: 1px;
    align-content: start;
    overflow: hidden auto;
  }
  .layers li {
    display: flex;
    gap: 2px;
    align-items: center;
    border-radius: 6px;
  }
  .layers li.on {
    background: color-mix(in srgb, var(--accent) 18%, transparent);
  }
  .layers li.err .layer-name {
    color: var(--bad, #f83800);
  }
  .empty {
    padding: 6px;
  }
  .layer-name {
    flex: 1;
    min-width: 0;
    text-align: left;
    border: 0;
    background: none;
    padding: 3px 6px;
    font-size: 13px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .layer-name.dim {
    opacity: 0.5;
  }
  .dot {
    display: inline-block;
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--c);
    margin-right: 6px;
  }
  .icon {
    min-width: 26px;
    padding: 2px 4px;
    border: 0;
    background: none;
  }
  .icon.off {
    opacity: 0.4;
  }
</style>
