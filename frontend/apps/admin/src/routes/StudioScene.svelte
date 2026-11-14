<script lang="ts">
  // Scene studio, one page per scene, laid out like OBS: the 1920x1080 stage
  // in the middle (zoomed to fit), elements and layers on the left, the
  // selected element, the scene's look and its stations on the right.
  //
  // A scene with a fixed built-in layout shows it as it is; "Adapt layout"
  // gives the scene its own copy made from the matching template, which can
  // then be changed freely. One "Save" stores the layout and the scene.
  import { onMount } from "svelte";
  import Modal from "../components/Modal.svelte";
  import LayersPanel from "../components/studio/LayersPanel.svelte";
  import PropertiesPanel from "../components/studio/PropertiesPanel.svelte";
  import ScenePanel from "../components/studio/ScenePanel.svelte";
  import SlotsPanel from "../components/studio/SlotsPanel.svelte";
  import Stage from "../components/studio/Stage.svelte";
  import StationsPanel from "../components/studio/StationsPanel.svelte";
  import TemplatePicker from "../components/studio/TemplatePicker.svelte";
  import GuideTools from "../components/GuideTools.svelte";
  import Tabs from "../components/Tabs.svelte";
  import { api, ApiError } from "../lib/api";
  import { confirmAsync } from "../lib/confirm.svelte";
  import { emptyDefinition } from "../lib/editor/elements";
  import { LayoutEditor } from "../lib/editor/layoutEditor.svelte";
  import { fillHeight } from "../lib/fillHeight";
  import { i18n, t, tDynamic } from "../lib/i18n.svelte";
  import { router } from "../lib/router.svelte";
  import {
    cleanSettings,
    defaultSettings,
    downloadExport,
    previewOf,
    type CustomLayout,
    type LayoutChoice,
    type LayoutDefinition,
    type LayoutInfo,
    type SceneRow,
    type SceneSettings,
    type SlotRow,
    type Template,
  } from "../lib/studio";
  import { toasts } from "../lib/toast.svelte";
  import type { StationRow } from "../lib/types";
  import { uiPrefs } from "../lib/uiPrefs.svelte";

  let { id }: { id: string } = $props();

  interface ServerError {
    element: number | null;
    field: string;
    message: string;
  }

  // ---- loaded
  let scene = $state<SceneRow | null>(null);
  let layouts = $state<LayoutInfo[]>([]);
  let customs = $state<CustomLayout[]>([]);
  let stations = $state<StationRow[]>([]);
  let templates = $state.raw<Template[]>([]);
  let notFound = $state(false);
  let busy = $state(false);

  // ---- the edited scene (saved = what the server has)
  let name = $state("");
  let layoutKey = $state("1v1");
  let mode = $state("none");
  let settings = $state<SceneSettings>(defaultSettings());
  let slots = $state<SlotRow[]>([]);
  let savedScene = $state("");

  // ---- its own layout (null: a fixed built-in layout)
  const editor = new LayoutEditor();
  let own = $state<CustomLayout | null>(null);
  let savedDef = $state("");
  /** A template picked in "change layout", created on save. */
  let pending = $state.raw<Template | null>(null);
  let serverErrors = $state<ServerError[]>([]);

  // ---- view
  let leftTab = $state<"layers" | "slots">("layers");
  let rightTab = $state<"props" | "scene" | "stations">("scene");
  let source = $state<"demo" | "live">("demo");
  let background = $state<"dark" | "checker">("checker");
  let showGrid = $state(false);
  let zoom = $state<"fit" | number>("fit");
  let picking = $state(false);
  let menuOpen = $state(false);

  function sceneSnapshot(): string {
    return JSON.stringify({ name, layoutKey, mode, settings: cleanSettings(settings), slots });
  }
  const sceneDirty = $derived(scene !== null && sceneSnapshot() !== savedScene);
  const layoutDirty = $derived(editor.editable && (pending !== null || JSON.stringify(editor.def) !== savedDef));
  const dirty = $derived(sceneDirty || layoutDirty);
  const builtin = $derived(!own && !pending);
  const info = $derived(layouts.find((l) => l.id === layoutKey));
  const sharedWith = $derived((own?.used_by ?? []).filter((slug) => slug !== scene?.slug));
  const canAdapt = $derived(builtin && templates.some((tpl) => tpl.builtin === layoutKey));
  const layoutTitle = $derived(
    pending
      ? (i18n.locale === "en" ? pending.name_en : pending.name_de)
      : own
        ? ownTitle(own)
        : info
          ? (i18n.locale === "en" ? info.title_en : info.title_de)
          : layoutKey,
  );

  function ownTitle(row: CustomLayout): string {
    const tpl = templates.find((x) => x.id === row.template_id);
    if (!tpl) return row.name;
    return t("studio.adapted_from", { name: i18n.locale === "en" ? tpl.name_en : tpl.name_de });
  }

  function slotsFor(count: number, existing: SlotRow[]): SlotRow[] {
    return Array.from(
      { length: count },
      (_, i) => existing.find((s) => s.slot === i) ?? { slot: i, station_id: null, label_override: null, name_override: null },
    );
  }

  function adoptScene(s: SceneRow): void {
    scene = s;
    name = s.name;
    layoutKey = s.layout;
    mode = s.mode;
    settings = { ...defaultSettings(), ...s.settings, theme: { ...s.settings.theme }, show: { ...defaultSettings().show, ...s.settings.show } };
    slots = slotsFor(slotCount(), s.slots);
    savedScene = sceneSnapshot();
  }

  function adoptLayout(row: CustomLayout | null): void {
    own = row;
    pending = null;
    serverErrors = [];
    editor.errorIds = [];
    editor.editable = row !== null;
    editor.load(row?.definition ?? emptyDefinition());
    savedDef = JSON.stringify(editor.def);
    if (row) {
      layoutKey = row.key;
      slots = slotsFor(row.definition?.slots ?? slots.length, slots);
    }
  }

  function slotCount(): number {
    if (editor.editable) return editor.def.slots;
    return layouts.find((l) => l.id === layoutKey)?.slots ?? scene?.slots.length ?? 2;
  }

  async function loadOwn(key: string): Promise<CustomLayout | null> {
    const lid = key.startsWith("custom:") ? key.slice(7) : null;
    if (!lid) return null;
    const [row, list] = await Promise.all([
      api<CustomLayout>(`/api/overlay-layouts/${encodeURIComponent(lid)}`),
      api<CustomLayout[]>("/api/overlay-layouts"),
    ]);
    customs = list;
    return { ...row, used_by: list.find((l) => l.id === row.id)?.used_by ?? [] };
  }

  async function load(): Promise<void> {
    try {
      const [all, ls, cs, st, tpls] = await Promise.all([
        api<SceneRow[]>("/api/scenes"),
        api<LayoutInfo[]>("/api/scenes/layouts"),
        api<CustomLayout[]>("/api/overlay-layouts"),
        api<StationRow[]>("/api/stations"),
        api<Template[]>("/api/studio/templates"),
      ]);
      layouts = ls;
      customs = cs;
      stations = st;
      templates = tpls;
      const found = all.find((s) => String(s.id) === id);
      if (!found) {
        notFound = true;
        return;
      }
      const row = await loadOwn(found.layout);
      adoptLayout(row);
      adoptScene(found);
      rightTab = row ? "props" : "scene";
      readDraft();
    } catch (e) {
      toasts.error(e);
    }
  }

  // ---- adapt / copy / reset / change layout

  async function adapt(copy = false): Promise<void> {
    if (!scene || busy) return;
    busy = true;
    try {
      const r = await api<{ scene: { layout: string; updated_at: string }; layout: CustomLayout }>(
        `/api/scenes/${scene.id}/edit-layout`,
        { method: "POST", body: { copy } },
      );
      // The server switched the scene's layout: take that over as saved.
      const wasDirty = sceneDirty;
      scene = { ...scene, layout: r.scene.layout, updated_at: r.scene.updated_at };
      const row = await loadOwn(r.scene.layout);
      adoptLayout(row);
      if (!wasDirty) savedScene = sceneSnapshot();
      else savedScene = JSON.stringify({ ...JSON.parse(savedScene), layoutKey: r.scene.layout });
      leftTab = "layers";
      rightTab = "props";
      toasts.ok(copy ? t("studio.copied_layout") : t("studio.adapted"));
    } catch (e) {
      toasts.error(e);
    } finally {
      busy = false;
    }
  }

  async function resetToTemplate(): Promise<void> {
    if (!own?.template_id) return;
    if (!(await confirmAsync({ title: t("studio.reset_confirm"), danger: true, confirmLabel: t("studio.reset") }))) return;
    try {
      const row = await api<CustomLayout>(`/api/overlay-layouts/${own.id}/reset`, {
        method: "POST",
        body: { expected_version: own.version },
      });
      adoptLayout({ ...row, used_by: own.used_by });
      toasts.ok(t("studio.reset_done"));
    } catch (e) {
      if (e instanceof ApiError && e.code === "stale") toasts.error(t("builder.stale"));
      else toasts.error(e);
    }
  }

  async function chooseLayout(choice: LayoutChoice): Promise<void> {
    picking = false;
    if (choice.kind === "template") {
      // Created on save; until then the stage shows the template, editable.
      own = null;
      pending = choice.template;
      editor.editable = true;
      editor.load(structuredClone(choice.template.definition));
      savedDef = "";
      slots = slotsFor(editor.def.slots, slots);
      leftTab = "layers";
      return;
    }
    if (choice.key === layoutKey && !pending) return;
    try {
      pending = null;
      const row = await loadOwn(choice.key);
      layoutKey = choice.key;
      adoptLayout(row);
      if (!row) slots = slotsFor(slotCount(), slots);
      if (!row && !layouts.find((l) => l.id === choice.key)?.supports_modes) mode = "none";
    } catch (e) {
      toasts.error(e);
    }
  }

  // ---- save

  function markErrors(errors: ServerError[], submitted: LayoutDefinition): void {
    serverErrors = errors;
    editor.errorIds = errors
      .map((err) => (err.element !== null ? submitted.elements[err.element]?.id : undefined))
      .filter((x): x is string => !!x);
  }

  async function save(): Promise<void> {
    if (!scene || busy || !dirty) return;
    if (!name.trim()) {
      toasts.push("error", t("builder.name_required"));
      return;
    }
    busy = true;
    const submitted = editor.def;
    try {
      // 1. The layout (a new one from a template, or the scene's own).
      if (pending) {
        const row = await api<CustomLayout>("/api/overlay-layouts", {
          method: "POST",
          body: { name: name.trim().slice(0, 64), description: pending.description_de, definition: submitted, template_id: pending.id },
        });
        layoutKey = row.key;
        adoptLayout({ ...row, used_by: [] });
      } else if (own && layoutDirty) {
        const row = await api<CustomLayout>(`/api/overlay-layouts/${own.id}`, {
          method: "PUT",
          body: { expected_version: own.version, definition: submitted },
        });
        adoptLayout({ ...row, used_by: own.used_by });
      }
      serverErrors = [];
      editor.errorIds = [];
      // 2. The scene (name, layout, look, stations).
      if (sceneSnapshot() !== savedScene) {
        const updated = await api<SceneRow>(`/api/scenes/${scene.id}`, {
          method: "PATCH",
          body: {
            name: name.trim(),
            layout: layoutKey,
            mode,
            settings: cleanSettings(settings),
            slots: slots.map((s) => ({
              slot: s.slot,
              station_id: s.station_id || null,
              label_override: s.label_override?.trim() || null,
              name_override: s.name_override?.trim() || null,
            })),
            expected_updated_at: scene.updated_at,
          },
        });
        adoptScene({ ...scene, ...updated });
        if (own) own = { ...own, used_by: [...new Set([...(own.used_by ?? []), scene.slug])] };
      }
      dropDraft();
      toasts.ok(t("studio.saved"));
    } catch (e) {
      if (e instanceof ApiError && e.code === "invalid") {
        const detail = (e.body as { detail?: { errors?: ServerError[] } } | null)?.detail;
        markErrors(detail?.errors ?? [], submitted);
        toasts.push("error", t("builder.invalid", { n: serverErrors.length }));
      } else if (e instanceof ApiError && (e.code === "stale" || e.status === 409)) {
        toasts.error(t("studio.stale"));
      } else {
        toasts.error(e);
      }
    } finally {
      busy = false;
    }
  }

  async function revert(): Promise<void> {
    if (!scene || !(await confirmAsync({ title: t("studio.revert_confirm"), danger: true, confirmLabel: t("studio.revert") }))) return;
    try {
      const row = await loadOwn(scene.layout);
      adoptLayout(row);
      adoptScene(scene);
      dropDraft();
    } catch (e) {
      toasts.error(e);
    }
  }

  async function duplicate(): Promise<void> {
    menuOpen = false;
    if (!scene) return;
    try {
      const copy = await api<SceneRow>(`/api/scenes/${scene.id}/duplicate`, { method: "POST", body: {} });
      router.go(`/studio/scene/${copy.id}`);
    } catch (e) {
      toasts.error(e);
    }
  }

  async function remove(): Promise<void> {
    menuOpen = false;
    if (!scene) return;
    if (!(await confirmAsync({ title: t("studio.confirm_delete_scene", { name: scene.name }), danger: true, confirmLabel: t("common.delete") }))) return;
    try {
      await api(`/api/scenes/${scene.id}`, { method: "DELETE" });
      // Its own layout goes too when no other scene uses it.
      if (own && !sharedWith.length) await api(`/api/overlay-layouts/${own.id}`, { method: "DELETE" }).catch(() => {});
      savedScene = sceneSnapshot();
      savedDef = JSON.stringify(editor.def);
      pending = null;
      dropDraft();
      router.go("/studio");
    } catch (e) {
      toasts.error(e);
    }
  }

  // ---- draft (a crash or a closed tab loses nothing)

  interface Draft {
    name: string;
    settings: SceneSettings;
    slots: SlotRow[];
    def: LayoutDefinition | null;
    version: number | null;
    at: string;
  }
  let draft = $state.raw<Draft | null>(null);
  const draftKey = $derived(`nltm.scene-draft.${id}`);

  function readDraft(): void {
    try {
      const raw = localStorage.getItem(draftKey);
      if (!raw) return;
      const d = JSON.parse(raw) as Draft;
      if ((d.version ?? null) === (own?.version ?? null)) draft = d;
      else localStorage.removeItem(draftKey);
    } catch {
      // A broken draft is only a lost convenience.
    }
  }

  function restoreDraft(): void {
    if (!draft) return;
    name = draft.name;
    settings = draft.settings;
    slots = draft.slots;
    if (draft.def && editor.editable) editor.apply(draft.def);
    draft = null;
  }

  function dropDraft(): void {
    draft = null;
    try {
      localStorage.removeItem(draftKey);
    } catch {
      // ignore
    }
  }

  $effect(() => {
    const key = draftKey;
    if (!dirty || pending) return;
    const data: Draft = {
      name,
      settings: $state.snapshot(settings) as SceneSettings,
      slots: $state.snapshot(slots) as SlotRow[],
      def: editor.editable ? editor.def : null,
      version: own?.version ?? null,
      at: new Date().toISOString(),
    };
    const timer = setTimeout(() => {
      try {
        localStorage.setItem(key, JSON.stringify(data));
      } catch {
        // storage full or blocked: no draft
      }
    }, 600);
    return () => clearTimeout(timer);
  });

  // ---- preview

  const preview = $derived(
    scene
      ? previewOf(
          { slug: scene.slug, name, layout: editor.editable ? "custom:edit" : layoutKey, mode, settings },
          editor.editable ? { slots: editor.def.slots, pairs: editor.def.pairs } : info,
          {
            names: slots.map((s) => s.name_override?.trim() || null),
            definition: editor.editable ? editor.def : null,
            liveSlug: source === "live" ? scene.slug : null,
          },
        )
      : null,
  );

  // The selected element is edited on the right.
  $effect(() => {
    if (editor.selected.length) rightTab = "props";
  });

  function onKey(event: KeyboardEvent): void {
    if (!scene) return;
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s") {
      event.preventDefault();
      void save();
      return;
    }
    editor.handleKey(event);
  }

  onMount(() => {
    void load();
    const beforeUnload = (e: BeforeUnloadEvent): void => {
      if (dirty) e.preventDefault();
    };
    const unguard = router.setGuard(async () => !dirty || (await confirmAsync({ title: t("studio.unsaved_confirm"), danger: true, confirmLabel: t("common.discard") })));
    addEventListener("beforeunload", beforeUnload);
    addEventListener("keydown", onKey);
    return () => {
      removeEventListener("beforeunload", beforeUnload);
      removeEventListener("keydown", onKey);
      unguard();
    };
  });
