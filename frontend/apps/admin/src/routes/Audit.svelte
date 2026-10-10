<script lang="ts">
  import ErrorBox from "../components/ErrorBox.svelte";
  import { onMount } from "svelte";
  import Pager from "../components/Pager.svelte";
  import { api, buildUrl } from "../lib/api";
  import { dateTime, fromLocalInput } from "../lib/format";
  import { i18n, t, tDynamic } from "../lib/i18n.svelte";
  import { router } from "../lib/router.svelte";
  import { errorText } from "../lib/toast.svelte";
  import type { AuditEntry } from "../lib/types";

  const LIMIT = 100;
  const query = router.current.query;
  let entity = $state(query.get("entity") ?? "");
  let action = $state(query.get("action") ?? "");
  let actor = $state(query.get("actor") ?? "");
  let since = $state("");
  let until = $state("");
  let q = $state(query.get("q") ?? "");
  let offset = $state(0);
  let page = $state<{ items: AuditEntry[]; total: number } | null>(null);
  let facets = $state<{ entities: string[]; actions: string[]; actors: string[] }>({
    entities: [],
    actions: [],
    actors: [],
  });
  let loadError = $state<string | null>(null);
  let timer: ReturnType<typeof setTimeout> | undefined;

  const filters = $derived({
    entity,
    action,
    actor,
    since: fromLocalInput(since),
    until: fromLocalInput(until),
    q,
  });
  const csvUrl = $derived(buildUrl("/api/audit.csv", filters));

  async function load(): Promise<void> {
    router.setQuery({ entity, action, actor, q });
    try {
      loadError = null;
      page = await api("/api/audit", { query: { ...filters, limit: LIMIT, offset } });
    } catch (e) {
      loadError = errorText(e);
    }
  }

  function reload(): void {
    offset = 0;
    void load();
  }

  function searchSoon(): void {
    clearTimeout(timer);
    timer = setTimeout(reload, 300);
  }

  /** Where the changed object lives in the admin UI. */
  function link(e: AuditEntry): string | null {
    if (e.action === "delete") return null;
    switch (e.entity) {
      case "player":
        return `#/players/${e.entity_id}`;
      case "game":
        return `#/games/${e.entity_id}`;
      case "scene":
        return `#/studio/scene/${e.entity_id}`;
      case "layout":
        return `#/studio/layout/${e.entity_id}`;
      case "event":
        return "#/events";
      case "station":
      case "station_config":
        return "#/stations";
      case "admin":
      case "token":
        return "#/settings?tab=access";
      case "database":
        return "#/database";
      case "spool":
        return "#/spool";
      case "match":
      case "tournament":
        return "#/tournament";
      default:
        return null;
    }
  }

  function show(value: unknown): string {
    if (value === null || value === undefined) return "–";
    return typeof value === "object" ? JSON.stringify(value) : String(value);
  }

  function changes(e: AuditEntry): [string, string, string][] {
    const keys = new Set([...Object.keys(e.before ?? {}), ...Object.keys(e.after ?? {})]);
    return [...keys].map((k) => [k, show(e.before?.[k]), show(e.after?.[k])]);
  }

  onMount(() => {
    void load();
    api<typeof facets>("/api/audit/facets")
      .then((f) => (facets = f))
      .catch(() => {});
  });
</script>

<div class="row head">
  <h1>{t("audit.title")}</h1>
  <span class="spacer"></span>
  <a class="button" href={csvUrl} download>CSV</a>
</div>

<div class="filters panel">
  <label class="field">
    {t("audit.entity")}
    <select bind:value={entity} onchange={reload}>
      <option value="">{t("common.all")}</option>
      {#each facets.entities as e (e)}<option value={e}>{tDynamic(`audit.entity.${e}`, e)}</option>{/each}
    </select>
  </label>
  <label class="field">
    {t("audit.action")}
    <select bind:value={action} onchange={reload}>
      <option value="">{t("common.all")}</option>
      {#each facets.actions as a (a)}<option value={a}>{tDynamic(`audit.action.${a}`, a)}</option>{/each}
    </select>
  </label>
  <label class="field">
    {t("audit.actor")}
    <select bind:value={actor} onchange={reload}>
      <option value="">{t("common.all")}</option>
      {#each facets.actors as a (a)}<option value={a}>{a}</option>{/each}
    </select>
  </label>
  <label class="field">{t("audit.since")}<input type="datetime-local" bind:value={since} onchange={reload} /></label>
  <label class="field">{t("audit.until")}<input type="datetime-local" bind:value={until} onchange={reload} /></label>
  <label class="field">{t("common.search")}<input type="search" bind:value={q} oninput={searchSoon} placeholder={t("audit.search_hint")} /></label>
</div>

{#if loadError}<ErrorBox text={loadError} onretry={() => void load()} />{/if}
<div class="table-wrap">
  <table class="table-cards">
    <thead>
      <tr>
        <th>{t("audit.time")}</th>
        <th>{t("audit.actor")}</th>
        <th>{t("audit.action")}</th>
        <th>{t("audit.entity")}</th>
        <th>{t("audit.changes")}</th>
      </tr>
    </thead>
    <tbody>
      {#each page?.items ?? [] as e (e.id)}
        {@const href = link(e)}
        <tr>
          <td class="nowrap card-sub" data-label={t("audit.time")}>{dateTime(e.ts, i18n.locale)}</td>
          <td class="card-title" data-label={t("audit.actor")}>{e.actor}</td>
          <td data-label={t("audit.action")}><span class="badge">{tDynamic(`audit.action.${e.action}`, e.action)}</span></td>
          <td data-label={t("audit.entity")}>
            {#if href}<a {href}>{tDynamic(`audit.entity.${e.entity}`, e.entity)} #{e.entity_id}</a>
            {:else}{tDynamic(`audit.entity.${e.entity}`, e.entity)} {e.entity_id}{/if}
          </td>
          <td class="small changes">
            {#each changes(e).slice(0, 8) as [key, before, after] (key)}
              <div><span class="muted">{key}:</span> {#if e.before}<s class="muted">{before}</s> → {/if}{after}</div>
            {/each}
          </td>
        </tr>
      {:else}
        <tr><td colspan="5" class="empty">{page ? t("audit.none") : loadError ? "–" : t("common.loading")}</td></tr>
      {/each}
    </tbody>
  </table>
</div>
{#if page}
  <Pager total={page.total} limit={LIMIT} {offset} onchange={(o) => { offset = o; void load(); }} />
{/if}

<style>
  .filters {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(170px, 1fr));
    gap: 10px;
    margin-bottom: 12px;
  }
  .nowrap {
    white-space: nowrap;
  }
  .changes div {
    overflow-wrap: anywhere;
  }
</style>
