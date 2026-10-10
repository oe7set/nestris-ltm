<script lang="ts">
  // Scene studio: gallery of scenes and own layouts with live thumbnails,
  // new scene from a layout gallery, duplicate, export and import.
  import { onMount } from "svelte";
  import Modal from "../components/Modal.svelte";
  import Thumb from "../components/Thumb.svelte";
  import { confirmAsync } from "../lib/confirm.svelte";
  import { api, ApiError } from "../lib/api";
  import { i18n, t, tDynamic } from "../lib/i18n.svelte";
  import { router } from "../lib/router.svelte";
  import {
    defaultSettings,
    downloadExport,
    previewOf,
    readImportFile,
    slugify,
    type CustomLayout,
    type LayoutInfo,
    type SceneRow,
  } from "../lib/studio";
  import { toasts } from "../lib/toast.svelte";

  type Tab = "scenes" | "layouts";
  let tab = $state<Tab>((router.current.query.get("tab") as Tab) ?? "scenes");
  let scenes = $state<SceneRow[]>([]);
  let layouts = $state<LayoutInfo[]>([]);
  let customs = $state<CustomLayout[]>([]);
  let selected = $state<Set<number>>(new Set());
  let loading = $state(true);

  // New scene dialog
  let creating = $state(false);
  let newName = $state("");
  let newSlug = $state("");
  let slugTouched = $state(false);
  let newLayout = $state("1v1_cam");

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
      [scenes, layouts, customs] = await Promise.all([
        api<SceneRow[]>("/api/scenes"),
        api<LayoutInfo[]>("/api/scenes/layouts"),
        api<CustomLayout[]>("/api/overlay-layouts"),
      ]);
    } catch (e) {
      toasts.error(e);
    } finally {
      loading = false;
    }
  }

  function layoutTitle(id: string): string {
    const l = layouts.find((x) => x.id === id);
    if (!l) return id;
    return i18n.locale === "en" ? l.title_en : l.title_de;
  }

  function setTab(next: Tab): void {
    tab = next;
    router.setQuery({ tab: next === "scenes" ? null : next });
  }

  // ---- scenes

  function openCreate(layoutId = "1v1_cam"): void {
    newName = "";
    newSlug = "";
    slugTouched = false;
    newLayout = layoutId;
    creating = true;
  }

  async function create(): Promise<void> {
    try {
      const scene = await api<SceneRow>("/api/scenes", {
        method: "POST",
        body: { name: newName.trim(), slug: newSlug.trim(), layout: newLayout, settings: { style: "nes" } },
      });
      creating = false;
      router.go(`/studio/scene/${scene.id}`);
    } catch (e) {
      toasts.error(e);
    }
  }

  async function duplicate(scene: SceneRow): Promise<void> {
    try {
      const copy = await api<SceneRow>(`/api/scenes/${scene.id}/duplicate`, { method: "POST", body: {} });
      toasts.ok(t("studio.duplicated", { name: copy.name }));
      await load();
    } catch (e) {
      toasts.error(e);
    }
  }

  async function remove(scene: SceneRow): Promise<void> {
    if (!(await confirmAsync({ title: t("studio.confirm_delete_scene", { name: scene.name }), danger: true, confirmLabel: t("common.delete") }))) return;
    try {
      await api(`/api/scenes/${scene.id}`, { method: "DELETE" });
      selected.delete(scene.id);
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
    try {
      await downloadExport(ids ? { scenes: ids.join(",") } : {});
    } catch (e) {
      toasts.error(e);
    }
  }

  // ---- layouts

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
      toasts.ok(
        t("studio.imported", { scenes: result.imported.scenes.length, layouts: result.imported.layouts.length }),
      );
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

  const builtins = $derived(layouts.filter((l) => !l.custom && l.id !== "replay"));
  const creatable = $derived(layouts.filter((l) => l.id !== "replay"));
  const newLayoutInfo = $derived(layouts.find((l) => l.id === newLayout));

  onMount(() => {
    void load();
  });
</script>

<div class="head row">
  <h1>{t("studio.title")}</h1>
  <span class="spacer"></span>
  <button onclick={() => fileInput.click()}>{t("studio.import")}</button>
  <input bind:this={fileInput} type="file" accept=".json,application/json" hidden onchange={pickFile} />
  {#if tab === "scenes"}
    <button disabled={!scenes.length} onclick={() => exportScenes(selected.size ? [...selected] : null)}>
      {selected.size ? t("studio.export_selected", { n: selected.size }) : t("studio.export_all")}
    </button>
    <button class="primary" onclick={() => openCreate()}>+ {t("studio.new_scene")}</button>
  {:else}
    <button class="primary" onclick={() => router.go("/studio/layout/new")}>+ {t("studio.new_layout")}</button>
  {/if}
</div>
<p class="hint">{t("studio.hint")}</p>

<div class="tabs">
  <button class:on={tab === "scenes"} onclick={() => setTab("scenes")}>{t("studio.tab_scenes")} ({scenes.length})</button>
  <button class:on={tab === "layouts"} onclick={() => setTab("layouts")}>{t("studio.tab_layouts")} ({customs.length})</button>
</div>

{#if loading}
  <p class="muted">…</p>
{:else if tab === "scenes"}
  {#if scenes.length === 0}
    <p class="muted">{t("studio.no_scenes")}</p>
  {/if}
  <div class="gallery">
    {#each scenes as s (s.id)}
      <article class="card panel" class:sel={selected.has(s.id)}>
        <a class="thumb-link" href="#/studio/scene/{s.id}" aria-label={s.name}>
          <Thumb slug={s.slug} title={s.name} />
        </a>
        <div class="row meta">
          <label class="check"><input type="checkbox" checked={selected.has(s.id)} onchange={() => toggle(s.id)} /></label>
          <div class="grow">
            <strong>{s.name}</strong>
            <div class="muted small">/o/{s.slug} · {layoutTitle(s.layout)}</div>
          </div>
          <span class="badge {s.settings.style === 'nes' ? 'accent' : ''}">{s.settings.style === "nes" ? "NES" : "Modern"}</span>
          {#if s.flow === "quali"}<span class="badge ok">{t("studio.quali_badge")}</span>{/if}
        </div>
        <div class="row actions">
          <a class="button primary" href="#/studio/scene/{s.id}">{t("common.edit")}</a>
          <button onclick={() => duplicate(s)}>{t("studio.duplicate")}</button>
          <button onclick={() => exportScenes([s.id])}>{t("studio.export")}</button>
          <span class="spacer"></span>
          <button class="danger" onclick={() => remove(s)}>{t("common.delete")}</button>
        </div>
      </article>
    {/each}
  </div>
{:else}
  {#if customs.length === 0}
    <p class="muted">{t("studio.no_layouts")}</p>
  {/if}
  <div class="gallery">
    {#each customs as l (l.id)}
      <article class="card panel">
        <a class="thumb-link" href="#/studio/layout/{l.id}" aria-label={l.name}>
          <Thumb
            config={previewOf(
              { slug: "preview", name: l.name, layout: l.key, mode: "none", settings: defaultSettings() },
              { slots: l.slots ?? 1, pairs: l.pairs },
            )}
            title={l.name}
          />
        </a>
        <div class="row meta">
          <div class="grow">
            <strong>{l.name}</strong>
            <div class="muted small">
              {t("studio.slots", { n: l.slots ?? "?" })}{l.pairs.length ? ` · ${t("studio.pairs", { n: l.pairs.length })}` : ""}
              {#if l.used_by?.length} · {t("studio.used_by", { scenes: l.used_by.join(", ") })}{/if}
            </div>
          </div>
          {#if !l.valid}<span class="badge bad">{t("studio.invalid")}</span>{/if}
        </div>
        <div class="row actions">
          <a class="button primary" href="#/studio/layout/{l.id}">{t("common.edit")}</a>
          <button onclick={() => duplicateLayout(l)}>{t("studio.duplicate")}</button>
          <button onclick={() => downloadExport({ layouts: l.id }).catch((e) => toasts.error(e))}>{t("studio.export")}</button>
          <span class="spacer"></span>
          <button class="danger" disabled={!!l.used_by?.length} title={l.used_by?.length ? t("studio.in_use") : ""} onclick={() => removeLayout(l)}>
            {t("common.delete")}
          </button>
        </div>
      </article>
    {/each}
  </div>
  {#if builtins.length}
    <h2 class="sub">{t("studio.builtin_layouts")}</h2>
    <div class="gallery small-cards">
      {#each builtins as l (l.id)}
        <article class="card panel">
          <Thumb config={previewOf({ slug: "preview", name: l.title_de, layout: l.id, mode: "none", settings: defaultSettings() }, l)} />
          <div class="meta"><strong>{i18n.locale === "en" ? l.title_en : l.title_de}</strong></div>
          <button onclick={() => openCreate(l.id)}>{t("studio.use_layout")}</button>
        </article>
      {/each}
    </div>
  {/if}
{/if}

{#if creating}
  <Modal title={t("studio.new_scene")} onclose={() => (creating = false)} wide>
    <div class="form-grid">
      <label class="field">
        {t("common.name")}
        <input bind:value={newName} maxlength="128" oninput={() => { if (!slugTouched) newSlug = slugify(newName); }} />
      </label>
      <label class="field">
        {t("scenes.slug")}
        <input bind:value={newSlug} maxlength="64" pattern="[a-z0-9][a-z0-9\-]*" oninput={() => (slugTouched = true)} />
      </label>
    </div>
    <p class="muted small">{t("studio.pick_layout")}</p>
    <div class="layout-pick">
      {#each creatable as l (l.id)}
        <button class="pick" class:on={newLayout === l.id} onclick={() => (newLayout = l.id)}>
          <Thumb config={previewOf({ slug: "preview", name: newName || l.title_de, layout: l.id, mode: "none", settings: defaultSettings() }, l)} />
          <span>{i18n.locale === "en" ? l.title_en : l.title_de}{l.custom ? " ★" : ""}</span>
        </button>
      {/each}
    </div>
    {#if newLayoutInfo}<p class="hint">{i18n.locale === "en" ? newLayoutInfo.description_en : newLayoutInfo.description_de}</p>{/if}
    {#snippet footer()}
      <button onclick={() => (creating = false)}>{t("common.cancel")}</button>
      <button class="primary" disabled={!newName.trim() || !/^[a-z0-9][a-z0-9-]*$/.test(newSlug)} onclick={create}>{t("studio.create")}</button>
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
  .tabs {
    display: flex;
    gap: 8px;
    margin: 10px 0 14px;
  }
  .tabs button.on {
    border-color: var(--accent);
    color: var(--accent);
  }
  .gallery {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
    gap: 14px;
  }
  .small-cards {
    grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  }
  .card {
    display: grid;
    gap: 10px;
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
  .actions {
    gap: 6px;
    flex-wrap: wrap;
  }
  .sub {
    margin-top: 28px;
  }
  .layout-pick {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
    gap: 10px;
    max-height: 56vh;
    overflow: auto;
    padding: 2px;
  }
  .pick {
    display: grid;
    gap: 6px;
    padding: 6px;
    text-align: left;
    background: var(--panel-2);
  }
  .pick.on {
    border-color: var(--accent);
    box-shadow: 0 0 0 2px var(--accent);
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
