<script lang="ts">
  import { copyText } from "../lib/clipboard";
  import { onMount } from "svelte";
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
    pairs: [number, number][];
  }
  interface Slot {
    slot: number;
    station_id: string | null;
    label_override: string | null;
    name_override: string | null;
  }
  /** Pairs that can be bound to a bracket match (none in qualifying: no hearts). */
  function matchPairs(s: Scene): [number, number][] {
    return s.qualifying ? [] : (layouts.find((l) => l.id === s.layout)?.pairs ?? []);
  }

  interface Scene {
    id: number;
    slug: string;
    name: string;
    layout: string;
    mode: string;
    auto_round: boolean;
    qualifying?: boolean;
    settings: { lang?: string; background?: string; camera_frames?: boolean; title?: string; style?: string };
    slots: Slot[];
    round: number | null;
    rounds?: number[];
    clients: number;
  }
  interface SlotState {
    slot: number;
    name: string | null;
    status: string;
    score: number | null;
    outcome: string | null;
    lives?: { current: number | null; max: number };
    match_result?: "won" | "lost" | null;
  }
  interface PairMatch {
    pair: number;
    match_id: string;
    round_name: string;
    bound_by: "manual" | "auto";
  }
  interface MatchOption {
    match_id: string;
    round_name: string;
    players: { nickname: string }[];
    winner_id: number | null;
  }

  let scenes = $state<Scene[]>([]);
  let layouts = $state<Layout[]>([]);
  let stations = $state<StationRow[]>([]);
  let live = $state<Record<string, SlotState[]>>({});
  let pairMatches = $state<Record<string, PairMatch[]>>({});
  let matchOptions = $state<MatchOption[]>([]);
  let previewSlug = $state<string | null>(null);

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
    await loadMatches();
  }

  async function loadMatches(): Promise<void> {
    try {
      matchOptions = (await api<{ matches: MatchOption[] }>("/api/tournament/matches")).matches;
    } catch {
      matchOptions = []; // no active event / bracket not fixed
    }
  }

  function matchLabel(m: MatchOption): string {
    return `${m.round_name}: ${m.players.map((p) => p.nickname).join(" vs ")}`;
  }

  async function bindPair(scene: Scene, pair: number, matchId: string): Promise<void> {
    await run(
      () => api(`/api/scenes/${scene.id}/pairs/${pair}/match`, { method: "PUT", body: { match_id: matchId || null } }),
      t("scenes.match_saved"),
    );
    await pollLive();
  }

  async function pollLive(): Promise<void> {
    for (const s of scenes) {
      try {
        const r = await api<{ state: { slots: SlotState[]; matches?: PairMatch[] } }>(`/api/scenes/${s.slug}/state`);
        live[s.slug] = r.state.slots;
        pairMatches[s.slug] = r.state.matches ?? [];
      } catch {
        // the scene may just have been deleted
      }
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

  function layoutTitle(id: string): string {
    const l = layouts.find((x) => x.id === id);
    return l ? (i18n.locale === "en" ? l.title_en : l.title_de) : id;
  }

  function newRound(slug: string, group?: number): void {
    const query = group === undefined ? undefined : { group: String(group) };
    void run(() => api(`/api/scenes/${slug}/rounds`, { method: "POST", query }), t("scenes.round_started"));
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
    const matchTimer = setInterval(() => void loadMatches(), 5000);
    return () => {
      clearInterval(timer);
      clearInterval(matchTimer);
    };
  });
</script>

<div class="row">
  <h1>{t("scenes.title")}</h1>
  <span class="spacer"></span>
  <a class="button primary" href="#/studio">+ {t("scenes.new")}</a>
</div>
<p class="hint">{t("scenes.hint")}</p>

<div class="list">
  {#each scenes as s (s.id)}
    <section class="panel scene">
      <div class="row">
        <strong>{s.name}</strong>
        <span class="badge">{layoutTitle(s.layout)}</span>
        {#if s.mode !== "none"}<span class="badge accent">{tDynamic(`scenes.mode.${s.mode}`, s.mode)}</span>{/if}
        {#if s.qualifying}
          <span class="badge accent">{t("studio.quali_badge")}</span>
        {:else if s.auto_round}
          <span class="badge">{t("scenes.auto_round_short")}</span>
        {/if}
        <span class="spacer"></span>
        <span class="muted small">
          {#if !s.qualifying}{t("scenes.round")} {s.rounds?.length ? s.rounds.join(" · ") : (s.round ?? "–")} ·{/if}
          OBS {s.clients}
        </span>
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
            {#if st.lives}
              <span class="hearts" title="{st.lives.current}/{st.lives.max}">
                {#each Array.from({ length: st.lives.max }, (_, i) => i) as i (i)}<span class:empty={i >= (st.lives.current ?? 0)}>♥</span>{/each}
              </span>
            {/if}
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
      <!-- Qualifying has no rounds and no hearts: no match binding. -->
      {#each matchPairs(s) as pair, index (index)}
        {@const bound = (pairMatches[s.slug] ?? []).find((p) => p.pair === index)}
        <div class="row pair">
          <span class="muted small">{t("scenes.match_for", { a: pair[0] + 1, b: pair[1] + 1 })}</span>
          <select value={bound?.match_id ?? ""} onchange={(e) => bindPair(s, index, e.currentTarget.value)}>
            <option value="">{t("scenes.match_none")}</option>
            {#each matchOptions.filter((m) => m.winner_id === null || m.match_id === bound?.match_id) as m (m.match_id)}
              <option value={m.match_id}>{matchLabel(m)}</option>
            {/each}
          </select>
          {#if bound}<span class="badge {bound.bound_by === 'manual' ? 'accent' : ''}">{bound.bound_by === "manual" ? t("scenes.match_manual") : t("scenes.match_auto")}</span>{/if}
        </div>
      {/each}
      {#if previewSlug === s.slug}
        <div class="preview"><iframe src={`/o/${s.slug}?bg=dark`} title={s.name}></iframe></div>
      {/if}
      <div class="row">
        {#if !s.qualifying}
          <button class="primary" onclick={() => newRound(s.slug)}>{t("scenes.new_round")}</button>
        {/if}
        {#if !s.qualifying && (layouts.find((l) => l.id === s.layout)?.pairs.length ?? 0) > 1}
          {#each layouts.find((l) => l.id === s.layout)?.pairs ?? [] as pair, index (index)}
            <button onclick={() => newRound(s.slug, index)}>{t("scenes.new_round_pair", { a: pair[0] + 1, b: pair[1] + 1 })}</button>
          {/each}
        {/if}
        <a class="button" href="#/studio/scene/{s.id}">{t("common.edit")}</a>
        <span class="spacer"></span>
        <button class="danger" onclick={() => remove(s)}>{t("common.delete")}</button>
      </div>
    </section>
  {:else}
    <p class="muted">{t("scenes.none")}</p>
  {/each}
</div>


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
  .pair {
    gap: 10px;
    align-items: center;
  }
  .pair select {
    max-width: 360px;
  }
  .hearts {
    color: #e5343a;
    font-size: 16px;
    letter-spacing: 1px;
  }
  .hearts .empty {
    color: transparent;
    -webkit-text-stroke: 1px #777;
  }
</style>
