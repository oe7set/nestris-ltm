<script lang="ts">
  // Right column of the studio: the selected element (position and size in
  // stage pixels, slot/pair, its own options, order), or tools for a
  // multiple selection (align, distribute).
  import { OPTIONAL_PAIR_TYPES, PAIR_TYPES, SLOT_TYPES, STAT_FIELDS } from "../../lib/editor/elements";
  import type { AlignMode } from "../../lib/editor/geometry";
  import type { LayoutEditor } from "../../lib/editor/layoutEditor.svelte";
  import { t, tDynamic } from "../../lib/i18n.svelte";
  import type { LayoutElement } from "../../lib/studio";

  let { editor }: { editor: LayoutEditor } = $props();

  const ALIGN_MODES: { mode: AlignMode; icon: string }[] = [
    { mode: "left", icon: "⇤" },
    { mode: "hcenter", icon: "↔" },
    { mode: "right", icon: "⇥" },
    { mode: "top", icon: "⤒" },
    { mode: "vcenter", icon: "↕" },
    { mode: "bottom", icon: "⤓" },
  ];
  const GEOM = [
    { f: "x", label: "X" },
    { f: "y", label: "Y" },
    { f: "w", label: "builder_w" },
    { f: "h", label: "builder_h" },
  ] as const;
  const TEXT_ALIGN_TYPES = ["stat", "name", "hearts", "nametag", "title", "round", "text", "ranking"];
  /** Types with a box behind their content (prop "frame"). */
  const FRAME_TYPES = ["stat", "name", "nametag", "next", "title", "round", "diff_graph", "ranking"];

  function frameOf(el: LayoutElement): string {
    const p = el.props ?? {};
    return typeof p.frame === "string" ? p.frame : p.boxed === false ? "none" : "nes";
  }

  /** One undo step; the older "boxed" goes away once "frame" says it. */
  function setFrame(el: LayoutElement, value: string): void {
    const props: Record<string, unknown> = { ...(el.props ?? {}) };
    delete props.boxed;
    if (value === "nes") delete props.frame;
    else props.frame = value;
    editor.patch(el.id, { props });
  }
</script>

