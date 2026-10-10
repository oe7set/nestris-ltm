<script lang="ts">
  import ErrorBox from "../components/ErrorBox.svelte";
  import { onMount } from "svelte";
  import BulkBar from "../components/BulkBar.svelte";
  import Modal from "../components/Modal.svelte";
  import Pager from "../components/Pager.svelte";
  import PlayerPicker from "../components/PlayerPicker.svelte";
  import { api } from "../lib/api";
  import { dateTime, duration, num, pct } from "../lib/format";
  import { format, i18n, t, tDynamic } from "../lib/i18n.svelte";
  import { router } from "../lib/router.svelte";
  import { Selection } from "../lib/selection.svelte";
  import { errorText, toasts } from "../lib/toast.svelte";
  import type { Game, Page, StationRow } from "../lib/types";

  type BulkAction = "delete" | "hide" | "unhide" | "assign" | "unassign";

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
  let importing = $state(false);
  let importFile = $state<File | null>(null);
  let importPlayer = $state<number | null>(null);
  let importBusy = $state(false);
  // Phones: the filters fold away behind a button (the search stays).
  let filtersOpen = $state(false);

  const selection = new Selection<Game>();
  let confirmDelete = $state(false);
  let assigning = $state(false);
  let assignPlayer = $state<number | null>(null);
  let bulkBusy = $state(false);
  let pageBox = $state<HTMLInputElement>();

  const rows = $derived(page?.items ?? []);
  const pageState = $derived(selection.pageState(rows));
  const activeFilters = $derived(
    [allTime, station !== "", status !== "", hidden !== "", sort !== "started_at", unassigned, flagged].filter(
      Boolean,
    ).length,
  );

  $effect(() => {
    if (pageBox) pageBox.indeterminate = pageState === "some";
  });

  async function runImport(): Promise<void> {
    if (!importFile) return;
    importBusy = true;
    try {
      const params = new URLSearchParams();
      if (importPlayer !== null) params.set("player_id", String(importPlayer));
      const response = await fetch(`/api/games/import?${params}`, {
        method: "POST",
        body: await importFile.arrayBuffer(),
        headers: { "Content-Type": "application/octet-stream" },
      });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(typeof body.detail === "string" ? body.detail : response.statusText);
      toasts.ok(t("games.imported", { n: body.games.length }));
      importing = false;
      importFile = null;
      importPlayer = null;
      await load();
    } catch (e) {
      toasts.error(e);
    } finally {
      importBusy = false;
    }
  }

  let loadError = $state<string | null>(null);

  async function load(): Promise<void> {
    router.setQuery({
      all: allTime, station, status, unassigned, flagged, hidden, q,
      sort: sort === "started_at" ? null : sort, offset: offset || null,
    });
    try {
      loadError = null;
      page = await api<Page<Game>>("/api/games", {
        query: {
          all_time: allTime, station_id: station, status, unassigned, flagged,
          hidden: hidden === "" ? null : hidden === "hidden", q, sort, limit: LIMIT, offset,
        },
      });
    } catch (e) {
      loadError = errorText(e);
    }
  }

  function reload(): void {
    offset = 0;
    // Other filters show other games: a selection made before would be invisible.
    selection.clear();
    void load();
  }

  function searchSoon(): void {
    clearTimeout(timer);
    timer = setTimeout(reload, 250);
  }

  function toggleRow(g: Game): void {
    if (!selection.toggle(g)) toasts.error(t("bulk.limit", { max: selection.max }));
  }

  function togglePage(): void {
    selection.setMany(rows, pageState !== "all");
  }

  async function bulk(action: BulkAction, extra: Record<string, unknown> = {}): Promise<void> {
    bulkBusy = true;
    const ids = selection.ids;
    try {
      const res = await api<{ affected: number }>("/api/games/bulk", {
        method: "POST",
        body: { ids, action, ...extra },
      });
      toasts.ok(format(tDynamic(`bulk.done.${action}`, action), { n: res.affected }));
      if (action === "delete") selection.forget(ids);
      else selection.clear();
      confirmDelete = false;
      assigning = false;
      assignPlayer = null;
      await load();
    } catch (e) {
      toasts.error(e);
    } finally {
      bulkBusy = false;
    }
  }

  function label(g: Game): string {
    const who = g.player_nickname ?? g.card_name ?? t("games.unassigned");
    return `${dateTime(g.started_at, i18n.locale)} · ${who} · ${num(g.score, i18n.locale)}`;
  }

  onMount(() => {
    void load();
    api<StationRow[]>("/api/stations").then((s) => (stations = s)).catch(() => {});
  });
