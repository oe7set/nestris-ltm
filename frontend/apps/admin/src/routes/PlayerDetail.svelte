<script lang="ts">
  import { onMount } from "svelte";
  import Modal from "../components/Modal.svelte";
  import PlayerPicker from "../components/PlayerPicker.svelte";
  import { api } from "../lib/api";
  import { dateTime, num } from "../lib/format";
  import { i18n, t, type MessageKey } from "../lib/i18n.svelte";
  import { router } from "../lib/router.svelte";
  import { toasts } from "../lib/toast.svelte";
  import type { Game, Page, PlayerDetail } from "../lib/types";

  let { id }: { id: number } = $props();

  const FIELDS: { key: keyof PlayerDetail; label: MessageKey; type?: string }[] = [
    { key: "nickname", label: "players.nickname" },
    { key: "first_name", label: "player.first_name" },
    { key: "last_name", label: "player.last_name" },
    { key: "birth_date", label: "player.birth_date", type: "date" },
    { key: "email", label: "player.email", type: "email" },
    { key: "phone", label: "player.phone", type: "tel" },
    { key: "street", label: "player.street" },
    { key: "postal_code", label: "player.postal_code" },
    { key: "city", label: "player.city" },
    { key: "country", label: "player.country" },
  ];

  let player = $state<PlayerDetail | null>(null);
  let form = $state<Record<string, string>>({});
  let games = $state<Game[]>([]);
  let newCard = $state("");
  let merging = $state(false);
  let mergeTarget = $state<number | null>(null);
  let error = $state<string | null>(null);

  async function load(): Promise<void> {
    try {
      player = await api<PlayerDetail>(`/api/players/${id}`);
      form = Object.fromEntries(
        [...FIELDS.map((f) => f.key), "notes"].map((k) => [k, String(player![k as keyof PlayerDetail] ?? "")]),
      );
      const page = await api<Page<Game>>("/api/games", {
        query: { player_id: id, all_time: true, limit: 20 },
      });
      games = page.items;
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    }
  }

  async function save(event: SubmitEvent): Promise<void> {
    event.preventDefault();
    const body: Record<string, string | null> = {};
    for (const [key, value] of Object.entries(form)) body[key] = value.trim() === "" ? null : value.trim();
    if (!body.nickname) return;
    try {
      await api(`/api/players/${id}`, { method: "PATCH", body });
      toasts.ok(t("common.saved"));
      await load();
    } catch (e) {
      toasts.error(e);
    }
  }

  async function action(fn: () => Promise<unknown>, message?: string): Promise<void> {
    try {
      await fn();
      if (message) toasts.ok(message);
      await load();
    } catch (e) {
      toasts.error(e);
    }
  }

  async function setFlags(hideEverywhere: boolean, hideBracket: boolean): Promise<void> {
    if (!player?.event) return;
    await action(() =>
      api(`/api/players/${id}/flags/${player!.event!.id}`, {
        method: "PUT",
        body: { hide_everywhere: hideEverywhere, hide_from_bracket: hideBracket },
      }),
    );
  }

  async function addCard(event: SubmitEvent): Promise<void> {
    event.preventDefault();
    await action(() => api(`/api/players/${id}/cards`, { method: "POST", body: { uid: newCard.trim() } }));
    newCard = "";
  }

  async function remove(): Promise<void> {
    if (!player || !confirm(t("player.delete_confirm", { name: player.nickname }))) return;
    await action(() => api(`/api/players/${id}`, { method: "DELETE" }), t("common.deleted"));
  }

  async function merge(): Promise<void> {
    if (mergeTarget === null) return;
    try {
      const r = await api<{ games: number; cards: number }>(`/api/players/${id}/merge`, {
        method: "POST",
        body: { into_id: mergeTarget },
      });
      toasts.ok(t("player.merged", r));
      router.go(`/players/${mergeTarget}`);
    } catch (e) {
      toasts.error(e);
    }
  }

  // onMount, not $effect: load() reads state that must not re-trigger it.
  onMount(() => {
    void load();
  });
</script>

<p><a href="#/players">‹ {t("players.title")}</a></p>

