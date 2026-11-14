<script lang="ts">
  // Scene studio, overview: every scene with a live thumbnail and its OBS
  // address. "New scene" starts from a template (1, 2 or 4 players) and the
  // scene gets its own, adaptable layout. Own layouts without a scene, import
  // and export are one level down.
  import { onMount } from "svelte";
  import Modal from "../components/Modal.svelte";
  import TemplatePicker from "../components/studio/TemplatePicker.svelte";
  import Thumb from "../components/Thumb.svelte";
  import { api, ApiError } from "../lib/api";
  import { copyText } from "../lib/clipboard";
  import { confirmAsync } from "../lib/confirm.svelte";
  import { i18n, t, tDynamic } from "../lib/i18n.svelte";
  import { router } from "../lib/router.svelte";
  import {
    downloadExport,
    readImportFile,
    slugify,
    type CustomLayout,
    type LayoutChoice,
    type LayoutInfo,
    type SceneRow,
    type Template,
  } from "../lib/studio";
  import { toasts } from "../lib/toast.svelte";

  let scenes = $state<SceneRow[]>([]);
  let layouts = $state<LayoutInfo[]>([]);
  let customs = $state<CustomLayout[]>([]);
  let templates = $state.raw<Template[]>([]);
  let selected = $state<Set<number>>(new Set());
  let loading = $state(true);
  let headMenu = $state(false);
  let cardMenu = $state<number | null>(null);
  let showLayouts = $state(false);

  // New scene dialog
  let creating = $state(false);
  let newName = $state("");
  let newSlug = $state("");
  let slugTouched = $state(false);
  let choice = $state<LayoutChoice | null>(null);

  // Import dialog
  interface ImportItem {
    slug?: string;
    id?: string;
    name: string;
    status: "new" | "conflict" | "same";
    errors: string[];
    existing_name?: string;
    suggested_slug?: string;
    layout?: string;
  }
  let importFile = $state<unknown>(null);
  let importReport = $state<{ ok: boolean; scenes: ImportItem[]; layouts: ImportItem[] } | null>(null);
  let sceneDecisions = $state<Record<string, string>>({});
  let layoutDecisions = $state<Record<string, string>>({});
  let importing = $state(false);
  let fileInput: HTMLInputElement;

  async function load(): Promise<void> {
    try {
      [scenes, layouts, customs, templates] = await Promise.all([
        api<SceneRow[]>("/api/scenes"),
        api<LayoutInfo[]>("/api/scenes/layouts"),
        api<CustomLayout[]>("/api/overlay-layouts"),
        api<Template[]>("/api/studio/templates"),
      ]);
    } catch (e) {
      toasts.error(e);
    } finally {
      loading = false;
    }
  }

  function layoutTitle(key: string): string {
    const own = customs.find((c) => c.key === key);
    if (own) {
      // An adapted scene: name the template it came from.
      const tpl = templates.find((x) => x.id === own.template_id);
      if (!tpl) return own.name;
      return t("studio.adapted_from", { name: i18n.locale === "en" ? tpl.name_en : tpl.name_de });
    }
    const l = layouts.find((x) => x.id === key);
    if (!l) return key;
    return i18n.locale === "en" ? l.title_en : l.title_de;
  }

  const isCustom = (key: string): boolean => key.startsWith("custom:");

  // ---- scenes

  function openCreate(): void {
    newName = "";
    newSlug = "";
    slugTouched = false;
    choice = templates.find((tpl) => tpl.featured) ? { kind: "template", template: templates.find((tpl) => tpl.featured)! } : null;
    creating = true;
  }

  function pick(next: LayoutChoice): void {
    choice = next;
    // A name to start with: the template's name, until the user types one.
    if (!newName.trim() && next.kind === "template") {
      newName = i18n.locale === "en" ? next.template.name_en : next.template.name_de;
      if (!slugTouched) newSlug = slugify(newName);
    }
  }

  async function create(): Promise<void> {
    if (!choice) return;
    try {
      const body =
        choice.kind === "template"
          ? { name: newName.trim(), slug: newSlug.trim(), template: choice.template.id, settings: { style: "nes" } }
          : { name: newName.trim(), slug: newSlug.trim(), layout: choice.key, settings: { style: "nes" } };
      const scene = await api<SceneRow>("/api/scenes", { method: "POST", body });
      creating = false;
      router.go(`/studio/scene/${scene.id}`);
    } catch (e) {
      toasts.error(e);
    }
  }

  async function duplicate(scene: SceneRow): Promise<void> {
    cardMenu = null;
    try {
      const copy = await api<SceneRow>(`/api/scenes/${scene.id}/duplicate`, { method: "POST", body: {} });
      toasts.ok(t("studio.duplicated", { name: copy.name }));
      await load();
    } catch (e) {
      toasts.error(e);
    }
  }

  async function remove(scene: SceneRow): Promise<void> {
    cardMenu = null;
    if (!(await confirmAsync({ title: t("studio.confirm_delete_scene", { name: scene.name }), danger: true, confirmLabel: t("common.delete") }))) return;
    try {
      await api(`/api/scenes/${scene.id}`, { method: "DELETE" });
      // Its own layout goes too when no other scene uses it.
      const own = customs.find((c) => c.key === scene.layout);
      if (own && (own.used_by ?? []).every((slug) => slug === scene.slug)) {
        await api(`/api/overlay-layouts/${own.id}`, { method: "DELETE" }).catch(() => {});
      }
      const next = new Set(selected);
      next.delete(scene.id);
      selected = next;
      await load();
    } catch (e) {
      toasts.error(e);
    }
  }

  function toggle(id: number): void {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    selected = next;
  }

  async function exportScenes(ids: number[] | null): Promise<void> {
    headMenu = false;
    cardMenu = null;
    try {
      await downloadExport(ids ? { scenes: ids.join(",") } : {});
    } catch (e) {
      toasts.error(e);
    }
  }

  async function copyUrl(scene: SceneRow): Promise<void> {
    try {
      await copyText(`${location.origin}/o/${scene.slug}`);
      toasts.ok(t("studio.url_copied"));
    } catch (e) {
      toasts.error(e);
    }
  }

  // ---- own layouts

  async function duplicateLayout(l: CustomLayout): Promise<void> {
    try {
      await api(`/api/overlay-layouts/${l.id}/duplicate`, { method: "POST", body: {} });
      await load();
    } catch (e) {
      toasts.error(e);
    }
  }

  async function removeLayout(l: CustomLayout): Promise<void> {
    if (!(await confirmAsync({ title: t("studio.confirm_delete_layout", { name: l.name }), danger: true, confirmLabel: t("common.delete") }))) return;
    try {
      await api(`/api/overlay-layouts/${l.id}`, { method: "DELETE" });
      await load();
    } catch (e) {
      toasts.error(e);
    }
  }

  // ---- import

  async function pickFile(event: Event): Promise<void> {
    const input = event.currentTarget as HTMLInputElement;
    const file = input.files?.[0];
    input.value = "";
    if (!file) return;
    try {
      importFile = await readImportFile(file);
      importReport = await api("/api/studio/import", { method: "POST", body: { file: importFile, dry_run: true } });
      sceneDecisions = Object.fromEntries(
        importReport!.scenes.map((s) => [s.slug!, s.status === "new" ? "create" : "rename"]),
      );
      layoutDecisions = Object.fromEntries(
        importReport!.layouts.map((l) => [l.id!, l.status === "new" ? "create" : l.status === "same" ? "keep" : "copy"]),
      );
    } catch (e) {
      importFile = null;
      importReport = null;
      toasts.error(e instanceof ApiError || e instanceof Error ? e : String(e));
    }
  }

  async function runImport(): Promise<void> {
    importing = true;
    try {
      const result = await api<{ imported: { scenes: string[]; layouts: string[] } }>("/api/studio/import", {
        method: "POST",
        body: { file: importFile, dry_run: false, scenes: sceneDecisions, layouts: layoutDecisions },
      });
      toasts.ok(t("studio.imported", { scenes: result.imported.scenes.length, layouts: result.imported.layouts.length }));
      importReport = null;
      importFile = null;
      await load();
    } catch (e) {
      toasts.error(e);
    } finally {
      importing = false;
    }
  }

  const sceneOptions: Record<string, string[]> = { new: ["create", "skip"], conflict: ["rename", "overwrite", "skip"] };
  const layoutOptions: Record<string, string[]> = {
    new: ["create", "skip"],
    same: ["keep", "copy", "skip"],
    conflict: ["keep", "replace", "copy", "skip"],
  };

  // Own layouts that no scene uses (the rest live in their scene).
  const loose = $derived(customs.filter((c) => !(c.used_by ?? []).length));
  const fixed = $derived(layouts.filter((l) => !l.custom && l.id !== "replay"));
  const validSlug = $derived(/^[a-z0-9][a-z0-9-]*$/.test(newSlug));

  onMount(() => {
    void load();
    const close = (e: MouseEvent): void => {
      if (!(e.target as Element | null)?.closest(".menu")) {
        headMenu = false;
        cardMenu = null;
      }
    };
    addEventListener("click", close);
    return () => removeEventListener("click", close);
  });
