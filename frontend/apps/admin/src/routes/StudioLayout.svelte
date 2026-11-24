<script lang="ts">
  // Layout editor for own layouts on their own (not tied to one scene):
  // the same stage and panels as the scene studio, with name and
  // description instead of the scene's look and stations.
  import { onMount } from "svelte";
  import GuideTools from "../components/GuideTools.svelte";
  import LayersPanel from "../components/studio/LayersPanel.svelte";
  import PropertiesPanel from "../components/studio/PropertiesPanel.svelte";
  import SlotsPanel from "../components/studio/SlotsPanel.svelte";
  import Stage from "../components/studio/Stage.svelte";
  import TemplatePicker from "../components/studio/TemplatePicker.svelte";
  import Tabs from "../components/Tabs.svelte";
  import { api, ApiError } from "../lib/api";
  import { confirmAsync } from "../lib/confirm.svelte";
  import { emptyDefinition } from "../lib/editor/elements";
  import { LayoutEditor } from "../lib/editor/layoutEditor.svelte";
  import { fillHeight } from "../lib/fillHeight";
  import { i18n, t, tDynamic } from "../lib/i18n.svelte";
  import { router } from "../lib/router.svelte";
  import {
    definitionPreview,
    downloadExport,
    type CustomLayout,
    type LayoutChoice,
    type LayoutDefinition,
    type Style,
    type Template,
  } from "../lib/studio";
  import { toasts } from "../lib/toast.svelte";
  import { uiPrefs } from "../lib/uiPrefs.svelte";

  let { id }: { id: string } = $props();

  interface ServerError {
    element: number | null;
    field: string;
    message: string;
  }
  interface Draft {
    name: string;
    description: string;
    def: LayoutDefinition;
    version: number | null;
    at: string;
  }

  const editor = new LayoutEditor();
  let layoutId = $state<string | null>(null);
  let version = $state<number | null>(null);
  let templateId = $state<string | null>(null);
  let name = $state("");
  let description = $state("");
  let saved = $state("");
  let usedBy = $state<string[]>([]);
  let loaded = $state(false);
  let notFound = $state(false);
  let starting = $state(false);
  let saving = $state(false);
  let templates = $state.raw<Template[]>([]);
  let draft = $state.raw<Draft | null>(null);
  let serverErrors = $state<ServerError[]>([]);

  let leftTab = $state<"layers" | "slots">("layers");
  let rightTab = $state<"props" | "layout">("layout");
  let style = $state<Style>("nes");
  let background = $state<"dark" | "checker">("dark");
  let showGrid = $state(true);
  let zoom = $state<"fit" | number>("fit");

  const snapshot = (): string => JSON.stringify({ name, description, def: editor.def });
  const dirty = $derived(loaded && !starting && snapshot() !== saved);
  const draftKey = $derived(`nltm.layout-draft.${id}`);
  const templateName = $derived.by(() => {
    const tpl = templates.find((x) => x.id === templateId);
    return tpl ? (i18n.locale === "en" ? tpl.name_en : tpl.name_de) : (templateId ?? "");
  });
  const preview = $derived(definitionPreview(editor.def, name || "Layout", style));

  function adopt(row: CustomLayout): void {
    layoutId = row.id;
    version = row.version;
    templateId = row.template_id ?? null;
    name = row.name;
    description = row.description;
    editor.load(row.definition ?? emptyDefinition());
    saved = snapshot();
  }

  function begin(definition: LayoutDefinition, title: string, template: string | null = null): void {
    editor.load(structuredClone($state.snapshot(definition)) as LayoutDefinition);
    name = title;
    description = "";
    templateId = template;
    saved = JSON.stringify({ name: "", description: "", def: emptyDefinition() });
    starting = false;
  }

  async function load(): Promise<void> {
    api<Template[]>("/api/studio/templates")
      .then((list) => (templates = list))
      .catch(() => {});
    if (id === "new") {
      starting = true;
      loaded = true;
      readDraft();
      return;
    }
    try {
      const [row, list] = await Promise.all([
        api<CustomLayout>(`/api/overlay-layouts/${encodeURIComponent(id)}`),
        api<CustomLayout[]>("/api/overlay-layouts"),
      ]);
      adopt(row);
      usedBy = list.find((l) => l.id === row.id)?.used_by ?? [];
      loaded = true;
      readDraft();
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) notFound = true;
      else toasts.error(e);
    }
  }

  // ---- draft

  function readDraft(): void {
    try {
      const raw = localStorage.getItem(draftKey);
      if (!raw) return;
      const d = JSON.parse(raw) as Draft;
      if (!d?.def || !Array.isArray(d.def.elements)) return;
      const same = JSON.stringify({ name: d.name, description: d.description, def: d.def }) === saved;
      if (!same && (d.version ?? null) === version) draft = d;
    } catch {
      // A broken draft is only a lost convenience.
    }
  }

  function restoreDraft(): void {
    if (!draft) return;
    const d = draft;
    if (starting) begin(d.def, d.name);
    else editor.apply(d.def);
    name = d.name;
    description = d.description;
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
    if (!dirty) return;
    const data: Draft = { name, description, def: editor.def, version, at: new Date().toISOString() };
    const timer = setTimeout(() => {
      try {
        localStorage.setItem(key, JSON.stringify(data));
      } catch {
        // storage full or blocked: no draft
      }
    }, 600);
    return () => clearTimeout(timer);
  });

  // ---- save

  async function save(asCopy: boolean): Promise<void> {
    if (saving) return;
    if (!name.trim()) {
      toasts.push("error", t("builder.name_required"));
      rightTab = "layout";
      return;
    }
    saving = true;
    const submitted = editor.def;
    const body = { name: name.trim(), description: description.trim(), definition: submitted };
    try {
      let row: CustomLayout;
      if (asCopy || layoutId === null) {
        row = await api<CustomLayout>("/api/overlay-layouts", {
          method: "POST",
          body: {
            ...(asCopy ? { ...body, name: t("builder.copy_name", { name: body.name }).slice(0, 64) } : body),
            template_id: templateId,
          },
        });
      } else {
        row = await api<CustomLayout>(`/api/overlay-layouts/${layoutId}`, {
          method: "PUT",
          body: { ...body, expected_version: version },
        });
      }
      serverErrors = [];
      editor.errorIds = [];
      dropDraft();
      toasts.ok(t("builder.saved"));
      if (asCopy || id === "new") {
        saved = snapshot(); // the work lives on in the new layout
        router.go(`/studio/layout/${row.id}`);
      } else {
        adopt(row);
      }
    } catch (e) {
      if (e instanceof ApiError && e.code === "invalid") {
        const detail = (e.body as { detail?: { errors?: ServerError[] } } | null)?.detail;
        serverErrors = detail?.errors ?? [];
        editor.errorIds = serverErrors
          .map((err) => (err.element !== null ? submitted.elements[err.element]?.id : undefined))
          .filter((x): x is string => !!x);
        toasts.push("error", t("builder.invalid", { n: serverErrors.length }));
      } else if (e instanceof ApiError && e.code === "stale") {
        toasts.push("error", t("builder.stale"));
      } else {
        toasts.error(e);
      }
    } finally {
      saving = false;
    }
  }

  async function resetToTemplate(): Promise<void> {
    if (!layoutId || !templateId || version === null) return;
    if (!(await confirmAsync({ title: t("studio.reset_confirm"), danger: true, confirmLabel: t("studio.reset") }))) return;
    try {
      adopt(await api<CustomLayout>(`/api/overlay-layouts/${layoutId}/reset`, { method: "POST", body: { expected_version: version } }));
      dropDraft();
      toasts.ok(t("studio.reset_done"));
    } catch (e) {
      if (e instanceof ApiError && e.code === "stale") toasts.error(t("builder.stale"));
      else toasts.error(e);
    }
  }

  async function remove(): Promise<void> {
    if (!layoutId) return;
    if (!(await confirmAsync({ title: t("studio.confirm_delete_layout", { name }), danger: true, confirmLabel: t("common.delete") }))) return;
    try {
      await api(`/api/overlay-layouts/${layoutId}`, { method: "DELETE" });
      dropDraft();
      saved = snapshot();
      router.go("/studio");
    } catch (e) {
      toasts.error(e);
    }
  }

  function pickStart(choice: LayoutChoice): void {
    if (choice.kind === "template") {
      const tpl = choice.template;
      begin(tpl.definition, i18n.locale === "en" ? tpl.name_en : tpl.name_de, tpl.id);
    }
  }

  $effect(() => {
    if (editor.selected.length) rightTab = "props";
  });

  function onKey(event: KeyboardEvent): void {
    if (!loaded || starting) return;
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s") {
      event.preventDefault();
      void save(false);
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
{:else if loaded && starting}
  <div class="head row">
    <a href="#/studio" class="muted">← {t("studio.title")}</a>
    <h1>{t("builder.title_new")}</h1>
  </div>
  {#if draft}
    <div class="banner">
      <span>{t("builder.draft_found", { at: new Date(draft.at).toLocaleString(i18n.locale) })}</span>
      <span class="spacer"></span>
      <button class="primary" onclick={restoreDraft}>{t("builder.draft_restore")}</button>
      <button onclick={dropDraft}>{t("builder.draft_discard")}</button>
    </div>
  {/if}
  <p class="muted">{t("builder.start")}</p>
  <div class="blank-row">
    {#each [1, 2, 4] as n (n)}
      <button class="blank" onclick={() => begin(emptyDefinition(n), "")}>
        <strong>{t("builder.start_blank")}</strong>
        <span class="muted small">{t("builder.start_blank_hint", { n })}</span>
      </button>
    {/each}
  </div>
  <TemplatePicker {templates} selected={null} onpick={pickStart} />
{:else if loaded}
  <div class="studio fill-page" use:fillHeight>
    <div class="bar">
      <a href="#/studio" class="back">← {t("studio.title")}</a>
      <h1>{name || t("builder.title_new")}</h1>
      {#if dirty}<span class="badge warn">{t("studio.unsaved")}</span>{/if}
      <span class="sep"></span>
      <button class="icon" title="{t('builder.undo')} (Ctrl+Z)" aria-label={t("builder.undo")} disabled={!editor.canUndo} onclick={() => editor.undo()}>↶</button>
      <button class="icon" title="{t('builder.redo')} (Ctrl+Y)" aria-label={t("builder.redo")} disabled={!editor.canRedo} onclick={() => editor.redo()}>↷</button>
      <span class="sep"></span>
      <div class="seg" title={t("builder.style_preview")}>
        <button aria-pressed={style === "nes"} class:on={style === "nes"} onclick={() => (style = "nes")}>NES</button>
        <button aria-pressed={style === "modern"} class:on={style === "modern"} onclick={() => (style = "modern")}>Modern</button>
      </div>
      <div class="seg">
        <button aria-pressed={background === "checker"} class:on={background === "checker"} onclick={() => (background = "checker")}>{t("studio.bg_checker")}</button>
        <button aria-pressed={background === "dark"} class:on={background === "dark"} onclick={() => (background = "dark")}>{t("scenes.bg_dark")}</button>
      </div>
      <label class="check"><input type="checkbox" bind:checked={showGrid} /> {t("builder.grid")}</label>
      <GuideTools />
      <span class="spacer"></span>
      <button class="icon" title={t("studio.focus_hint")} aria-pressed={uiPrefs.studioFocus} class:on={uiPrefs.studioFocus} onclick={() => uiPrefs.toggle("studioFocus")}>⛶</button>
      {#if layoutId}
        {#if templateId}<button onclick={resetToTemplate}>{t("studio.reset_template")}</button>{/if}
        <button onclick={() => layoutId && downloadExport({ layouts: layoutId }).catch((e) => toasts.error(e))}>{t("studio.export")}</button>
        <button class="danger" disabled={usedBy.length > 0} title={usedBy.length ? t("studio.in_use") : ""} onclick={remove}>{t("common.delete")}</button>
        <button onclick={() => save(true)} disabled={saving}>{t("builder.save_copy")}</button>
      {/if}
      <button class="primary" title="Ctrl+S" onclick={() => save(false)} disabled={saving || (!dirty && layoutId !== null)}>{t("builder.save")}</button>
    </div>
    {#if draft}
      <div class="banner">
        <span>{t("builder.draft_found", { at: new Date(draft.at).toLocaleString(i18n.locale) })}</span>
        <span class="spacer"></span>
        <button class="primary" onclick={restoreDraft}>{t("builder.draft_restore")}</button>
        <button onclick={dropDraft}>{t("builder.draft_discard")}</button>
      </div>
    {:else if usedBy.length}
      <p class="hint">{t("builder.used_by", { scenes: usedBy.join(", ") })}</p>
    {/if}

    <div class="body">
      <aside class="col">
        <Tabs tabs={[{ id: "layers", label: t("builder.layers") }, { id: "slots", label: t("studio.slots_pairs") }]} active={leftTab} onchange={(v) => (leftTab = v)} />
        <div class="scroll">
          {#if leftTab === "layers"}<LayersPanel {editor} />{:else}<SlotsPanel {editor} />{/if}
        </div>
      </aside>
      <section class="center">
        <Stage {editor} {preview} {background} bind:showGrid bind:zoom />
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
      <aside class="col">
        <Tabs tabs={[{ id: "props", label: t("builder.properties") }, { id: "layout", label: t("builder.layout") }]} active={rightTab} onchange={(v) => (rightTab = v)} />
        <div class="scroll">
          {#if rightTab === "props"}
            <PropertiesPanel {editor} nes={style === "nes"} />
          {:else}
            <section class="panel block">
              <label class="field">{t("builder.name")}<input bind:value={name} maxlength="64" /></label>
              <label class="field">{t("builder.description")}<textarea bind:value={description} maxlength="500" rows="3"></textarea></label>
              {#if templateId}<p class="muted small">{t("studio.from_template", { name: templateName })}</p>{/if}
            </section>
          {/if}
        </div>
      </aside>
    </div>
  </div>
{/if}

<style>
  .head {
    gap: 10px;
    margin-bottom: 10px;
  }
  .head h1 {
    margin: 0;
  }
  .blank-row {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
    gap: 10px;
    margin-bottom: 12px;
  }
  .blank {
    display: grid;
    gap: 4px;
    padding: 12px;
    text-align: left;
    border-style: dashed;
  }
  .studio {
    display: grid;
    grid-template-rows: auto auto minmax(0, 1fr);
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
  .banner {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 10px;
    padding: 6px 12px;
    border: 1px solid var(--accent);
    border-radius: 8px;
  }
  .hint {
    margin: 0;
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
  }
  .block {
    display: grid;
    gap: 10px;
  }
  .center {
    display: grid;
    grid-template-rows: minmax(0, 1fr) auto;
    gap: 8px;
    min-height: 0;
    min-width: 0;
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