<section class="panel block">
  <h2>{t("builder.properties")}</h2>
  {#if !editor.editable}
    <p class="muted small">{t("studio.builtin_props")}</p>
  {:else if editor.one}
    {@const el = editor.one}
    {@const p = el.props ?? {}}
    <div class="row title">
      <strong>{tDynamic(`builder.type_${el.type}`, el.type)}</strong>
      <span class="muted small">{el.id}</span>
    </div>

    <div class="geom" title={t("studio.pixels_hint")}>
      {#each GEOM as g (g.f)}
        <label>
          <span>{g.label === "X" || g.label === "Y" ? g.label : t(`studio.${g.label}`)}</span>
          <input type="number" step="1" value={el[g.f]} disabled={el.locked} onchange={(e) => editor.setGeom(el, g.f, e.currentTarget.value)} />
          <span class="unit">px</span>
        </label>
      {/each}
    </div>
    <div class="row wrap">
      <button class="small" disabled={el.locked} onclick={() => editor.centreSelected("x")}>{t("studio.centre_h")}</button>
      <button class="small" disabled={el.locked} onclick={() => editor.centreSelected("y")}>{t("studio.centre_v")}</button>
    </div>

    {#if SLOT_TYPES.has(el.type)}
      <label class="field">{t("builder.slot")}
        <select value={el.slot ?? 0} onchange={(e) => editor.patch(el.id, { slot: Number(e.currentTarget.value) })}>
          {#each editor.slotNumbers as s (s)}<option value={s}>{t("studio.slot_long", { n: s + 1 })}</option>{/each}
        </select>
      </label>
    {/if}
    {#if PAIR_TYPES.has(el.type) || OPTIONAL_PAIR_TYPES.has(el.type)}
      <label class="field">{t("builder.pair")}
        <select
          value={el.pair ?? ""}
          onchange={(e) => editor.patch(el.id, { pair: e.currentTarget.value === "" ? null : Number(e.currentTarget.value) })}
        >
          {#if OPTIONAL_PAIR_TYPES.has(el.type)}<option value="">{t("builder.pair_none")}</option>{/if}
          {#each editor.def.pairs as pair, i (i)}<option value={i}>P{i + 1}: {t("studio.slot_long", { n: pair[0] + 1 })} vs {pair[1] + 1}</option>{/each}
        </select>
      </label>
    {/if}

    {#if el.type === "stat"}
      <label class="field">{t("builder.field")}
        <select value={p.field ?? "score"} onchange={(e) => editor.setProp(el, "field", e.currentTarget.value)}>
          {#each STAT_FIELDS as f (f)}<option value={f}>{tDynamic(`builder.field_${f}`, f)}</option>{/each}
        </select>
      </label>
      <label class="field">{t("builder.label")}
        <input value={p.label ?? ""} placeholder={t("builder.label_auto")} maxlength="24" oninput={(e) => editor.setProp(el, "label", e.currentTarget.value)} />
      </label>
      <label class="check"><input type="checkbox" checked={p.show_label !== false} onchange={(e) => editor.setProp(el, "show_label", e.currentTarget.checked)} /> {t("builder.show_label")}</label>
    {/if}
    {#if FRAME_TYPES.includes(el.type)}
      <label class="field">{el.type === "ranking" ? t("studio.frame_entries") : t("studio.frame")}
        <select value={frameOf(el)} onchange={(e) => setFrame(el, e.currentTarget.value)}>
          {#each ["nes", "panel", "none"] as f (f)}<option value={f}>{tDynamic(`studio.frame_${f}`, f)}</option>{/each}
        </select>
      </label>
    {/if}
    {#if el.type === "next"}
      <label class="check"><input type="checkbox" checked={p.show_label !== false} onchange={(e) => editor.setProp(el, "show_label", e.currentTarget.checked)} /> {t("builder.show_label")}</label>
    {/if}
    {#if el.type === "title" || el.type === "text"}
      <label class="field">{t("builder.text")}
        <input
          value={p.text ?? ""}
          placeholder={el.type === "title" ? t("builder.title_auto") : ""}
          maxlength={el.type === "title" ? 64 : 200}
          oninput={(e) => editor.setProp(el, "text", e.currentTarget.value)}
        />
      </label>
    {/if}
    {#if el.type === "text"}
      <label class="field">{t("builder.size")}
        <input type="number" min="8" max="160" value={p.size ?? 24} onchange={(e) => editor.setProp(el, "size", Math.min(160, Math.max(8, Number(e.currentTarget.value) || 24)))} />
      </label>
    {/if}
    {#if el.type === "ranking"}
      <label class="field">{t("builder.direction")}
        <select value={p.direction ?? "row"} onchange={(e) => editor.setProp(el, "direction", e.currentTarget.value)}>
          <option value="row">{t("builder.dir_row")}</option>
          <option value="column">{t("builder.dir_column")}</option>
        </select>
      </label>
      <label class="check"><input type="checkbox" checked={p.show_points !== false} onchange={(e) => editor.setProp(el, "show_points", e.currentTarget.checked ? null : false)} /> {t("studio.show_points")}</label>
    {/if}
    {#if TEXT_ALIGN_TYPES.includes(el.type)}
      <label class="field">{t("builder.align_text")}
        <select
          value={p.align ?? (["nametag", "title", "round", "ranking"].includes(el.type) ? "center" : "left")}
          onchange={(e) => editor.setProp(el, "align", e.currentTarget.value)}
        >
          {#each ["left", "center", "right"] as a (a)}<option value={a}>{tDynamic(`builder.align_${a}`, a)}</option>{/each}
        </select>
      </label>
    {/if}
    {#if el.type === "stat" || el.type === "text"}
      <div class="row color">
        <span>{t("builder.color")}</span>
        <input type="color" value={typeof p.color === "string" ? p.color : "#fcfcfc"} oninput={(e) => editor.setProp(el, "color", e.currentTarget.value)} />
        {#if p.color}<button class="link" onclick={() => editor.setProp(el, "color", null)}>{t("builder.color_auto")}</button>{/if}
      </div>
    {/if}
    {#if el.type === "name"}
      <label class="check"><input type="checkbox" checked={!!p.show_rank} onchange={(e) => editor.setProp(el, "show_rank", e.currentTarget.checked)} /> {t("builder.show_rank")}</label>
    {/if}
    {#if el.type === "nametag"}
      <label class="check"><input type="checkbox" checked={!!p.show_round} onchange={(e) => editor.setProp(el, "show_round", e.currentTarget.checked)} /> {t("builder.show_round")}</label>
    {/if}
    {#if el.type === "camera"}
      <label class="check"><input type="checkbox" checked={p.framed !== false} onchange={(e) => editor.setProp(el, "framed", e.currentTarget.checked)} /> {t("builder.framed")}</label>
      <p class="muted small">{t("studio.camera_hint")}</p>
    {/if}
    {#if el.type === "frame"}
      <label class="field">{t("builder.frame_style")}
        <select value={p.style ?? "nes"} onchange={(e) => editor.setProp(el, "style", e.currentTarget.value)}>
          <option value="nes">{t("builder.frame_nes")}</option>
          <option value="panel">{t("builder.frame_panel")}</option>
        </select>
      </label>
    {/if}

    <div class="row wrap">
      <label class="check"><input type="checkbox" checked={!!el.hidden} onchange={(e) => editor.patch(el.id, { hidden: e.currentTarget.checked })} /> {t("builder.hidden")}</label>
      <label class="check"><input type="checkbox" checked={!!el.locked} onchange={(e) => editor.patch(el.id, { locked: e.currentTarget.checked })} /> {t("builder.locked")}</label>
    </div>

    <span class="label">{t("studio.order")}</span>
    <div class="row wrap">
      <button class="small" onclick={() => editor.restack(el.id, "top")}>{t("builder.to_front")}</button>
      <button class="small" onclick={() => editor.restack(el.id, "up")}>{t("builder.forward")}</button>
      <button class="small" onclick={() => editor.restack(el.id, "down")}>{t("builder.backward")}</button>
      <button class="small" onclick={() => editor.restack(el.id, "bottom")}>{t("builder.to_back")}</button>
    </div>
    <div class="row wrap">
      <button onclick={() => editor.duplicateSelected()}>{t("builder.duplicate")}</button>
      <button class="danger" disabled={el.locked} onclick={() => editor.removeSelected()}>{t("builder.delete")}</button>
    </div>
  {:else if editor.sel.length > 1}
    <p>{t("builder.selected_n", { n: editor.sel.length })}</p>
    <span class="label">{t("builder.align")}</span>
    <div class="row wrap">
      {#each ALIGN_MODES as a (a.mode)}
        <button class="icon" title={tDynamic(`studio.align_${a.mode}`, a.mode)} aria-label={tDynamic(`studio.align_${a.mode}`, a.mode)} onclick={() => editor.alignSelected(a.mode)}>{a.icon}</button>
      {/each}
    </div>
    {#if editor.sel.length > 2}
      <div class="row wrap">
        <button class="small" onclick={() => editor.distributeSelected("x")}>{t("builder.distribute_h")}</button>
        <button class="small" onclick={() => editor.distributeSelected("y")}>{t("builder.distribute_v")}</button>
      </div>
    {/if}
    <div class="row wrap">
      <button class="small" onclick={() => editor.centreSelected("x")}>{t("studio.centre_h")}</button>
      <button class="small" onclick={() => editor.centreSelected("y")}>{t("studio.centre_v")}</button>
    </div>
    <div class="row wrap">
      <button onclick={() => editor.duplicateSelected()}>{t("builder.duplicate")}</button>
      <button class="danger" onclick={() => editor.removeSelected()}>{t("builder.delete")}</button>
    </div>
  {:else}
    <p class="muted small">{t("builder.nothing_selected")}</p>
    <p class="muted small">{t("studio.keys")}</p>
  {/if}
</section>

<style>
  .block {
    display: grid;
    gap: 10px;
    align-content: start;
  }
  h2 {
    margin: 0;
    font-size: 15px;
  }
  .title {
    gap: 8px;
    align-items: baseline;
  }
  .label {
    font-size: 13px;
    color: var(--muted);
  }
  .geom {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 6px;
  }
  .geom label {
    display: grid;
    grid-template-columns: auto minmax(0, 1fr) auto;
    align-items: center;
    gap: 6px;
    font-size: 13px;
  }
  .geom input {
    min-width: 0;
    width: 100%;
  }
  .unit {
    color: var(--muted);
    font-size: 12px;
  }
  .wrap {
    flex-wrap: wrap;
    gap: 6px;
  }
  .small {
    padding: 3px 10px;
    font-size: 13px;
  }
  .icon {
    min-width: 34px;
    padding: 4px 8px;
  }
  .color {
    gap: 8px;
    align-items: center;
  }
  .color input {
    width: 34px;
    height: 26px;
    padding: 0;
  }
</style>