</script>

<div class="row head">
  <h1>{t("games.title")}</h1>
  <span class="spacer"></span>
  <button onclick={() => (importing = true)}>{t("games.import")}</button>
  <a class="button primary" href="#/games/new">+ {t("games.new")}</a>
</div>

{#if importing}
  <Modal title={t("games.import")} onclose={() => (importing = false)}>
    <p class="hint">{t("games.import_hint")}</p>
    <label class="field">
      {t("games.import_file")}
      <input type="file" accept=".ngf,.gz" onchange={(e) => (importFile = e.currentTarget.files?.[0] ?? null)} />
    </label>
    <div class="field-like">
      <span class="muted small">{t("games.import_player")}</span>
      <PlayerPicker value={importPlayer} onselect={(p) => (importPlayer = p.id)} />
    </div>
    {#snippet footer()}
      <button onclick={() => (importing = false)}>{t("common.cancel")}</button>
      <button class="primary" disabled={!importFile || importBusy} onclick={runImport}>{t("games.import")}</button>
    {/snippet}
  </Modal>
{/if}

<div class="row searchbar">
  <input type="search" placeholder={t("games.q")} bind:value={q} oninput={searchSoon} />
  <button class="filter-toggle" aria-expanded={filtersOpen} onclick={() => (filtersOpen = !filtersOpen)}>
    {activeFilters ? t("list.filters_n", { n: activeFilters }) : t("list.filters")}
  </button>
</div>

<div class="row filters" class:open={filtersOpen}>
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
</div>

{#if loadError}<ErrorBox text={loadError} onretry={() => void load()} />{/if}
<div class="table-wrap">
  <table class="table-cards">
    <thead>
      <tr>
        <th class="sel">
          <input
            type="checkbox"
            bind:this={pageBox}
            checked={pageState === "all"}
            disabled={!rows.length}
            onchange={togglePage}
            aria-label={t("bulk.select_page")}
            title={t("bulk.select_page")}
          />
        </th>
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
      {#each rows as g (g.id)}
        <tr
          class="clickable"
          class:dim={g.hidden}
          class:selected={selection.has(g.id)}
          onclick={() => router.go(`/games/${g.id}`)}
        >
          <td class="sel" onclick={(e) => e.stopPropagation()}>
            <input
              type="checkbox"
              checked={selection.has(g.id)}
              onchange={() => toggleRow(g)}
              aria-label={`${t("bulk.select_row")}: ${label(g)}`}
            />
          </td>
          <td class="card-sub" data-label={t("games.started")}>{dateTime(g.started_at, i18n.locale)}</td>
          <td class="card-title" data-label={t("games.player")}>
            {#if g.player_nickname}{g.player_nickname}
            {:else}<span class="badge warn">{t("games.unassigned")}</span>
              {#if g.card_name}<span class="muted small">„{g.card_name}“</span>{/if}
            {/if}
          </td>
          <td data-label={t("games.station")}>{g.station_id ?? "–"}</td>
          <td class="num card-score" data-label={t("games.score")}><strong>{num(g.score ?? g.live?.score, i18n.locale)}</strong></td>
          <td class="num" data-label={t("games.lines")}>{num(g.lines ?? g.live?.lines, i18n.locale)}</td>
          <td class="num" data-label={t("games.levels")}>{g.start_level ?? "–"} → {g.end_level ?? "–"}</td>
          <td class="num hide-sm" data-label={t("games.trt")}>{pct(g.tetris_rate, i18n.locale)}</td>
          <td class="num hide-sm" data-label={t("games.duration")}>{duration(g.duration_s)}</td>
          <td class="card-badges"><div class="badges">
            {#if g.status !== "finished"}<span class="badge {g.status === 'live' ? 'ok' : ''}">{tDynamic(`games.status.${g.status}`, g.status)}</span>{/if}
            {#if g.cheated}<span class="badge bad">{t("games.cheat", { n: g.cheated })}</span>{/if}
            {#if g.valid === false}<span class="badge bad">{t("games.invalid")}</span>{/if}
            {#if g.is_edited}<span class="badge accent">{t("games.edited")}</span>{/if}
            {#if g.source === "manual"}<span class="badge">{t("games.manual")}</span>{/if}
            {#if g.source === "self_reported"}<span class="badge warn">{t("games.self_reported")}</span>{/if}
            {#if g.hidden}<span class="badge">{t("games.hidden")}</span>{/if}
          </div></td>
        </tr>
      {:else}
        <tr><td colspan="10" class="empty">{page ? t("games.none") : loadError ? "–" : t("common.loading")}</td></tr>
      {/each}
    </tbody>
  </table>
</div>
{#if page}
  <Pager total={page.total} limit={LIMIT} {offset} onchange={(o) => { offset = o; void load(); }} />
{/if}

<BulkBar count={selection.size} onclear={() => selection.clear()}>
  {#if page?.event}
    <button disabled={bulkBusy} onclick={() => bulk("hide")} title={t("bulk.hide_hint", { event: page.event.name })}>{t("bulk.hide")}</button>
    <button disabled={bulkBusy} onclick={() => bulk("unhide")} title={t("bulk.hide_hint", { event: page.event.name })}>{t("bulk.unhide")}</button>
  {/if}
  <button disabled={bulkBusy} onclick={() => (assigning = true)}>{t("bulk.assign")}</button>
  <button disabled={bulkBusy} onclick={() => bulk("unassign")}>{t("bulk.unassign")}</button>
  <button class="danger" disabled={bulkBusy} onclick={() => (confirmDelete = true)}>{t("bulk.delete")}</button>
</BulkBar>

{#if confirmDelete}
  <Modal title={t("bulk.delete_games_title", { n: selection.size })} onclose={() => (confirmDelete = false)}>
    <p>{t("bulk.delete_games_text")}</p>
    <ul class="small picked">
      {#each selection.rows.slice(0, 5) as g (g.id)}<li>{label(g)}</li>{/each}
      {#if selection.size > 5}<li class="muted">{t("bulk.and_more", { n: selection.size - 5 })}</li>{/if}
    </ul>
    {#snippet footer()}
      {#if page?.event}
        <button disabled={bulkBusy} onclick={() => { confirmDelete = false; void bulk("hide"); }}>{t("bulk.hide")}</button>
      {/if}
      <span class="spacer"></span>
      <button onclick={() => (confirmDelete = false)}>{t("common.cancel")}</button>
      <button class="danger" disabled={bulkBusy} onclick={() => bulk("delete")}>{t("bulk.delete")}</button>
    {/snippet}
  </Modal>
{/if}

{#if assigning}
  <Modal title={t("bulk.assign_title", { n: selection.size })} onclose={() => (assigning = false)}>
    <PlayerPicker value={assignPlayer} onselect={(p) => (assignPlayer = p.id)} />
    {#snippet footer()}
      <button onclick={() => (assigning = false)}>{t("common.cancel")}</button>
      <button
        class="primary"
        disabled={bulkBusy || assignPlayer === null}
        onclick={() => bulk("assign", { player_id: assignPlayer })}>{t("bulk.assign")}</button
      >
    {/snippet}
  </Modal>
{/if}

<style>
  .searchbar {
    margin-bottom: 8px;
  }
  .searchbar input[type="search"] {
    width: min(320px, 100%);
  }
  .filter-toggle {
    display: none;
  }
  .filters {
    margin-bottom: 12px;
  }
  .badges {
    display: flex;
    gap: 4px;
    flex-wrap: wrap;
  }
  .field-like {
    display: grid;
    gap: 4px;
  }
  tr.dim td {
    opacity: 0.55;
  }
  .picked {
    margin: 0;
    padding-left: 18px;
  }
  @media (max-width: 640px) {
    .head h1 {
      flex-basis: 100%;
      margin-bottom: 4px;
    }
    .searchbar input[type="search"] {
      flex: 1;
      width: auto;
    }
    .filter-toggle {
      display: inline-flex;
      min-height: 40px;
    }
    .filters {
      display: none;
    }
    .filters.open {
      display: grid;
      grid-template-columns: 1fr;
      gap: 8px;
    }
    .filters select {
      min-height: 40px;
    }
  }
</style>
