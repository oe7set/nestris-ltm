<script lang="ts">
  // Scene editor: everything about a scene's look and stations, with a large
  // live preview that follows every change before it is saved.
  import { onMount } from "svelte";
  import GuideOverlay from "../components/GuideOverlay.svelte";
  import GuideTools from "../components/GuideTools.svelte";
  import Modal from "../components/Modal.svelte";
  import Thumb from "../components/Thumb.svelte";
  import { api, ApiError } from "../lib/api";
  import { fillHeight } from "../lib/fillHeight";
  import { i18n, t, tDynamic } from "../lib/i18n.svelte";
  import { router } from "../lib/router.svelte";
  import {
    cleanSettings,
    defaultSettings,
    downloadExport,
    MODES,
    previewOf,
    SHOW_KEYS,
    THEME_DEFAULTS,
    THEME_KEYS,
    type CustomLayout,
    type LayoutInfo,
    type SceneRow,
    type SceneSettings,
    type SlotRow,
  } from "../lib/studio";
  import { toasts } from "../lib/toast.svelte";
  import type { StationRow } from "../lib/types";

  let { id }: { id: string } = $props();

  let scene = $state<SceneRow | null>(null);
  let layouts = $state<LayoutInfo[]>([]);
  let customs = $state<CustomLayout[]>([]);
  let stations = $state<StationRow[]>([]);
  let notFound = $state(false);
  let saving = $state(false);
  let picking = $state(false);
  let source = $state<"demo" | "live">("demo");
  let background = $state<"dark" | "checker" | "transparent">("checker");

  // The edited copy (saved = what the server has).
  let name = $state("");
  let layout = $state("1v1");
  let mode = $state("none");
  let autoRound = $state(false);
  let qualifying = $state(false);
  // One choice in the editor for both flags.
  type Flow = "manual" | "auto" | "quali";
  const flow = $derived<Flow>(qualifying ? "quali" : autoRound ? "auto" : "manual");
  function setFlow(next: Flow): void {
    qualifying = next === "quali";
    autoRound = next === "auto";
  }
  let settings = $state<SceneSettings>(defaultSettings());
  let slots = $state<SlotRow[]>([]);
  let saved = $state("");

  function snapshot(): string {
    return JSON.stringify({ name, layout, mode, autoRound, qualifying, settings: cleanSettings(settings), slots });
  }
  const dirty = $derived(scene !== null && snapshot() !== saved);

  function adopt(s: SceneRow): void {
    scene = s;
    name = s.name;
    layout = s.layout;
    mode = s.mode;
    autoRound = s.auto_round;
    qualifying = s.qualifying ?? false;
    settings = { ...defaultSettings(), ...s.settings, theme: { ...s.settings.theme }, show: { ...defaultSettings().show, ...s.settings.show } };
    slots = slotsFor(info?.slots ?? s.slots.length, s.slots);
    saved = snapshot();
  }

  const info = $derived(layouts.find((l) => l.id === layout));
  const customDef = $derived(customs.find((c) => c.key === layout)?.definition ?? null);
  const builtin = $derived(info ? !info.custom : true);

  function slotsFor(count: number, existing: SlotRow[]): SlotRow[] {
    return Array.from(
      { length: count },
      (_, i) => existing.find((s) => s.slot === i) ?? { slot: i, station_id: null, label_override: null, name_override: null },
    );
  }

  async function load(): Promise<void> {
    try {
      const [all, ls, cs, st] = await Promise.all([
        api<SceneRow[]>("/api/scenes"),
        api<LayoutInfo[]>("/api/scenes/layouts"),
        api<CustomLayout[]>("/api/overlay-layouts"),
        api<StationRow[]>("/api/stations"),
      ]);
      layouts = ls;
      stations = st;
      // Definitions of own layouts for the preview (no extra round trip later).
      customs = await Promise.all(cs.map((c) => api<CustomLayout>(`/api/overlay-layouts/${c.id}`)));
      const found = all.find((s) => String(s.id) === id);
      if (!found) {
        notFound = true;
        return;
      }
      adopt(found);
    } catch (e) {
      toasts.error(e);
    }
  }

  function chooseLayout(next: string): void {
    layout = next;
    const l = layouts.find((x) => x.id === next);
    slots = slotsFor(l?.slots ?? slots.length, slots);
    if (!l?.supports_modes) mode = "none";
    picking = false;
  }

  async function save(): Promise<void> {
    if (!scene) return;
    saving = true;
    try {
      const updated = await api<SceneRow>(`/api/scenes/${scene.id}`, {
        method: "PATCH",
        body: {
          name: name.trim(),
          layout,
          mode,
          auto_round: autoRound,
          qualifying,
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
      adopt({ ...scene, ...updated });
      toasts.ok(t("studio.saved"));
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) toasts.error(t("studio.stale"));
      else toasts.error(e);
    } finally {
      saving = false;
    }
  }

  function revert(): void {
    if (scene) adopt(scene);
  }

  async function duplicate(): Promise<void> {
    // The copy is made from the saved scene; leaving asks about unsaved changes (guard).
    if (!scene) return;
    try {
      const copy = await api<SceneRow>(`/api/scenes/${scene.id}/duplicate`, { method: "POST", body: {} });
      router.go(`/studio/scene/${copy.id}`);
    } catch (e) {
      toasts.error(e);
    }
  }

  async function remove(): Promise<void> {
    if (!scene || !confirm(t("studio.confirm_delete_scene", { name: scene.name }))) return;
    try {
      await api(`/api/scenes/${scene.id}`, { method: "DELETE" });
      saved = snapshot(); // nothing left to lose
      router.go("/studio");
    } catch (e) {
      toasts.error(e);
    }
  }

  const preview = $derived(
    scene
      ? previewOf(
          { slug: scene.slug, name, layout, mode, auto_round: autoRound, qualifying, settings },
          info,
          {
            names: slots.map((s) => s.name_override?.trim() || null),
            definition: customDef,
            liveSlug: source === "live" ? scene.slug : null,
          },
        )
      : null,
  );

  onMount(() => {
    void load();
    // Leaving with unsaved changes: ask first (browser close and in-app navigation).
    const beforeUnload = (e: BeforeUnloadEvent): void => {
      if (dirty) e.preventDefault();
    };
    const unguard = router.setGuard(() => !dirty || confirm(t("studio.unsaved_confirm")));
    addEventListener("beforeunload", beforeUnload);
    return () => {
      removeEventListener("beforeunload", beforeUnload);
      unguard();
    };
  });
</script>

{#if notFound}
  <p class="muted">{t("common.not_found")} · <a href="#/studio">{t("studio.title")}</a></p>
{:else if scene}
  <div class="head row">
    <a href="#/studio" class="muted">← {t("studio.title")}</a>
    <h1>{name || scene.name}</h1>
    {#if dirty}<span class="badge warn">{t("studio.unsaved")}</span>{/if}
    <span class="spacer"></span>
    <button onclick={duplicate}>{t("studio.duplicate")}</button>
    <button onclick={() => scene && downloadExport({ scenes: String(scene.id) }).catch((e) => toasts.error(e))}>{t("studio.export")}</button>
    <button class="danger" onclick={remove}>{t("common.delete")}</button>
    <button disabled={!dirty || saving} onclick={revert}>{t("studio.revert")}</button>
    <button class="primary" disabled={!dirty || saving || !name.trim()} onclick={save}>{t("common.save")}</button>
  </div>

  <div class="editor fill-page">
    <aside class="side" use:fillHeight>
      <section class="panel block">
        <h2>{t("studio.general")}</h2>
        <label class="field">{t("common.name")}<input bind:value={name} maxlength="128" /></label>
        <div class="field">
          <span>{t("studio.url")}</span>
          <code class="mono">/o/{scene.slug}</code>
        </div>
        <div class="field">
          <span>{t("scenes.layout")}</span>
          <button class="layout-btn" onclick={() => (picking = true)}>
            {info ? (i18n.locale === "en" ? info.title_en : info.title_de) : layout} — {t("studio.change")}
          </button>
        </div>
        <label class="field">
          {t("studio.flow")}
          <select value={flow} onchange={(e) => setFlow(e.currentTarget.value as Flow)}>
            <option value="manual">{t("studio.flow_manual")}</option>
            <option value="auto">{t("studio.flow_auto")}</option>
            <option value="quali">{t("studio.flow_quali")}</option>
          </select>
        </label>
        <p class="muted small">{t(flow === "quali" ? "studio.flow_quali_hint" : "studio.flow_rounds_hint")}</p>
        {#if info?.supports_modes && !qualifying}
          <label class="field">
            {t("scenes.mode")}
            <select bind:value={mode}>
              {#each MODES as m (m)}<option value={m}>{tDynamic(`scenes.mode.${m}`, m)}</option>{/each}
            </select>
          </label>
        {/if}
      </section>

      <section class="panel block">
        <h2>{t("studio.look")}</h2>
        <div class="seg">
          <button class:on={settings.style === "nes"} onclick={() => (settings.style = "nes")}>NES</button>
          <button class:on={settings.style === "modern"} onclick={() => (settings.style = "modern")}>Modern</button>
        </div>
        <label class="field">{t("scenes.title_override")}<input bind:value={settings.title} maxlength="64" placeholder={name} /></label>
        <div class="two">
          <label class="field">
            {t("settings.language")}
            <select bind:value={settings.lang}><option value="de">Deutsch</option><option value="en">English</option></select>
          </label>
          <label class="field">
            {t("scenes.background")}
            <select bind:value={settings.background}>
              <option value="transparent">{t("scenes.bg_transparent")}</option>
              <option value="dark">{t("scenes.bg_dark")}</option>
            </select>
          </label>
        </div>
        <label class="check"><input type="checkbox" bind:checked={settings.camera_frames} /> {t("scenes.camera_frames")}</label>
      </section>

      <section class="panel block">
        <div class="row"><h2>{t("studio.colors")}</h2><span class="spacer"></span>
          <button class="link small" onclick={() => (settings.theme = {})}>{t("studio.reset_colors")}</button></div>
        <div class="colors">
          {#each THEME_KEYS as k (k)}
            <label class="color">
              <input
                type="color"
                value={settings.theme[k] ?? THEME_DEFAULTS[k]}
                oninput={(e) => (settings.theme = { ...settings.theme, [k]: e.currentTarget.value })}
              />
              <span class:custom={!!settings.theme[k]}>{tDynamic(`studio.color_${k}`, k)}</span>
              {#if settings.theme[k]}
                <button class="link small" aria-label={t("studio.reset_colors")} onclick={() => { const { [k]: _, ...rest } = settings.theme; settings.theme = rest; }}>↺</button>
              {/if}
            </label>
          {/each}
        </div>
      </section>

      {#if builtin}
        <section class="panel block">
          <h2>{t("studio.blocks")}</h2>
          <div class="blocks">
            {#each SHOW_KEYS as k (k)}
              <label class="check"><input type="checkbox" bind:checked={settings.show[k]} /> {tDynamic(`studio.block_${k}`, k)}</label>
            {/each}
          </div>
        </section>
      {/if}

      <section class="panel block">
        <h2>{t("studio.stations")}</h2>
        <p class="muted small">{t("studio.stations_hint")}</p>
        {#each slots as slot (slot.slot)}
          <div class="slot row">
            <span class="muted small slot-no">{t("scenes.slot")} {slot.slot + 1}</span>
            <select bind:value={slot.station_id}>
              <option value={null}>–</option>
              {#each stations as st (st.id)}<option value={st.id}>{st.name ?? st.id}</option>{/each}
            </select>
            <input placeholder={t("scenes.name_override")} bind:value={slot.name_override} maxlength="64" />
          </div>
        {/each}
      </section>
    </aside>

    <section class="stage-col">
      <div class="row tools">
        <div class="seg">
          <button class:on={source === "demo"} onclick={() => (source = "demo")}>{t("studio.demo")}</button>
          <button class:on={source === "live"} onclick={() => (source = "live")}>{t("studio.live")}</button>
        </div>
        <div class="seg">
          <button class:on={background === "checker"} onclick={() => (background = "checker")}>{t("studio.bg_checker")}</button>
          <button class:on={background === "dark"} onclick={() => (background = "dark")}>{t("scenes.bg_dark")}</button>
        </div>
        <GuideTools />
        <span class="spacer"></span>
        <a class="small" href="/o/{scene.slug}" target="_blank" rel="noopener">{t("studio.open_overlay")} ↗</a>
      </div>
      <div class="preview">
        <Thumb config={preview} still={false} background={background === "dark" ? "dark" : "checker"} title={name} />
        <GuideOverlay />
      </div>
      {#if source === "live"}<p class="muted small">{t("studio.live_hint")}</p>{/if}
    </section>
  </div>
{/if}

{#if picking}
  <Modal title={t("studio.pick_layout")} onclose={() => (picking = false)} wide>
    <div class="layout-pick">
      {#each layouts.filter((l) => l.id !== "replay" || layout === "replay") as l (l.id)}
        <button class="pick" class:on={layout === l.id} onclick={() => chooseLayout(l.id)}>
          <Thumb config={previewOf({ slug: "preview", name, layout: l.id, mode: "none", auto_round: false, settings }, l, { definition: customs.find((c) => c.key === l.id)?.definition ?? null })} />
          <span>{i18n.locale === "en" ? l.title_en : l.title_de}{l.custom ? " ★" : ""}</span>
        </button>
      {/each}
    </div>
  </Modal>
{/if}

<style>
  .head {
    gap: 10px;
    margin-bottom: 12px;
    flex-wrap: wrap;
  }
  .head h1 {
    margin: 0;
  }
  .editor {
    display: grid;
    grid-template-columns: minmax(320px, 400px) 1fr;
    gap: 16px;
    align-items: start;
  }
  .side {
    display: grid;
    gap: 12px;
    max-height: var(--fill-h, calc(100vh - 150px));
    overflow: auto;
    padding-right: 4px;
  }
  .block {
    display: grid;
    gap: 10px;
  }
  .block h2 {
    margin: 0;
    font-size: 15px;
  }
  .preview {
    position: relative;
  }
  .stage-col {
    position: sticky;
    top: 12px;
    display: grid;
    gap: 10px;
  }
  .tools {
    gap: 10px;
    align-items: center;
  }
  .seg {
    display: inline-flex;
    border: 1px solid var(--line);
    border-radius: 8px;
    overflow: hidden;
  }
  .seg button {
    border: 0;
    border-radius: 0;
  }
  .seg button.on {
    background: var(--accent);
    color: var(--accent-ink);
  }
  .two {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 10px;
  }
  .colors {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 8px;
  }
  .color {
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .color input {
    width: 34px;
    height: 26px;
    padding: 0;
    border: 1px solid var(--line);
  }
  .color .custom {
    color: var(--accent);
  }
  .blocks {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 6px;
  }
  .slot {
    gap: 6px;
  }
  .slot select,
  .slot input {
    min-width: 0;
    flex: 1;
  }
  .slot-no {
    width: 52px;
    flex: none;
  }
  .layout-btn {
    text-align: left;
  }
  .layout-pick {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
    gap: 10px;
    max-height: 64vh;
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
  @media (max-width: 1100px) {
    .editor {
      grid-template-columns: 1fr;
    }
    .stage-col {
      position: static;
    }
  }
</style>