</script>

{#if notFound}
  <p class="muted">{t("common.not_found")} · <a href="#/studio">{t("studio.title")}</a></p>
{:else if scene}
  <div class="studio fill-page" use:fillHeight>
    <!-- toolbar -->
    <div class="bar">
      <a href="#/studio" class="back" title={t("studio.title")}>← {t("studio.title")}</a>
      <h1 title={name}>{name || scene.name}</h1>
      {#if dirty}<span class="badge warn">{t("studio.unsaved")}</span>{/if}
      <span class="sep"></span>
      <button class="icon" title="{t('builder.undo')} (Ctrl+Z)" aria-label={t("builder.undo")} disabled={!editor.canUndo} onclick={() => editor.undo()}>↶</button>
      <button class="icon" title="{t('builder.redo')} (Ctrl+Y)" aria-label={t("builder.redo")} disabled={!editor.canRedo} onclick={() => editor.redo()}>↷</button>
      <span class="sep"></span>
      <div class="seg" title={t("builder.style_preview")}>
        <button aria-pressed={settings.style === "nes"} class:on={settings.style === "nes"} onclick={() => (settings.style = "nes")}>NES</button>
        <button aria-pressed={settings.style === "modern"} class:on={settings.style === "modern"} onclick={() => (settings.style = "modern")}>Modern</button>
      </div>
      <div class="seg" title={t("studio.source_hint")}>
        <button aria-pressed={source === "demo"} class:on={source === "demo"} onclick={() => (source = "demo")}>{t("studio.demo")}</button>
        <button aria-pressed={source === "live"} class:on={source === "live"} onclick={() => (source = "live")}>{t("studio.live")}</button>
      </div>
      <div class="seg">
        <button aria-pressed={background === "checker"} class:on={background === "checker"} onclick={() => (background = "checker")}>{t("studio.bg_checker")}</button>
        <button aria-pressed={background === "dark"} class:on={background === "dark"} onclick={() => (background = "dark")}>{t("scenes.bg_dark")}</button>
      </div>
      {#if editor.editable}
        <label class="check"><input type="checkbox" bind:checked={showGrid} /> {t("builder.grid")}</label>
      {/if}
      <GuideTools />
      <span class="spacer"></span>
      <button class="icon" title={t("studio.focus_hint")} aria-pressed={uiPrefs.studioFocus} class:on={uiPrefs.studioFocus} onclick={() => uiPrefs.toggle("studioFocus")}>⛶</button>
      <div class="menu">
        <button aria-haspopup="menu" aria-expanded={menuOpen} onclick={() => (menuOpen = !menuOpen)}>⋯</button>
        {#if menuOpen}
          <div class="menu-list" role="menu">
            <button role="menuitem" onclick={() => { menuOpen = false; picking = true; }}>{t("studio.change_layout")}</button>
            {#if own?.template_id}
              <button role="menuitem" onclick={() => { menuOpen = false; void resetToTemplate(); }}>{t("studio.reset_template")}</button>
            {/if}
            <button role="menuitem" onclick={duplicate}>{t("studio.duplicate")}</button>
            <button role="menuitem" onclick={() => { menuOpen = false; if (scene) downloadExport({ scenes: String(scene.id) }).catch((e) => toasts.error(e)); }}>{t("studio.export")}</button>
            <button role="menuitem" class="danger-text" onclick={remove}>{t("common.delete")}</button>
          </div>
        {/if}
      </div>
      <button disabled={!dirty || busy} onclick={revert}>{t("studio.revert")}</button>
      <button class="primary" disabled={!dirty || busy || !name.trim()} title="Ctrl+S" onclick={save}>{t("common.save")}</button>
    </div>

    {#if draft}
      <div class="banner">
        <span>{t("builder.draft_found", { at: new Date(draft.at).toLocaleString(i18n.locale) })}</span>
        <span class="spacer"></span>
        <button class="primary" onclick={restoreDraft}>{t("builder.draft_restore")}</button>
        <button onclick={dropDraft}>{t("builder.draft_discard")}</button>
      </div>
    {/if}
    {#if sharedWith.length}
      <div class="banner">
        <span>{t("studio.shared_layout", { scenes: sharedWith.join(", ") })}</span>
        <span class="spacer"></span>
        <button onclick={() => adapt(true)} disabled={busy || layoutDirty}>{t("studio.copy_for_scene")}</button>
      </div>
    {/if}

    <div class="body">
      <!-- left: layers / slots -->
      <aside class="col">
        {#if editor.editable}
          <Tabs tabs={[{ id: "layers", label: t("builder.layers") }, { id: "slots", label: t("studio.slots_pairs") }]} active={leftTab} onchange={(v) => (leftTab = v)} />
          <div class="scroll">
            {#if leftTab === "layers"}<LayersPanel {editor} />{:else}<SlotsPanel {editor} />{/if}
          </div>
        {:else}
          <section class="panel fixed">
            <h2>{t("studio.fixed_title")}</h2>
            <p><strong>{layoutTitle}</strong></p>
            <p class="muted small">{t("studio.fixed_explain")}</p>
            {#if canAdapt}
              <button class="primary" disabled={busy} onclick={() => adapt(false)}>{t("studio.adapt")}</button>
            {:else}
              <button onclick={() => (picking = true)}>{t("studio.change_layout")}</button>
            {/if}
          </section>
        {/if}
      </aside>

      <!-- centre: the stage -->
      <section class="center">
        <Stage {editor} {preview} live={source === "live"} {background} bind:showGrid bind:zoom>
          {#snippet notice()}
            {#if !editor.editable && canAdapt}
              <div class="notice-box">
                <span>{t("studio.fixed_notice", { name: layoutTitle })}</span>
                <button class="primary" disabled={busy} onclick={() => adapt(false)}>{t("studio.adapt")}</button>
              </div>
            {:else if pending}
              <div class="notice-box"><span>{t("studio.pending_notice", { name: layoutTitle })}</span></div>
            {/if}
          {/snippet}
        </Stage>
        {#if serverErrors.length || editor.problems.size}
          <div class="panel errors">
            <strong>{t("builder.errors")}</strong>
            <ul>
              {#each serverErrors as err, i (i)}<li>{err.message}</li>{/each}
              {#each [...editor.problems] as [eid, what] (eid)}
                <li><button class="link" onclick={() => (editor.selected = [eid])}>{eid}</button>: {tDynamic(`builder.problem_${what}`, what)}</li>
              {/each}
            </ul>
          </div>
        {/if}
      </section>

      <!-- right: element / scene / stations -->
      <aside class="col">
        <Tabs
          tabs={[
            { id: "props", label: t("builder.properties") },
            { id: "scene", label: t("studio.tab_scene") },
            { id: "stations", label: t("studio.stations") },
          ]}
          active={rightTab}
          onchange={(v) => (rightTab = v)}
        />
        <div class="scroll">
          {#if rightTab === "props"}
            <PropertiesPanel {editor} />
          {:else if rightTab === "scene"}
            <ScenePanel bind:name bind:settings slug={scene.slug} {layoutTitle} {builtin} onchangelayout={() => (picking = true)} />
          {:else}
            <StationsPanel bind:slots {stations} />
          {/if}
        </div>
      </aside>
    </div>
  </div>
{/if}

{#if picking}
  <Modal title={t("studio.change_layout")} onclose={() => (picking = false)} wide>
    <p class="muted small">{t("studio.change_layout_hint")}</p>
    <TemplatePicker
      {templates}
      customs={customs.filter((c) => c.key !== layoutKey)}
      builtins={layouts.filter((l) => !l.custom && l.id !== "replay")}
      selected={null}
      onpick={chooseLayout}
    />
  </Modal>
{/if}

<style>
  .studio {
    display: grid;
    grid-template-rows: auto auto auto minmax(0, 1fr);
    gap: 8px;
    height: var(--fill-h, calc(100vh - 60px));
    min-height: 520px;
  }
  .bar {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 8px;
  }
  .bar h1 {
    margin: 0;
    font-size: 20px;
    max-width: 28ch;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .back {
    color: var(--muted);
    white-space: nowrap;
  }
  .sep {
    width: 1px;
    height: 24px;
    background: var(--line);
  }
  .icon {
    min-width: 34px;
    padding: 4px 8px;
  }
  .icon.on {
    border-color: var(--accent);
    color: var(--accent);
  }
  .check {
    display: inline-flex;
    gap: 6px;
    align-items: center;
    font-size: 14px;
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
  .menu-list button {
    text-align: left;
    border: 0;
    background: none;
    padding: 8px 10px;
  }
  .menu-list button:hover {
    background: var(--panel-2);
  }
  .danger-text {
    color: var(--bad, #f83800);
  }
  .banner {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 10px;
    padding: 6px 12px;
    border: 1px solid var(--accent);
    border-radius: 8px;
  }
  .body {
    display: grid;
    grid-template-columns: 270px minmax(0, 1fr) 320px;
    gap: 10px;
    min-height: 0;
  }
  .col {
    display: grid;
    grid-template-rows: auto minmax(0, 1fr);
    gap: 6px;
    min-height: 0;
  }
  .scroll {
    display: grid;
    gap: 10px;
    align-content: start;
    overflow: auto;
    min-height: 0;
    padding-right: 2px;
  }
  .fixed {
    display: grid;
    gap: 8px;
    align-content: start;
  }
  .fixed h2 {
    margin: 0;
    font-size: 15px;
  }
  .fixed p {
    margin: 0;
  }
  .center {
    display: grid;
    grid-template-rows: minmax(0, 1fr) auto;
    gap: 8px;
    min-height: 0;
    min-width: 0;
  }
  .notice-box {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 8px 12px;
    background: color-mix(in srgb, var(--panel) 92%, transparent);
    border: 1px solid var(--accent);
    border-radius: 8px;
    box-shadow: 0 6px 20px rgb(0 0 0 / 0.5);
  }
  .errors ul {
    margin: 6px 0 0;
    padding-left: 18px;
  }
  .link {
    background: none;
    border: 0;
    padding: 0;
    color: var(--accent);
    cursor: pointer;
    text-decoration: underline;
  }
  @media (max-width: 1250px) {
    .body {
      grid-template-columns: 230px minmax(0, 1fr) 280px;
    }
  }
  @media (max-width: 1000px) {
    .studio {
      height: auto;
    }
    .body {
      grid-template-columns: 1fr;
    }
    .center {
      height: 60vh;
    }
  }
</style>
