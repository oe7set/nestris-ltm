<script lang="ts">
  import { copyText } from "../lib/clipboard";
  import { onMount } from "svelte";
  import Modal from "../components/Modal.svelte";
  import { api } from "../lib/api";
  import { i18n, t, tDynamic } from "../lib/i18n.svelte";
  import { toasts } from "../lib/toast.svelte";
  import type { StationRow } from "../lib/types";

  interface Layout {
    id: string;
    slots: number;
    title_de: string;
    title_en: string;
    description_de: string;
    description_en: string;
    supports_modes: boolean;
  }
  interface Slot {
    slot: number;
    station_id: string | null;
    label_override: string | null;
    name_override: string | null;
  }
  interface Scene {
    id: number;
    slug: string;
    name: string;
    layout: string;
    mode: string;
    auto_round: boolean;
    settings: { lang?: string; background?: string; camera_frames?: boolean; title?: string };
    slots: Slot[];
    round: number | null;
    clients: number;
  }
  interface SlotState {
    slot: number;
    name: string | null;
    status: string;
    score: number | null;
    outcome: string | null;
  }

  const MODES = ["none", "top2_advance", "worst_out", "winner_only"] as const;

  function blank() {
    return {
      slug: "",
      name: "",
      layout: "1v1",
      mode: "none",
      auto_round: false,
      lang: "de",
      background: "transparent",
      camera_frames: false,
      title: "",
      slots: [] as Slot[],
    };
  }

  let scenes = $state<Scene[]>([]);
  let layouts = $state<Layout[]>([]);
  let stations = $state<StationRow[]>([]);
  let live = $state<Record<string, SlotState[]>>({});
  let editing = $state<Scene | null>(null);
  let open = $state(false);
  let form = $state(blank());
  let previewSlug = $state<string | null>(null);

  const layout = $derived(layouts.find((l) => l.id === form.layout));
  // OBS usually runs on another PC: prefer the host's LAN address.
  let origin = $state(location.origin);

  async function load(): Promise<void> {
    try {
      [scenes, layouts, stations] = await Promise.all([
        api<Scene[]>("/api/scenes"),
        api<Layout[]>("/api/scenes/layouts"),
        api<StationRow[]>("/api/stations"),
      ]);
    } catch (e) {
      toasts.error(e);
    }
  }

  async function pollLive(): Promise<void> {
    for (const s of scenes) {
      try {
        const r = await api<{ state: { slots: SlotState[] } }>(`/api/scenes/${s.slug}/state`);
        live[s.slug] = r.state.slots;
      } catch {
        // the scene may just have been deleted
      }
    }
  }

  function slotsFor(count: number, existing: Slot[]): Slot[] {
    return Array.from(
      { length: count },
      (_, i) =>
        existing.find((s) => s.slot === i) ?? {
          slot: i,
          station_id: null,
          label_override: null,
          name_override: null,
        },
    );
  }

  function openNew(): void {
    editing = null;
    form = blank();
    form.slots = slotsFor(2, []);
    open = true;
  }

  function openEdit(scene: Scene): void {
    editing = scene;
    form = {
      slug: scene.slug,
      name: scene.name,
      layout: scene.layout,
      mode: scene.mode,
      auto_round: scene.auto_round,
      lang: scene.settings.lang ?? "de",
      background: scene.settings.background ?? "transparent",
      camera_frames: scene.settings.camera_frames ?? false,
      title: scene.settings.title ?? "",
      slots: slotsFor(layouts.find((l) => l.id === scene.layout)?.slots ?? 2, scene.slots),
    };
    open = true;
  }

  function onLayoutChange(): void {
    form.slots = slotsFor(layout?.slots ?? 1, form.slots);
    if (!layout?.supports_modes) form.mode = "none";
  }

  async function save(): Promise<void> {
    const body = {
      name: form.name.trim(),
      layout: form.layout,
      mode: form.mode,
      auto_round: form.auto_round,
      settings: {
        lang: form.lang,
        background: form.background,
        camera_frames: form.camera_frames,
        ...(form.title.trim() ? { title: form.title.trim() } : {}),
      },
      slots: form.slots.map((s) => ({
        slot: s.slot,
        station_id: s.station_id || null,
        label_override: s.label_override?.trim() || null,
        name_override: s.name_override?.trim() || null,
      })),
    };
    try {
      if (editing) await api(`/api/scenes/${editing.id}`, { method: "PATCH", body });
      else await api("/api/scenes", { method: "POST", body: { ...body, slug: form.slug.trim() } });
      open = false;
      toasts.ok(t("common.saved"));
      await load();
      await pollLive();
    } catch (e) {
      toasts.error(e);
    }
  }

  async function run(fn: () => Promise<unknown>, message?: string): Promise<void> {
    try {
      await fn();
      if (message) toasts.ok(message);
      await load();
      await pollLive();
    } catch (e) {
      toasts.error(e);
    }
  }

  async function copy(text: string): Promise<void> {
    try {
      await copyText(text);
      toasts.ok(t("common.copied"));
    } catch (e) {
      toasts.error(e);
    }
  }

  function slugify(name: string): string {
    return name
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-|-$/g, "")
      .slice(0, 64);
  }

  function layoutTitle(id: string): string {
    const l = layouts.find((x) => x.id === id);
    return l ? (i18n.locale === "en" ? l.title_en : l.title_de) : id;
  }

  function newRound(slug: string): void {
    void run(() => api(`/api/scenes/${slug}/rounds`, { method: "POST" }), t("scenes.round_started"));
  }

  function resetSlot(slug: string, slot: number): void {
    void run(() => api(`/api/scenes/${slug}/reset-slot`, { method: "POST", body: { slot } }));
  }

  function remove(scene: Scene): void {
    if (confirm(t("scenes.delete_confirm", { name: scene.name }))) {
      void run(() => api(`/api/scenes/${scene.id}`, { method: "DELETE" }));
    }
  }

  onMount(() => {
    void load().then(pollLive);
    api<{ base_urls: string[] }>("/api/meta/pages")
      .then((m) => (origin = m.base_urls[1] ?? m.base_urls[0] ?? location.origin))
      .catch(() => {});
    const timer = setInterval(pollLive, 1500);
    return () => clearInterval(timer);
  });
