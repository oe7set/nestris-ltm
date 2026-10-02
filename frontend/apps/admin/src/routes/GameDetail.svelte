<script lang="ts">
  import { onMount } from "svelte";
  import Modal from "../components/Modal.svelte";
  import PlayerPicker from "../components/PlayerPicker.svelte";
  import { api } from "../lib/api";
  import { dateTime, duration, fromLocalInput, num, pct, toLocalInput } from "../lib/format";
  import { i18n, t, tDynamic } from "../lib/i18n.svelte";
  import { router } from "../lib/router.svelte";
  import { toasts } from "../lib/toast.svelte";
  import type { GameDetail } from "../lib/types";

  let { id }: { id: number } = $props();

  let game = $state<GameDetail | null>(null);
  let activeEvent = $state<{ id: number; name: string } | null>(null);
  let error = $state<string | null>(null);
  let editing = $state(false);
  let hiding = $state(false);
  let hideReason = $state("");
  let edit = $state({
    player_id: null as number | null,
    score: null as number | null,
    lines: null as number | null,
    start_level: null as number | null,
    end_level: null as number | null,
    started_at: "",
    notes: "",
    status: "finished",
  });

  async function load(): Promise<void> {
    try {
      game = await api<GameDetail>(`/api/games/${id}`);
      activeEvent = await api<{ id: number; name: string } | null>("/api/events/active");
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    }
  }

  function startEdit(): void {
    if (!game) return;
    edit = {
      player_id: game.player_id,
      score: game.score,
      lines: game.lines,
      start_level: game.start_level,
      end_level: game.end_level,
      started_at: toLocalInput(game.started_at),
      notes: game.notes ?? "",
      status: game.status,
    };
    editing = true;
  }

  async function save(): Promise<void> {
    try {
      await api(`/api/games/${id}`, {
        method: "PATCH",
        body: {
          ...(edit.player_id !== null ? { player_id: edit.player_id } : {}),
          score: edit.score,
          lines: edit.lines,
          start_level: edit.start_level,
          end_level: edit.end_level,
          started_at: fromLocalInput(edit.started_at),
          notes: edit.notes.trim() || null,
          status: edit.status,
        },
      });
      editing = false;
      toasts.ok(t("common.saved"));
      await load();
    } catch (e) {
      toasts.error(e);
    }
  }

  async function run(fn: () => Promise<unknown>): Promise<void> {
    try {
      await fn();
      await load();
    } catch (e) {
      toasts.error(e);
    }
  }

  async function remove(): Promise<void> {
    if (!confirm(t("game.delete_confirm", { id }))) return;
    try {
      await api(`/api/games/${id}`, { method: "DELETE" });
      toasts.ok(t("common.deleted"));
      router.go("/games");
    } catch (e) {
      toasts.error(e);
    }
  }

  onMount(() => {
    void load();
  });
</script>

<p><a href="#/games">‹ {t("games.title")}</a></p>

