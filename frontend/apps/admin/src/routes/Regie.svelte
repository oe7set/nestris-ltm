<script lang="ts">
  // Control room: everything needed during the event on one page. The
  // tournament phase (qualifying / fixed, FIX), the global run switches, and
  // per scene: how it runs, the live slots with hearts -/+, the match each
  // pair shows, new round, reset slot. Designing scenes is the studio's job.
  import Hearts from "../components/Hearts.svelte";
  import Segmented from "../components/Segmented.svelte";
  import { onMount } from "svelte";
  import PhaseBanner from "../components/PhaseBanner.svelte";
  import { poll } from "../lib/poll";
  import { api } from "../lib/api";
  import { changeHeart } from "../lib/hearts";
  import { copyText } from "../lib/clipboard";
  import { i18n, t, tDynamic } from "../lib/i18n.svelte";
  import { FLOWS, type Flow, type LayoutInfo, type SceneRow } from "../lib/studio";
  import { toasts } from "../lib/toast.svelte";

  const MODES = ["none", "top2_advance", "worst_out", "winner_only"] as const;

  interface SlotState {
    slot: number;
    name: string | null;
    station_id: string | null;
    status: string;
    score: number | null;
    outcome: string | null;
    lives?: { current: number | null; max: number };
    match_result?: "won" | "lost" | null;
    player_id?: number;
  }
  interface PairMatch {
    pair: number;
    match_id: string;
    round_name: string;
    bound_by: "manual" | "auto";
  }
  interface SceneState {
    scene: { qualifying?: boolean; seeded?: boolean };
    round: number;
    groups: { group: number; round: number; complete: boolean }[];
    slots: SlotState[];
    matches?: PairMatch[];
  }
  interface MatchOption {
    match_id: string;
    round_name: string;
    players: { nickname: string }[];
    winner_id: number | null;
  }
  interface LivesSettings {
    default_lives: number;
    auto_bind: boolean;
    auto_deduct: boolean;
  }

  let scenes = $state<(SceneRow & { clients: number })[]>([]);
  let layouts = $state<LayoutInfo[]>([]);
  let live = $state<Record<string, SceneState>>({});
  let matchOptions = $state<MatchOption[]>([]);
  let lives = $state<LivesSettings | null>(null);
  let nextRound = $state<"manual" | "auto">("manual");
  let previewSlug = $state<string | null>(null);
  let busy = $state(false);
  // OBS usually runs on another PC: prefer the host's LAN address.
  let origin = $state(location.origin);

  async function load(): Promise<void> {
    try {
      [scenes, layouts] = await Promise.all([
        api<(SceneRow & { clients: number })[]>("/api/scenes"),
        api<LayoutInfo[]>("/api/scenes/layouts"),
      ]);
      nextRound = (await api<{ next_round: "manual" | "auto" }>("/api/settings/scenes")).next_round;
    } catch (e) {
      toasts.error(e);
    }
    await loadMatches();
  }

  async function loadMatches(): Promise<void> {
    try {
      const info = await api<{ settings: LivesSettings; matches: MatchOption[] }>("/api/tournament/matches");
      matchOptions = info.matches;
      lives = info.settings;
    } catch {
      matchOptions = []; // no active event
      lives = null;
    }
  }

  async function pollLive(): Promise<void> {
    for (const s of scenes) {
      try {
        live[s.slug] = (await api<{ state: SceneState }>(`/api/scenes/${s.slug}/state`)).state;
      } catch {
        // the scene may just have been deleted
      }
    }
  }

  async function run(fn: () => Promise<unknown>, message?: string): Promise<void> {
    if (busy) return;
    busy = true;
    try {
      await fn();
      if (message) toasts.ok(message);
    } catch (e) {
      toasts.error(e);
    } finally {
      busy = false;
      await load();
      await pollLive();
    }
  }

  const layoutOf = (s: SceneRow): LayoutInfo | undefined => layouts.find((l) => l.id === s.layout);
  const layoutTitle = (s: SceneRow): string => {
    const l = layoutOf(s);
    return l ? (i18n.locale === "en" ? l.title_en : l.title_de) : s.layout;
  };
  const isQuali = (s: SceneRow): boolean => live[s.slug]?.scene.qualifying ?? s.flow === "quali";

  function setFlow(s: SceneRow, flow: Flow): void {
    void run(() => api(`/api/scenes/${s.id}/flow`, { method: "PATCH", body: { flow } }), t("common.saved"));
  }
  function setMode(s: SceneRow, mode: string): void {
    void run(() => api(`/api/scenes/${s.id}/flow`, { method: "PATCH", body: { mode } }), t("common.saved"));
  }
  function setNextRound(value: "manual" | "auto"): void {
    void run(() => api("/api/settings/scenes", { method: "PUT", body: { next_round: value } }), t("common.saved"));
  }
  function setLives(change: Partial<LivesSettings>): void {
    void run(() => api("/api/tournament/lives/settings", { method: "PUT", body: change }), t("common.saved"));
  }
  function newRound(s: SceneRow, group?: number): void {
    const query = group === undefined ? undefined : { group: String(group) };
    void run(() => api(`/api/scenes/${s.slug}/rounds`, { method: "POST", query }), t("scenes.round_started"));
  }
  function resetSlot(s: SceneRow, slot: number): void {
    void run(() => api(`/api/scenes/${s.slug}/reset-slot`, { method: "POST", body: { slot } }));
  }
  function bindPair(s: SceneRow, pair: number, matchId: string): void {
    void run(
      () => api(`/api/scenes/${s.id}/pairs/${pair}/match`, { method: "PUT", body: { match_id: matchId || null } }),
      t("scenes.match_saved"),
    );
  }
  /** Hearts of the match the slot's pair shows. */
  function heart(s: SceneRow, st: SlotState, action: "lose" | "gain"): void {
    const pair = layoutOf(s)?.pairs.findIndex((p) => p.includes(st.slot)) ?? -1;
    const match = live[s.slug]?.matches?.find((m) => m.pair === pair);
    if (!match || st.player_id === undefined || st.player_id === null) return;
    const playerId = st.player_id;
    void run(() => changeHeart(match.match_id, playerId, st.name ?? "–", action, pollLive));
  }
  const matchLabel = (m: MatchOption): string => `${m.round_name}: ${m.players.map((p) => p.nickname).join(" vs ")}`;
  const roundText = (s: SceneRow): string => {
    const state = live[s.slug];
    if (!state) return "";
    if (isQuali(s)) return t("studio.quali_badge");
    return `${t("scenes.round")} ${state.groups.map((g) => g.round).join(" · ")}`;
  };

  async function copy(text: string): Promise<void> {
    try {
      await copyText(text);
      toasts.ok(t("common.copied"));
    } catch (e) {
      toasts.error(e);
    }
  }

  onMount(() => {
    void load().then(pollLive);
    api<{ base_urls: string[] }>("/api/meta/pages")
      .then((m) => (origin = m.base_urls[1] ?? m.base_urls[0] ?? location.origin))
      .catch(() => {});
    const stopLive = poll(pollLive, 1500);
    const stopMatches = poll(loadMatches, 5000);
    return () => {
      stopLive();
      stopMatches();
    };
  });