{#if error}
  <p class="error-box">{error}</p>
{:else if player}
  <div class="row">
    <h1>{player.nickname}</h1>
    {#if player.auto_created}<span class="badge warn">{t("players.auto")}</span>{/if}
    {#if player.deleted_at}<span class="badge bad">{t("players.deleted")}</span>{/if}
    <span class="spacer"></span>
    {#if player.auto_created}
      <button onclick={() => action(() => api(`/api/players/${id}`, { method: "PATCH", body: { auto_created: false } }))}>
        ✓ {t("player.mark_checked")}
      </button>
    {/if}
    <button onclick={() => { merging = true; mergeTarget = null; }}>{t("player.merge")}</button>
    {#if player.deleted_at}
      <button onclick={() => action(() => api(`/api/players/${id}/restore`, { method: "POST" }))}>{t("player.restore")}</button>
    {:else}
      <button class="danger" onclick={remove}>{t("common.delete")}</button>
    {/if}
  </div>
  <p class="hint">
    {t("player.stats", {
      games: num(player.games_total, i18n.locale),
      best: num(player.best_score, i18n.locale),
      best_event: num(player.best_score_event, i18n.locale),
    })}
  </p>

  <div class="layout">
    <form class="panel grid" onsubmit={save}>
      <div class="form-grid">
        {#each FIELDS as f (f.key)}
          <label class="field">
            {t(f.label)}
            <input type={f.type ?? "text"} bind:value={form[f.key]} required={f.key === "nickname"} />
          </label>
        {/each}
      </div>
      <label class="field">
        {t("common.notes")}
        <textarea bind:value={form.notes}></textarea>
      </label>
      <div class="row"><span class="spacer"></span><button class="primary" type="submit">{t("common.save")}</button></div>
    </form>

    <div class="grid side">
      <section class="panel">
        <h2>{t("player.cards")}</h2>
        {#each player.cards as card (card.uid)}
          <div class="row card">
            <span class="mono">{card.uid}</span>
            {#if card.card_name}<span class="muted small">„{card.card_name}“</span>{/if}
            <span class="spacer"></span>
            <button class="link small" onclick={() => action(() => api(`/api/players/${id}/cards/${card.uid}`, { method: "DELETE" }))}>✕</button>
          </div>
          <div class="muted small">
            {t("player.last_seen")}: {dateTime(card.last_seen_at, i18n.locale)}
          </div>
        {:else}
          <p class="muted small">{t("player.no_cards")}</p>
        {/each}
        <form class="row add" onsubmit={addCard}>
          <input placeholder={t("player.card_uid")} bind:value={newCard} pattern="[0-9A-Fa-f]+" maxlength="32" required />
          <button type="submit">{t("player.add_card")}</button>
        </form>
      </section>

      <section class="panel">
        {#if player.event}
          <h2>{t("player.visibility", { event: player.event.name })}</h2>
          <label class="check">
            <input
              type="checkbox"
              checked={player.hide_everywhere}
              onchange={(e) => setFlags(e.currentTarget.checked, player!.hide_from_bracket ?? false)}
            />
            {t("player.hide_everywhere")}
          </label>
          <label class="check">
            <input
              type="checkbox"
              checked={player.hide_from_bracket}
              disabled={player.hide_everywhere}
              onchange={(e) => setFlags(player!.hide_everywhere ?? false, e.currentTarget.checked)}
            />
            {t("player.hide_bracket")}
          </label>
        {:else}
          <p class="muted small">{t("player.no_event")}</p>
        {/if}
      </section>
    </div>
  </div>

  <h2 class="games-head">{t("player.games")}</h2>
  <div class="table-wrap">
    <table class="table-cards">
      <thead>
        <tr>
          <th>{t("games.started")}</th>
          <th>{t("games.station")}</th>
          <th class="num">{t("games.score")}</th>
          <th class="num">{t("games.lines")}</th>
          <th class="num">{t("games.levels")}</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        {#each games as g (g.id)}
          <tr class="clickable" onclick={() => router.go(`/games/${g.id}`)}>
            <td class="card-title" data-label={t("games.started")}>{dateTime(g.started_at, i18n.locale)}</td>
            <td data-label={t("games.station")}>{g.station_id ?? "–"}</td>
            <td class="num card-score" data-label={t("games.score")}><strong>{num(g.score, i18n.locale)}</strong></td>
            <td class="num" data-label={t("games.lines")}>{num(g.lines, i18n.locale)}</td>
            <td class="num" data-label={t("games.levels")}>{g.start_level ?? "–"} → {g.end_level ?? "–"}</td>
            <td class="card-badges">{#if g.flagged}<span class="badge bad">!</span>{/if}</td>
          </tr>
        {:else}
          <tr><td colspan="6" class="empty">{t("games.none")}</td></tr>
        {/each}
      </tbody>
    </table>
  </div>
{:else}
  <p class="muted">{t("common.loading")}</p>
{/if}

{#if merging && player}
  <Modal title={t("player.merge")} onclose={() => (merging = false)}>
    <p class="hint">{t("player.merge_hint")}</p>
    <div class="muted small">{t("player.merge_into")}</div>
    <PlayerPicker value={mergeTarget} excludeId={id} onselect={(p) => (mergeTarget = p.id)} />
    {#snippet footer()}
      <button onclick={() => (merging = false)}>{t("common.cancel")}</button>
      <button class="primary" disabled={mergeTarget === null} onclick={merge}>{t("player.merge")}</button>
    {/snippet}
  </Modal>
{/if}

<style>
  .layout {
    display: grid;
    gap: 16px;
    grid-template-columns: 2fr minmax(260px, 1fr);
    align-items: start;
  }
  .side {
    gap: 16px;
  }
  .side section {
    display: grid;
    gap: 6px;
  }
  .card {
    margin-top: 4px;
  }
  .add {
    margin-top: 8px;
  }
  .add input {
    flex: 1;
  }
  .games-head {
    margin-top: 22px;
  }
  @media (max-width: 900px) {
    .layout {
      grid-template-columns: 1fr;
    }
  }
</style>