</script>

<div class="row">
  <h1>{t("scenes.title")}</h1>
  <span class="spacer"></span>
  <button class="primary" onclick={openNew}>+ {t("scenes.new")}</button>
</div>
<p class="hint">{t("scenes.hint")}</p>

<div class="list">
  {#each scenes as s (s.id)}
    <section class="panel scene">
      <div class="row">
        <strong>{s.name}</strong>
        <span class="badge">{layoutTitle(s.layout)}</span>
        {#if s.mode !== "none"}<span class="badge accent">{tDynamic(`scenes.mode.${s.mode}`, s.mode)}</span>{/if}
        {#if s.auto_round}<span class="badge">{t("scenes.auto_round_short")}</span>{/if}
        <span class="spacer"></span>
        <span class="muted small">{t("scenes.round")} {s.round ?? "–"} · OBS {s.clients}</span>
      </div>
      <div class="row url">
        <code class="mono">{origin}/o/{s.slug}</code>
        <button onclick={() => copy(`${origin}/o/${s.slug}`)}>{t("common.copy")}</button>
        <button onclick={() => (previewSlug = previewSlug === s.slug ? null : s.slug)}>{t("scenes.preview")}</button>
      </div>
      <div class="slots">
        {#each live[s.slug] ?? [] as st (st.slot)}
          {@const cfg = s.slots.find((x) => x.slot === st.slot)}
          <div class="slot">
            <span class="muted small">{t("scenes.slot")} {st.slot + 1} · {cfg?.station_id ?? "–"}</span>
            <span>{st.name ?? "–"}</span>
            <span class="badge {st.status === 'playing' ? 'ok' : st.status === 'finished' ? 'accent' : ''}">
              {tDynamic(`scenes.status.${st.status}`, st.status)}{st.score !== null ? ` · ${st.score.toLocaleString()}` : ""}
            </span>
            {#if st.outcome}
              <span class="badge {st.outcome === 'eliminated' ? 'bad' : 'ok'}">{tDynamic(`scenes.outcome.${st.outcome}`, st.outcome)}</span>
            {/if}
            {#if st.status === "finished" || st.status === "playing"}
              <button class="link small" onclick={() => resetSlot(s.slug, st.slot)}>{t("scenes.reset_slot")}</button>
            {/if}
          </div>
        {/each}
      </div>
      {#if previewSlug === s.slug}
        <div class="preview"><iframe src={`/o/${s.slug}?bg=dark`} title={s.name}></iframe></div>
      {/if}
      <div class="row">
        <button class="primary" onclick={() => newRound(s.slug)}>{t("scenes.new_round")}</button>
        <button onclick={() => openEdit(s)}>{t("common.edit")}</button>
        <span class="spacer"></span>
        <button class="danger" onclick={() => remove(s)}>{t("common.delete")}</button>
      </div>
    </section>
  {:else}
    <p class="muted">{t("scenes.none")}</p>
  {/each}
</div>

{#if open}
  <Modal title={editing ? editing.name : t("scenes.new")} onclose={() => (open = false)}>
    <div class="form-grid">
      <label class="field">
        {t("common.name")}
        <input
          bind:value={form.name}
          maxlength="128"
          oninput={() => {
            if (!editing) form.slug = slugify(form.name);
          }}
        />
      </label>
      <label class="field">
        {t("scenes.slug")}
        <input bind:value={form.slug} disabled={!!editing} pattern="[a-z0-9][a-z0-9\-]*" maxlength="64" />
      </label>
      <label class="field">
        {t("scenes.layout")}
        <select bind:value={form.layout} onchange={onLayoutChange}>
          {#each layouts as l (l.id)}<option value={l.id}>{i18n.locale === "en" ? l.title_en : l.title_de}</option>{/each}
        </select>
      </label>
      {#if layout?.supports_modes}
        <label class="field">
          {t("scenes.mode")}
          <select bind:value={form.mode}>
            {#each MODES as m (m)}<option value={m}>{tDynamic(`scenes.mode.${m}`, m)}</option>{/each}
          </select>
        </label>
      {/if}
    </div>
    {#if layout}<p class="hint">{i18n.locale === "en" ? layout.description_en : layout.description_de}</p>{/if}

    <div class="slot-form">
      {#each form.slots as slot (slot.slot)}
        <div class="row">
          <span class="muted small slot-no">{t("scenes.slot")} {slot.slot + 1}</span>
          <select bind:value={slot.station_id} aria-label={t("nav.stations")}>
            <option value={null}>–</option>
            {#each stations as st (st.id)}<option value={st.id}>{st.name ?? st.id}</option>{/each}
          </select>
          <input placeholder={t("scenes.name_override")} bind:value={slot.name_override} maxlength="64" />
        </div>
      {/each}
    </div>

    <div class="form-grid">
      <label class="field">{t("scenes.title_override")}<input bind:value={form.title} maxlength="64" /></label>
      <label class="field">
        {t("settings.language")}
        <select bind:value={form.lang}>
          <option value="de">Deutsch</option>
          <option value="en">English</option>
        </select>
      </label>
      <label class="field">
        {t("scenes.background")}
        <select bind:value={form.background}>
          <option value="transparent">{t("scenes.bg_transparent")}</option>
          <option value="dark">{t("scenes.bg_dark")}</option>
        </select>
      </label>
    </div>
    <label class="check"><input type="checkbox" bind:checked={form.camera_frames} /> {t("scenes.camera_frames")}</label>
    <label class="check"><input type="checkbox" bind:checked={form.auto_round} /> {t("scenes.auto_round")}</label>
    {#snippet footer()}
      <button onclick={() => (open = false)}>{t("common.cancel")}</button>
      <button class="primary" disabled={!form.name.trim() || !form.slug.trim()} onclick={save}>{t("common.save")}</button>
    {/snippet}
  </Modal>
{/if}

<style>
  .list {
    display: grid;
    gap: 14px;
  }
  .scene {
    display: grid;
    gap: 10px;
  }
  .url code {
    color: var(--link);
  }
  .slots {
    display: grid;
    gap: 6px;
    grid-template-columns: repeat(auto-fill, minmax(230px, 1fr));
  }
  .slot {
    display: grid;
    gap: 3px;
    padding: 8px 10px;
    border: 1px solid var(--line);
    border-radius: 8px;
    justify-items: start;
  }
  .preview iframe {
    width: 100%;
    aspect-ratio: 16 / 9;
    border: 1px solid var(--line);
    border-radius: 8px;
  }
  .slot-form {
    display: grid;
    gap: 6px;
  }
  .slot-form select,
  .slot-form input {
    flex: 1;
  }
  .slot-no {
    width: 60px;
  }
</style>