{#if error}
  <p class="error-box">{error}</p>
{:else if game}
  <div class="row">
    <h1>{t("game.title", { id: game.id })}</h1>
    <span class="badge {game.status === 'live' ? 'ok' : ''}">{tDynamic(`games.status.${game.status}`, game.status)}</span>
    {#if game.cheated}<span class="badge bad">{t("games.cheat", { n: game.cheated })}</span>{/if}
    {#if game.valid === false}<span class="badge bad">{t("games.invalid")}</span>{/if}
    {#if game.is_edited}<span class="badge accent">{t("games.edited")}</span>{/if}
    {#if game.hidden}<span class="badge">{t("games.hidden")}</span>{/if}
    <span class="spacer"></span>
    <button onclick={startEdit}>{t("common.edit")}</button>
    {#if activeEvent}
      {#if game.hidden}
        <button onclick={() => run(() => api(`/api/games/${id}/hidden/${activeEvent!.id}`, { method: "DELETE" }))}>{t("game.unhide")}</button>
      {:else}
        <button onclick={() => { hiding = true; hideReason = ""; }}>{t("game.hide")}</button>
      {/if}
    {/if}
    <button class="danger" onclick={remove}>{t("common.delete")}</button>
  </div>

  <div class="score">
    <span class="big">{num(game.score, i18n.locale)}</span>
    <span class="muted">
      {#if game.player_id}<a href={`#/players/${game.player_id}`}>{game.player_nickname}</a>
      {:else}<span class="badge warn">{t("games.unassigned")}</span>{/if}
    </span>
  </div>
  {#if game.hidden_in.length}
    <p class="hint">{t("game.hidden_in", { events: game.hidden_in.map((h) => h.event + (h.reason ? ` (${h.reason})` : "")).join(", ") })}</p>
  {/if}

  <div class="cols">
    <section class="panel">
      <h2>{t("game.details")}</h2>
      <dl>
        <dt>{t("games.station")}</dt><dd>{game.station_id ?? "–"}</dd>
        <dt>{t("game.started_at")}</dt><dd>{dateTime(game.started_at, i18n.locale)}</dd>
        <dt>{t("game.ended_at")}</dt><dd>{dateTime(game.ended_at, i18n.locale)}</dd>
        <dt>{t("games.duration")}</dt><dd>{duration(game.duration_s)}</dd>
        <dt>{t("game.end_reason")}</dt><dd>{game.end_reason ?? "–"}</dd>
        <dt>{t("game.source")}</dt><dd>{game.source}{game.external_id ? ` · ${game.external_id}` : ""}</dd>
        <dt>{t("game.card")}</dt><dd>{game.card_name ?? "–"} {#if game.card_uid}<span class="mono muted small">{game.card_uid}</span>{/if}</dd>
        {#if game.notes}<dt>{t("common.notes")}</dt><dd>{game.notes}</dd>{/if}
      </dl>
    </section>
    <section class="panel">
      <h2>{t("game.stats")}</h2>
      <dl>
        <dt>{t("games.lines")}</dt><dd>{num(game.lines, i18n.locale)}</dd>
        <dt>{t("games.levels")}</dt><dd>{game.start_level ?? "–"} → {game.end_level ?? "–"}</dd>
        <dt>{t("game.clears")}</dt>
        <dd>{t("game.clears_value", { s: game.clears_single ?? 0, d: game.clears_double ?? 0, t: game.clears_triple ?? 0, x: game.clears_tetris ?? 0 })}</dd>
        <dt>{t("games.trt")}</dt><dd>{pct(game.tetris_rate, i18n.locale)}</dd>
        <dt>{t("game.burn")}</dt><dd>{num(game.burn, i18n.locale)}</dd>
        <dt>{t("game.drought")}</dt><dd>{num(game.max_drought, i18n.locale)}</dd>
        <dt>{t("game.pieces")}</dt><dd>{num(game.pieces, i18n.locale)}</dd>
        <dt>{t("game.pps")}</dt><dd>{game.pps?.toFixed(2) ?? "–"}</dd>
      </dl>
    </section>
    <section class="panel">
      <h2>{t("game.validation")}</h2>
      {#if game.valid !== null}
        <p><span class="badge {game.valid ? 'ok' : 'bad'}">{game.valid ? t("game.valid") : t("games.invalid")}</span></p>
      {/if}
      {#each game.validation?.issues ?? [] as issue (issue.code + issue.detail)}
        <div class="issue">
          <span class="badge {issue.severity === 'error' ? 'bad' : 'warn'}">{issue.code}</span>
          <span class="small">{issue.detail}</span>
        </div>
      {:else}
        <p class="muted small">{t("game.no_issues")}</p>
      {/each}
      {#if game.cheats.length}
        <h2 class="sub">{t("game.cheats")}</h2>
        {#each game.cheats as c (c.id)}
          <div class="small">
            {dateTime(c.ts, i18n.locale)} · +{num(c.points, i18n.locale)} ({num(c.score_before, i18n.locale)} → {num(c.score_after, i18n.locale)})
          </div>
        {/each}
      {/if}
      <h2 class="sub">{t("game.recording")}</h2>
      <p class="small muted">{t("game.frames", { n: num(game.frame_count, i18n.locale) })}</p>
      <p class="small muted">{game.recording ? `${num(game.recording.size_bytes, i18n.locale)} B` : t("game.no_recording")}</p>
    </section>
  </div>
{:else}
  <p class="muted">{t("common.loading")}</p>
{/if}

{#if editing && game}
  <Modal title={`${t("common.edit")}: ${t("game.title", { id: game.id })}`} onclose={() => (editing = false)}>
    <p class="hint">{t("game.edit_hint")}</p>
    <div class="field-like">
      <span class="muted small">{t("games.player")}</span>
      <PlayerPicker value={edit.player_id} initialLabel={game.player_nickname} onselect={(p) => (edit.player_id = p.id)} />
      {#if game.player_id}
        <button class="link small" onclick={() => run(() => api(`/api/games/${id}/unassign`, { method: "POST" })).then(() => (editing = false))}>
          {t("game.unassign")}
        </button>
      {/if}
    </div>
    <div class="form-grid">
      <label class="field">{t("games.score")}<input type="number" min="0" bind:value={edit.score} /></label>
      <label class="field">{t("games.lines")}<input type="number" min="0" bind:value={edit.lines} /></label>
      <label class="field">{t("game.start_level")}<input type="number" min="0" max="29" bind:value={edit.start_level} /></label>
      <label class="field">{t("game.end_level")}<input type="number" min="0" bind:value={edit.end_level} /></label>
      <label class="field">{t("game.started_at")}<input type="datetime-local" bind:value={edit.started_at} /></label>
      <label class="field">{t("games.status")}
        <select bind:value={edit.status}>
          {#each ["live", "finished", "abandoned"] as s (s)}<option value={s}>{tDynamic(`games.status.${s}`, s)}</option>{/each}
        </select>
      </label>
    </div>
    <label class="field">{t("common.notes")}<textarea bind:value={edit.notes}></textarea></label>
    {#snippet footer()}
      <button onclick={() => (editing = false)}>{t("common.cancel")}</button>
      <button class="primary" onclick={save}>{t("common.save")}</button>
    {/snippet}
  </Modal>
{/if}

{#if hiding && activeEvent}
  <Modal title={t("game.hide")} onclose={() => (hiding = false)}>
    <label class="field">{t("game.hide_reason")}<input bind:value={hideReason} maxlength="255" /></label>
    {#snippet footer()}
      <button onclick={() => (hiding = false)}>{t("common.cancel")}</button>
      <button
        class="primary"
        onclick={() =>
          run(() =>
            api(`/api/games/${id}/hidden/${activeEvent!.id}`, { method: "PUT", body: { reason: hideReason.trim() || null } }),
          ).then(() => (hiding = false))}
      >
        {t("game.hide")}
      </button>
    {/snippet}
  </Modal>
{/if}

<style>
  .score {
    display: flex;
    align-items: baseline;
    gap: 14px;
    margin: 4px 0 16px;
  }
  .big {
    font-size: 34px;
    font-weight: 700;
    color: var(--accent);
    font-variant-numeric: tabular-nums;
  }
  .cols {
    display: grid;
    gap: 16px;
    grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
    align-items: start;
  }
  dl {
    display: grid;
    grid-template-columns: auto 1fr;
    gap: 6px 14px;
    margin: 0;
  }
  dt {
    color: var(--muted);
  }
  dd {
    margin: 0;
  }
  .issue {
    display: flex;
    gap: 8px;
    align-items: baseline;
    margin-bottom: 6px;
  }
  h2.sub {
    margin-top: 14px;
  }
  .field-like {
    display: grid;
    gap: 4px;
    justify-items: start;
  }
</style>
