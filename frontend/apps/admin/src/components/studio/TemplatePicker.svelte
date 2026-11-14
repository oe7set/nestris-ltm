<script lang="ts">
  // Pick what a scene shows: a template (the scene gets its own, adaptable
  // copy), one of the own layouts, or a fixed built-in layout. Templates are
  // grouped by player count; the most used ones come first.
  import { i18n, t } from "../../lib/i18n.svelte";
  import {
    defaultSettings,
    definitionPreview,
    previewOf,
    type CustomLayout,
    type LayoutChoice,
    type LayoutInfo,
    type Template,
  } from "../../lib/studio";
  import Thumb from "../Thumb.svelte";

  interface Props {
    templates: Template[];
    /** Own layouts with their definitions. */
    customs?: CustomLayout[];
    /** Fixed built-in layouts (not adaptable); empty = not offered. */
    builtins?: LayoutInfo[];
    selected: LayoutChoice | null;
    onpick: (choice: LayoutChoice) => void;
  }
  let { templates, customs = [], builtins = [], selected, onpick }: Props = $props();

  let showFixed = $state(false);
  const en = $derived(i18n.locale === "en");
  const groups = $derived(
    [4, 2, 1]
      .map((n) => ({
        n,
        items: templates.filter((tpl) => tpl.players === n).sort((a, b) => Number(b.featured) - Number(a.featured)),
      }))
      .filter((g) => g.items.length),
  );

  const tplChoice = (template: Template): LayoutChoice => ({ kind: "template", template });
  const keyChoice = (key: string): LayoutChoice => ({ kind: "layout", key });

  function isOn(choice: LayoutChoice): boolean {
    if (!selected) return false;
    if (choice.kind === "template") return selected.kind === "template" && selected.template.id === choice.template.id;
    return selected.kind === "layout" && selected.key === choice.key;
  }
</script>

<div class="picker">
  {#each groups as g (g.n)}
    <h3>{t("studio.players_n", { n: g.n })}</h3>
    <div class="grid">
      {#each g.items as tpl (tpl.id)}
        {@const choice = tplChoice(tpl)}
        <button class="pick" class:on={isOn(choice)} class:featured={tpl.featured} aria-pressed={isOn(choice)} onclick={() => onpick(choice)}>
          <Thumb config={definitionPreview(tpl.definition, en ? tpl.name_en : tpl.name_de)} />
          <strong>{en ? tpl.name_en : tpl.name_de}{#if tpl.featured}<span class="star" title={t("studio.featured")}> ★</span>{/if}</strong>
          <span class="muted small">{en ? tpl.description_en : tpl.description_de}</span>
        </button>
      {/each}
    </div>
  {/each}

  {#if customs.length}
    <h3>{t("studio.own_layouts")}</h3>
    <div class="grid">
      {#each customs as l (l.id)}
        {@const choice = keyChoice(l.key)}
        <button class="pick" class:on={isOn(choice)} aria-pressed={isOn(choice)} disabled={!l.valid || !l.definition} onclick={() => onpick(choice)}>
          {#if l.definition}<Thumb config={definitionPreview(l.definition, l.name)} />{/if}
          <strong>{l.name}</strong>
          <span class="muted small">{t("studio.slots", { n: l.slots ?? "?" })}{l.used_by?.length ? ` · ${t("studio.used_by", { scenes: l.used_by.join(", ") })}` : ""}</span>
        </button>
      {/each}
    </div>
  {/if}

  {#if builtins.length}
    <button class="link fixed-toggle" aria-expanded={showFixed} onclick={() => (showFixed = !showFixed)}>
      {showFixed ? "▾" : "▸"} {t("studio.fixed_layouts")}
    </button>
    {#if showFixed}
      <p class="muted small">{t("studio.fixed_hint")}</p>
      <div class="grid">
        {#each builtins as l (l.id)}
          {@const choice = keyChoice(l.id)}
          <button class="pick" class:on={isOn(choice)} aria-pressed={isOn(choice)} onclick={() => onpick(choice)}>
            <Thumb config={previewOf({ slug: "preview", name: en ? l.title_en : l.title_de, layout: l.id, mode: "none", settings: defaultSettings() }, l)} />
            <strong>{en ? l.title_en : l.title_de}</strong>
            <span class="muted small">{en ? l.description_en : l.description_de}</span>
          </button>
        {/each}
      </div>
    {/if}
  {/if}
</div>

<style>
  .picker {
    display: grid;
    gap: 8px;
  }
  h3 {
    margin: 8px 0 0;
    font-size: 14px;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 1px;
  }
  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(230px, 1fr));
    gap: 10px;
  }
  .pick {
    display: grid;
    gap: 6px;
    padding: 6px;
    text-align: left;
    align-content: start;
    background: var(--panel-2);
  }
  .pick.featured {
    border-color: color-mix(in srgb, var(--accent) 45%, var(--line));
  }
  .pick.on {
    border-color: var(--accent);
    box-shadow: 0 0 0 2px var(--accent);
  }
  .star {
    color: var(--accent);
  }
  .fixed-toggle {
    justify-self: start;
    margin-top: 8px;
  }
</style>