</script>

<div class="row head">
  <h1>{t("regie.title")}</h1>
  <span class="spacer"></span>
  <a class="button" href="#/studio">{t("regie.design")} →</a>
</div>

<PhaseBanner onchange={() => void pollLive()} />

<section class="panel switches">
  <Segmented
    label={t("regie.next_round")}
    options={[
      { value: "manual", label: t("regie.next_round_manual") },
      { value: "auto", label: t("regie.next_round_auto") },
    ]}
    value={nextRound}
    onchange={setNextRound}
  />
  {#if lives}
    <label class="check" title={t("regie.auto_bind_hint")}>
      <input type="checkbox" checked={lives.auto_bind} onchange={(e) => setLives({ auto_bind: e.currentTarget.checked })} />
      {t("matches.auto_bind")}
    </label>
    <label class="check" title={t("matches.auto_deduct_hint")}>
      <input type="checkbox" checked={lives.auto_deduct} onchange={(e) => setLives({ auto_deduct: e.currentTarget.checked })} />
      {t("matches.auto_deduct")}
    </label>
    <span class="muted small">{t("regie.default_hearts", { n: lives.default_lives })} · <a href="#/settings?tab=tournament">{t("nav.settings")}</a></span>
  {/if}
</section>

<div class="list">
  {#each scenes as s (s.id)}
    {@const state = live[s.slug]}
    {@const layout = layoutOf(s)}
    {@const quali = isQuali(s)}
    <section class="panel scene">
      <div class="row">
        <strong>{s.name}</strong>
        <span class="badge">{layoutTitle(s)}</span>
        <span class="badge {quali ? 'quali' : 'accent'}">{roundText(s)}</span>
        <span class="spacer"></span>
        <span class="muted small">OBS {s.clients}</span>
      </div>

      <div class="row controls">
        <label class="field">
          {t("regie.flow")}
          <select value={s.flow} onchange={(e) => setFlow(s, e.currentTarget.value as Flow)}>
            {#each FLOWS as f (f)}<option value={f}>{tDynamic(`regie.flow_${f}`, f)}</option>{/each}
          </select>
        </label>
        {#if !quali && layout?.supports_modes}
          <label class="field">
            {t("scenes.mode")}
            <select value={s.mode} onchange={(e) => setMode(s, e.currentTarget.value)}>
              {#each MODES as m (m)}<option value={m}>{tDynamic(`scenes.mode.${m}`, m)}</option>{/each}
            </select>
          </label>
        {/if}
        <span class="spacer"></span>
        <div class="row url">
          <code class="mono">{origin}/o/{s.slug}</code>
          <button onclick={() => copy(`${origin}/o/${s.slug}`)}>{t("common.copy")}</button>
          <button onclick={() => (previewSlug = previewSlug === s.slug ? null : s.slug)}>{t("scenes.preview")}</button>
        </div>
      </div>

      <div class="slots">
        {#each state?.slots ?? [] as st (st.slot)}
          <div class="slot">
            <span class="muted small">{t("scenes.slot")} {st.slot + 1} · {st.station_id ?? "–"}</span>
            <strong>{st.name ?? "–"}</strong>
            {#if st.lives && !quali}
              <Hearts
                current={st.lives.current ?? 0}
                max={st.lives.max}
                name={st.name ?? "–"}
                disabled={busy}
                onlose={() => heart(s, st, "lose")}
                ongain={() => heart(s, st, "gain")}
              />
            {/if}
            <span class="badge {st.status === 'playing' ? 'ok' : st.status === 'finished' ? 'accent' : ''}">
              {tDynamic(`scenes.status.${st.status}`, st.status)}{st.score !== null ? ` · ${st.score.toLocaleString()}` : ""}
            </span>
            {#if st.outcome && !quali}
              <span class="badge {st.outcome === 'eliminated' ? 'bad' : 'ok'}">{tDynamic(`scenes.outcome.${st.outcome}`, st.outcome)}</span>
            {/if}
            {#if st.status === "finished" || st.status === "playing"}
              <button class="link small" onclick={() => resetSlot(s, st.slot)}>{t("scenes.reset_slot")}</button>
            {/if}
          </div>
        {/each}
      </div>

      {#if !quali}
        {#each layout?.pairs ?? [] as pair, index (index)}
          {@const bound = (state?.matches ?? []).find((p) => p.pair === index)}
          <div class="row pair">
            <span class="muted small">{t("scenes.match_for", { a: pair[0] + 1, b: pair[1] + 1 })}</span>
            <select value={bound?.match_id ?? ""} onchange={(e) => bindPair(s, index, e.currentTarget.value)}>
              <option value="">{t("scenes.match_none")}</option>
              {#each matchOptions.filter((m) => m.winner_id === null || m.match_id === bound?.match_id) as m (m.match_id)}
                <option value={m.match_id}>{matchLabel(m)}</option>
              {/each}
            </select>
            {#if bound}<span class="badge {bound.bound_by === 'manual' ? 'accent' : ''}">{bound.bound_by === "manual" ? t("scenes.match_manual") : t("scenes.match_auto")}</span>{/if}
            {#if (layout?.pairs.length ?? 0) > 1}
              <button onclick={() => newRound(s, index)}>{t("scenes.new_round_pair", { a: pair[0] + 1, b: pair[1] + 1 })}</button>
            {/if}
          </div>
        {/each}
      {/if}

      {#if previewSlug === s.slug}
        <div class="preview"><iframe src={`/o/${s.slug}?bg=dark`} title={s.name}></iframe></div>
      {/if}

      <div class="row">
        {#if !quali}
          <button class="primary" disabled={busy} onclick={() => newRound(s)}>{t("scenes.new_round")}</button>
        {:else}
          <span class="muted small">{t("regie.quali_hint")}</span>
        {/if}
        <span class="spacer"></span>
        <a class="button" href="#/studio/scene/{s.id}">{t("regie.design_scene")}</a>
      </div>
    </section>
  {:else}
    <p class="muted">{t("scenes.none")} <a href="#/studio">{t("nav.studio")} →</a></p>
  {/each}
</div>

<style>
  .head {
    margin-bottom: 8px;
  }
  .switches {
    display: flex;
    flex-wrap: wrap;
    gap: 24px;
    align-items: end;
    margin-bottom: 14px;
  }
  .list {
    display: grid;
    gap: 14px;
  }
  .scene {
    display: grid;
    gap: 10px;
  }
  .controls {
    gap: 14px;
    align-items: end;
    flex-wrap: wrap;
  }
  .url {
    gap: 8px;
    align-items: center;
  }
  .url code {
    color: var(--link);
  }
  .badge.quali {
    border-color: #3cbcfc;
    color: #3cbcfc;
  }
  .slots {
    display: grid;
    gap: 6px;
    grid-template-columns: repeat(auto-fill, minmax(230px, 1fr));
  }
  .slot {
    display: grid;
    gap: 4px;
    padding: 8px 10px;
    border: 1px solid var(--line);
    border-radius: 8px;
    justify-items: start;
  }
  .pair {
    gap: 10px;
    align-items: center;
    flex-wrap: wrap;
  }
  .pair select {
    max-width: 360px;
  }
  .preview iframe {
    width: 100%;
    aspect-ratio: 16 / 9;
    border: 1px solid var(--line);
    border-radius: 8px;
  }
</style>