</script>

<div class="head row">
  <h1>{t("studio.title")}</h1>
  <span class="spacer"></span>
  <div class="menu">
    <button aria-haspopup="menu" aria-expanded={headMenu} onclick={() => (headMenu = !headMenu)}>{t("studio.more")} ▾</button>
    {#if headMenu}
      <div class="menu-list" role="menu">
        <button role="menuitem" onclick={() => { headMenu = false; fileInput.click(); }}>{t("studio.import")}</button>
        <button role="menuitem" disabled={!scenes.length} onclick={() => exportScenes(selected.size ? [...selected] : null)}>
          {selected.size ? t("studio.export_selected", { n: selected.size }) : t("studio.export_all")}
        </button>
        <button role="menuitem" onclick={() => { headMenu = false; router.go("/studio/layout/new"); }}>{t("studio.new_layout")}</button>
      </div>
    {/if}
  </div>
  <input bind:this={fileInput} type="file" accept=".json,application/json" hidden onchange={pickFile} />
  <button class="primary" onclick={openCreate}>+ {t("studio.new_scene")}</button>
</div>
<p class="hint">{t("studio.hint")}</p>

{#if loading}
  <p class="muted">{t("common.loading")}</p>
{:else}
  {#if scenes.length === 0}
    <div class="panel empty">
      <p>{t("studio.no_scenes")}</p>
      <button class="primary" onclick={openCreate}>+ {t("studio.new_scene")}</button>
    </div>
  {/if}
  <div class="gallery">
    {#each scenes as s (s.id)}
      <article class="card panel" class:sel={selected.has(s.id)}>
        <a class="thumb-link" href="#/studio/scene/{s.id}" aria-label={s.name}>
          <Thumb slug={s.slug} title={s.name} />
        </a>
        <div class="row meta">
          <label class="check" title={t("studio.select_export")}><input type="checkbox" checked={selected.has(s.id)} onchange={() => toggle(s.id)} /></label>
          <div class="grow">
            <strong>{s.name}</strong>
            <div class="muted small ellipsis">{layoutTitle(s.layout)}</div>
          </div>
          <span class="badge {isCustom(s.layout) ? 'accent' : ''}" title={isCustom(s.layout) ? t("studio.badge_custom_hint") : t("studio.badge_fixed_hint")}>
            {isCustom(s.layout) ? t("studio.badge_custom") : t("studio.badge_fixed")}
          </span>
          {#if s.flow === "quali"}<span class="badge ok">{t("studio.quali_badge")}</span>{/if}
        </div>
        <div class="row url">
          <code class="mono">/o/{s.slug}</code>
          <button class="small" title={t("studio.obs_hint")} onclick={() => copyUrl(s)}>{t("studio.copy_url")}</button>
        </div>
        <div class="row actions">
          <a class="button primary" href="#/studio/scene/{s.id}">{t("studio.open_editor")}</a>
          <span class="spacer"></span>
          <div class="menu">
            <button aria-haspopup="menu" aria-expanded={cardMenu === s.id} aria-label={t("studio.more")} onclick={() => (cardMenu = cardMenu === s.id ? null : s.id)}>⋯</button>
            {#if cardMenu === s.id}
              <div class="menu-list" role="menu">
                <button role="menuitem" onclick={() => duplicate(s)}>{t("studio.duplicate")}</button>
                <button role="menuitem" onclick={() => exportScenes([s.id])}>{t("studio.export")}</button>
                <a role="menuitem" href="/o/{s.slug}" target="_blank" rel="noopener">{t("studio.open_overlay")} ↗</a>
                <button role="menuitem" class="danger-text" onclick={() => remove(s)}>{t("common.delete")}</button>
              </div>
            {/if}
          </div>
        </div>
      </article>
    {/each}
  </div>

  <section class="own">
    <button class="link toggle" aria-expanded={showLayouts} onclick={() => (showLayouts = !showLayouts)}>
      {showLayouts ? "▾" : "▸"} {t("studio.loose_layouts")} ({loose.length})
    </button>
    {#if showLayouts}
      <p class="muted small">{t("studio.loose_hint")}</p>
      <div class="gallery small-cards">
        {#each loose as l (l.id)}
          <article class="card panel">
            <div class="row meta">
              <div class="grow">
                <strong>{l.name}</strong>
                <div class="muted small">{t("studio.slots", { n: l.slots ?? "?" })}{l.pairs.length ? ` · ${t("studio.pairs", { n: l.pairs.length })}` : ""}</div>
              </div>
              {#if !l.valid}<span class="badge bad">{t("studio.invalid")}</span>{/if}
            </div>
            <div class="row actions">
              <a class="button primary" href="#/studio/layout/{l.id}">{t("common.edit")}</a>
              <button onclick={() => duplicateLayout(l)}>{t("studio.duplicate")}</button>
              <span class="spacer"></span>
              <button class="danger" onclick={() => removeLayout(l)}>{t("common.delete")}</button>
            </div>
          </article>
        {:else}
          <p class="muted small">{t("studio.no_layouts")}</p>
        {/each}
      </div>
    {/if}
  </section>
{/if}

{#if creating}
  <Modal title={t("studio.new_scene")} onclose={() => (creating = false)} wide>
    <div class="form-grid">
      <label class="field">
        {t("common.name")}
        <input bind:value={newName} maxlength="128" oninput={() => { if (!slugTouched) newSlug = slugify(newName); }} />
      </label>
      <label class="field">
        {t("studio.url_name")}
        <input bind:value={newSlug} maxlength="64" pattern="[a-z0-9][a-z0-9\-]*" oninput={() => (slugTouched = true)} />
        <span class="muted small">/o/{newSlug || "…"}</span>
      </label>
    </div>
    <p class="muted small">{t("studio.pick_template")}</p>
    <TemplatePicker {templates} builtins={fixed} selected={choice} onpick={pick} />
    {#snippet footer()}
      <button onclick={() => (creating = false)}>{t("common.cancel")}</button>
      <button class="primary" disabled={!newName.trim() || !validSlug || !choice} onclick={create}>{t("studio.create")}</button>
    {/snippet}
  </Modal>
{/if}

{#if importReport}
  <Modal title={t("studio.import_title")} onclose={() => (importReport = null)} wide>
    {#if !importReport.ok}<p class="error-box">{t("studio.import_errors")}</p>{/if}
    {#if importReport.layouts.length}
      <h3>{t("studio.tab_layouts")}</h3>
      <table>
        <tbody>
          {#each importReport.layouts as l (l.id)}
            <tr>
              <td><strong>{l.name}</strong></td>
              <td><span class="badge {l.status === 'conflict' ? 'warn' : l.status === 'new' ? 'ok' : ''}">{t(`studio.status_${l.status}`)}</span>
                {#if l.existing_name}<span class="muted small"> ({l.existing_name})</span>{/if}</td>
              <td>
                {#if l.errors.length}
                  <span class="bad-text small">{l.errors.join("; ")}</span>
                {:else}
                  <select bind:value={layoutDecisions[l.id!]}>
                    {#each layoutOptions[l.status] ?? [] as o (o)}<option value={o}>{tDynamic(`studio.decision_${o}`, o)}</option>{/each}
                  </select>
                {/if}
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    {/if}
    <h3>{t("studio.tab_scenes")}</h3>
    <table>
      <tbody>
        {#each importReport.scenes as s (s.slug)}
          <tr>
            <td><strong>{s.name}</strong><div class="muted small">/o/{s.slug} · {layoutTitle(s.layout ?? "")}</div></td>
            <td><span class="badge {s.status === 'conflict' ? 'warn' : 'ok'}">{t(`studio.status_${s.status}`)}</span></td>
            <td>
              {#if s.errors.length}
                <span class="bad-text small">{s.errors.join("; ")}</span>
              {:else}
                <select bind:value={sceneDecisions[s.slug!]}>
                  {#each sceneOptions[s.status] ?? [] as o (o)}
                    <option value={o}>{o === "rename" ? t("studio.decision_rename", { slug: s.suggested_slug ?? "" }) : tDynamic(`studio.decision_${o}`, o)}</option>
                  {/each}
                </select>
              {/if}
            </td>
          </tr>
        {/each}
      </tbody>
    </table>
    <p class="muted small">{t("studio.import_note")}</p>
    {#snippet footer()}
      <button onclick={() => (importReport = null)}>{t("common.cancel")}</button>
      <button class="primary" disabled={!importReport?.ok || importing} onclick={runImport}>{t("studio.import_run")}</button>
    {/snippet}
  </Modal>
{/if}

<style>
  .head {
    gap: 10px;
    margin-bottom: 4px;
  }
  .head h1 {
    margin: 0;
  }
  .empty {
    display: grid;
    gap: 10px;
    justify-items: start;
    margin-bottom: 14px;
  }
  .gallery {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
    gap: 14px;
  }
  .small-cards {
    grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  }
  .card {
    display: grid;
    gap: 8px;
    align-content: start;
  }
  .card.sel {
    border-color: var(--accent);
  }
  .thumb-link {
    display: block;
  }
  .meta {
    gap: 10px;
    align-items: center;
  }
  .grow {
    flex: 1;
    min-width: 0;
  }
  .ellipsis {
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .url {
    gap: 8px;
    align-items: center;
  }
  .url code {
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .small {
    padding: 2px 8px;
    font-size: 13px;
  }
  .actions {
    gap: 6px;
    flex-wrap: wrap;
  }
  .menu {
    position: relative;
  }
  .menu-list {
    position: absolute;
    right: 0;
    top: calc(100% + 4px);
    z-index: 20;
    display: grid;
    min-width: 220px;
    padding: 4px;
    background: var(--panel);
    border: 1px solid var(--line);
    border-radius: 8px;
    box-shadow: 0 8px 24px rgb(0 0 0 / 0.4);
  }
  .menu-list button,
  .menu-list a {
    text-align: left;
    border: 0;
    background: none;
    padding: 8px 10px;
    color: inherit;
    border-radius: 6px;
  }
  .menu-list button:hover,
  .menu-list a:hover {
    background: var(--panel-2);
  }
  .danger-text {
    color: var(--bad, #f83800) !important;
  }
  .own {
    margin-top: 28px;
    display: grid;
    gap: 8px;
  }
  .toggle {
    justify-self: start;
    font-size: 15px;
  }
  table {
    width: 100%;
    border-collapse: collapse;
    margin-bottom: 12px;
  }
  td {
    padding: 6px 8px;
    border-bottom: 1px solid var(--line);
    vertical-align: top;
  }
  .bad-text {
    color: var(--bad);
  }
</style>
