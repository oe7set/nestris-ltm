<script lang="ts">
  // Hearts of the 1-vs-1 matches of the fixed bracket (Turnier → Matches &
  // Herzen): take/give hearts, hearts per match, which scene pair shows the
  // match, history with undo. The defaults live in Einstellungen.
  import { onMount } from "svelte";
  import { api } from "../lib/api";
  import { dateTime } from "../lib/format";
  import { i18n, t } from "../lib/i18n.svelte";
  import { toasts } from "../lib/toast.svelte";

  interface MatchPlayer {
    id: number;
    nickname: string;
    seed: number | null;
    lives: number;
  }
  interface LifeEvent {
    id: number;
    player_id: number;
    kind: "lose" | "gain" | "set";
    value: number | null;
    source: string;
    actor: string | null;
    created_at: string;
    undone: boolean;
  }
  interface MatchRow {
    match_id: string;
    round: number;
    round_name: string;
    max_lives: number;
    custom_max: boolean;
    players: MatchPlayer[];
    winner_id: number | null;
    decided_by_lives: boolean;
    events: LifeEvent[];
    bound: { scene_id: number; pair: number; bound_by: string }[];
  }
  interface LivesState {
    seeded: boolean;
    settings: { default_lives: number; auto_bind: boolean; auto_deduct: boolean };
    matches: MatchRow[];
  }
  interface SceneRow {
    id: number;
    name: string;
  }

  let info = $state<LivesState | null>(null);
  let scenes = $state<SceneRow[]>([]);
  let busy = $state(false);
  let history = $state<string | null>(null);

  async function load(): Promise<void> {
    try {
      info = await api<LivesState>("/api/tournament/matches");
    } catch (e) {
      toasts.error(e);
    }
  }

  async function act(fn: () => Promise<unknown>): Promise<void> {
    if (busy) return;
    busy = true;
    try {
      await fn();
    } catch (e) {
      toasts.error(e);
    } finally {
      busy = false;
      await load();
    }
  }

  const change = (m: MatchRow, p: MatchPlayer, action: "lose" | "gain") =>
    act(() => api(`/api/tournament/matches/${m.match_id}/lives`, { method: "POST", body: { player_id: p.id, action } }));
  const setMax = (m: MatchRow, value: string) =>
    act(() =>
      api(`/api/tournament/matches/${m.match_id}/max-lives`, {
        method: "PUT",
        body: { max_lives: value === "" ? null : Number(value) },
      }),
    );
  const undo = (e: LifeEvent) => act(() => api(`/api/tournament/lives/undo/${e.id}`, { method: "POST" }));

  function name(m: MatchRow, id: number): string {
    return m.players.find((p) => p.id === id)?.nickname ?? String(id);
  }

  function eventText(m: MatchRow, e: LifeEvent): string {
    const who = name(m, e.player_id);
    if (e.kind === "set") return t("matches.ev_set", { player: who, n: e.value ?? 0 });
    return t(e.kind === "lose" ? "matches.ev_lose" : "matches.ev_gain", { player: who });
  }

  function sceneName(id: number): string {
    return scenes.find((s) => s.id === id)?.name ?? `#${id}`;
  }

  onMount(() => {
    void load();
    void api<SceneRow[]>("/api/scenes").then((s) => (scenes = s)).catch(() => {});
    const timer = setInterval(() => void load(), 3000);
    return () => clearInterval(timer);
  });
</script>

<p class="hint">
  {t("matches.intro")}
  <a href="#/settings?tab=tournament">{t("nav.settings")} →</a>
</p>

