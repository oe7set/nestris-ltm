<script lang="ts">
  import { onMount } from "svelte";
  import Pager from "../components/Pager.svelte";
  import { api } from "../lib/api";
  import { dateTime, duration, num, pct } from "../lib/format";
  import { i18n, t, tDynamic } from "../lib/i18n.svelte";
  import { router } from "../lib/router.svelte";
  import { toasts } from "../lib/toast.svelte";
  import type { Game, Page, StationRow } from "../lib/types";

  const LIMIT = 50;
  const query = router.current.query;
  let allTime = $state(query.get("all") === "true");
  let station = $state(query.get("station") ?? "");
  let status = $state(query.get("status") ?? "");
  let unassigned = $state(query.get("unassigned") === "true");
  let flagged = $state(query.get("flagged") === "true");
  let hidden = $state(query.get("hidden") ?? "");
  let sort = $state(query.get("sort") ?? "started_at");
  let q = $state(query.get("q") ?? "");
  let offset = $state(Number(query.get("offset") ?? 0));
  let page = $state<Page<Game> | null>(null);
  let stations = $state<StationRow[]>([]);
  let timer: ReturnType<typeof setTimeout> | undefined;

  async function load(): Promise<void> {
    router.setQuery({
      all: allTime, station, status, unassigned, flagged, hidden, q,
      sort: sort === "started_at" ? null : sort, offset: offset || null,
    });
    try {
      page = await api<Page<Game>>("/api/games", {
        query: {
          all_time: allTime, station_id: station, status, unassigned, flagged,
          hidden: hidden === "" ? null : hidden === "hidden", q, sort, limit: LIMIT, offset,
        },
      });
    } catch (e) {
      toasts.error(e);
    }
  }

  function reload(): void {
    offset = 0;
    void load();
  }

  function searchSoon(): void {
    clearTimeout(timer);
    timer = setTimeout(reload, 250);
  }

  onMount(() => {
    void load();
    api<StationRow[]>("/api/stations").then((s) => (stations = s)).catch(() => {});
  });
</script>

<div class="row">
  <h1>{t("games.title")}</h1>
  <span class="spacer"></span>
  <a class="button primary" href="#/games/new">+ {t("games.new")}</a>
</div>

<div class="row filters">
  <select bind:value={allTime} onchange={reload}>
    <option value={false}>{page?.event ? t("games.scope_event", { event: page.event.name }) : t("games.scope_all")}</option>
    <option value={true}>{t("games.all_time")}</option>
  </select>
  <select bind:value={station} onchange={reload} aria-label={t("games.station")}>
    <option value="">{t("games.station")}: {t("common.all")}</option>
    {#each stations as s (s.id)}<option value={s.id}>{s.name ?? s.id}</option>{/each}
  </select>
  <select bind:value={status} onchange={reload} aria-label={t("games.status")}>
    <option value="">{t("games.status")}: {t("common.all")}</option>
    {#each ["live", "finished", "abandoned"] as s (s)}<option value={s}>{tDynamic(`games.status.${s}`, s)}</option>{/each}
  </select>
  <select bind:value={hidden} onchange={reload} aria-label={t("games.visibility")} disabled={allTime}>
    <option value="">{t("games.visibility")}: {t("common.all")}</option>
    <option value="visible">{t("games.visible")}</option>
    <option value="hidden">{t("games.hidden")}</option>
  </select>
  <select bind:value={sort} onchange={reload} aria-label={t("games.sort")}>
    <option value="started_at">{t("games.sort_time")}</option>
    <option value="score">{t("games.sort_score")}</option>
  </select>
  <label class="check"><input type="checkbox" bind:checked={unassigned} onchange={reload} /> {t("games.unassigned")}</label>
  <label class="check"><input type="checkbox" bind:checked={flagged} onchange={reload} /> {t("games.flagged")}</label>
  <input type="search" placeholder={t("games.q")} bind:value={q} oninput={searchSoon} />
</div>

<div class="table-wrap">
  <table>
    <thead>
      <tr>
        <th>{t("games.started")}</th>
        <th>{t("games.player")}</th>
        <th>{t("games.station")}</th>
        <th class="num">{t("games.score")}</th>
        <th class="num">{t("games.lines")}</th>
        <th class="num">{t("games.levels")}</th>
        <th class="num">{t("games.trt")}</th>
        <th class="num">{t("games.duration")}</th>
        <th></th>
      </tr>
    </thead>
    <tbody>
      {#each page?.items ?? [] as g (g.id)}
        <tr class="clickable" class:dim={g.hidden} onclick={() => router.go(`/games/${g.id}`)}>
          <td>{dateTime(g.started_at, i18n.locale)}</td>
          <td>
            {#if g.player_nickname}{g.player_nickname}
            {:else}<span class="badge warn">{t("games.unassigned")}</span>
              {#if g.card_name}<span class="muted small">„{g.card_name}“</span>{/if}
            {/if}
          </td>
          <td>{g.station_id ?? "–"}</td>
          <td class="num"><strong>{num(g.score ?? g.live?.score, i18n.locale)}</strong></td>
          <td class="num">{num(g.lines ?? g.live?.lines, i18n.locale)}</td>
          <td class="num">{g.start_level ?? "–"} → {g.end_level ?? "–"}</td>
          <td class="num">{pct(g.tetris_rate, i18n.locale)}</td>
          <td class="num">{duration(g.duration_s)}</td>
          <td><div class="badges">
            {#if g.status !== "finished"}<span class="badge {g.status === 'live' ? 'ok' : ''}">{tDynamic(`games.status.${g.status}`, g.status)}</span>{/if}
            {#if g.cheated}<span class="badge bad">{t("games.cheat", { n: g.cheated })}</span>{/if}
            {#if g.valid === false}<span class="badge bad">{t("games.invalid")}</span>{/if}
            {#if g.is_edited}<span class="badge accent">{t("games.edited")}</span>{/if}
            {#if g.source === "manual"}<span class="badge">{t("games.manual")}</span>{/if}
            {#if g.hidden}<span class="badge">{t("games.hidden")}</span>{/if}
          </div></td>
        </tr>
      {:else}
        <tr><td colspan="9" class="empty">{page ? t("games.none") : t("common.loading")}</td></tr>
      {/each}
    </tbody>
  </table>
</div>
{#if page}
  <Pager total={page.total} limit={LIMIT} {offset} onchange={(o) => { offset = o; void load(); }} />
{/if}

<style>
  .filters {
    margin-bottom: 12px;
  }
  .filters input[type="search"] {
    width: min(240px, 100%);
  }
  .badges {
    display: flex;
    gap: 4px;
    flex-wrap: wrap;
  }
  tr.dim td {
    opacity: 0.55;
  }
</style>