{#if info}
  {#if !info.seeded}
    <p class="info-box">{t("matches.not_seeded")}</p>
  {:else if info.matches.length === 0}
    <p class="muted">{t("matches.none")}</p>
  {:else}
    <div class="grid">
      {#each info.matches as m (m.match_id)}
        <section class="panel match" class:done={m.winner_id !== null}>
          <div class="row head">
            <strong>{m.round_name}</strong>
            <span class="muted small mono">{m.match_id}</span>
            <span class="spacer"></span>
            {#each m.bound as b (`${b.scene_id}-${b.pair}`)}
              <span class="badge accent">{sceneName(b.scene_id)}{b.pair > 0 ? ` · ${t("matches.pair")} ${b.pair + 1}` : ""}{b.bound_by === "auto" ? " (auto)" : ""}</span>
            {/each}
          </div>
          {#each m.players as p (p.id)}
            <div class="player row" class:winner={m.winner_id === p.id} class:loser={m.winner_id !== null && m.winner_id !== p.id}>
              <span class="nick">{#if p.seed}<span class="muted small">#{p.seed}</span> {/if}{p.nickname}</span>
              <span class="hearts" aria-label="{p.lives}/{m.max_lives}">
                {#each Array.from({ length: m.max_lives }, (_, i) => i) as i (i)}
                  <span class="heart" class:empty={i >= p.lives}>♥</span>
                {/each}
              </span>
              <button disabled={busy || p.lives <= 0} onclick={() => change(m, p, "lose")} title={t("matches.lose")}>−</button>
              <button disabled={busy || p.lives >= m.max_lives} onclick={() => change(m, p, "gain")} title={t("matches.gain")}>+</button>
            </div>
          {/each}
          <div class="row foot">
            {#if m.winner_id !== null}
              <span class="badge ok">{t("matches.winner", { player: name(m, m.winner_id) })}{m.decided_by_lives ? "" : ` (${t("matches.manual")})`}</span>
            {/if}
            <span class="spacer"></span>
            <label class="small">
              {t("matches.hearts")}
              <select value={m.custom_max ? String(m.max_lives) : ""} onchange={(e) => setMax(m, e.currentTarget.value)}>
                <option value="">{t("matches.default")} ({info.settings.default_lives})</option>
                {#each [1, 2, 3, 4, 5] as n (n)}<option value={String(n)}>{n}</option>{/each}
              </select>
            </label>
            {#if m.events.length}
              <button class="link small" onclick={() => (history = history === m.match_id ? null : m.match_id)}>
                {t("matches.history")} ({m.events.filter((e) => !e.undone).length})
              </button>
            {/if}
          </div>
          {#if history === m.match_id}
            <ul class="events">
              {#each [...m.events].reverse() as e (e.id)}
                <li class:undone={e.undone}>
                  <span class="muted small">{dateTime(e.created_at, i18n.locale)}</span>
                  {eventText(m, e)}
                  <span class="muted small">· {e.actor ?? e.source}</span>
                  {#if !e.undone}<button class="link small" disabled={busy} onclick={() => undo(e)}>{t("matches.undo")}</button>{/if}
                </li>
              {/each}
            </ul>
          {/if}
        </section>
      {/each}
    </div>
  {/if}
{/if}

<style>
  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(380px, 1fr));
    gap: 14px;
  }
  .match {
    display: grid;
    gap: 8px;
  }
  .match.done {
    opacity: 0.75;
  }
  .player {
    gap: 10px;
    align-items: center;
  }
  .player .nick {
    flex: 1;
    font-weight: 600;
  }
  .player.winner .nick {
    color: var(--ok, #4c4);
  }
  .player.loser .nick {
    text-decoration: line-through;
    opacity: 0.6;
  }
  .player button {
    width: 36px;
    padding: 2px 0;
    font-size: 18px;
  }
  .hearts {
    display: flex;
    gap: 3px;
    font-size: 22px;
    line-height: 1;
  }
  .heart {
    color: #e5343a;
    text-shadow: 0 0 1px #000;
  }
  .heart.empty {
    color: transparent;
    -webkit-text-stroke: 1.5px #777;
  }
  .events {
    margin: 0;
    padding-left: 18px;
    font-size: 13px;
  }
  .events li.undone {
    text-decoration: line-through;
    opacity: 0.55;
  }
</style>
