<script lang="ts">
  import { onMount } from "svelte";
  import Pager from "../components/Pager.svelte";
  import { api } from "../lib/api";
  import { dateTime } from "../lib/format";
  import { i18n, t } from "../lib/i18n.svelte";
  import { toasts } from "../lib/toast.svelte";
  import type { AuditEntry } from "../lib/types";

  const LIMIT = 100;
  const ENTITIES = ["player", "game", "event", "station", "admin", "token"];
  let entity = $state("");
  let offset = $state(0);
  let page = $state<{ items: AuditEntry[]; total: number } | null>(null);

  async function load(): Promise<void> {
    try {
      page = await api("/api/audit", { query: { entity, limit: LIMIT, offset } });
    } catch (e) {
      toasts.error(e);
    }
  }

  function link(e: AuditEntry): string | null {
    if (e.entity === "player") return `#/players/${e.entity_id}`;
    if (e.entity === "game" && e.action !== "delete") return `#/games/${e.entity_id}`;
    return null;
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
  });
</script>

<div class="row">
  <h1>{t("audit.title")}</h1>
  <span class="spacer"></span>
  <select bind:value={entity} onchange={() => { offset = 0; void load(); }} aria-label={t("audit.filter")}>
    <option value="">{t("audit.filter")}: {t("common.all")}</option>
    {#each ENTITIES as e (e)}<option value={e}>{e}</option>{/each}
  </select>
</div>

<div class="table-wrap">
  <table>
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
          <td class="nowrap">{dateTime(e.ts, i18n.locale)}</td>
          <td>{e.actor}</td>
          <td><span class="badge">{e.action}</span></td>
          <td>{#if href}<a {href}>{e.entity} #{e.entity_id}</a>{:else}{e.entity} {e.entity_id}{/if}</td>
          <td class="small">
            {#each changes(e).slice(0, 8) as [key, before, after] (key)}
              <div><span class="muted">{key}:</span> {#if e.before}<s class="muted">{before}</s> → {/if}{after}</div>
            {/each}
          </td>
        </tr>
      {:else}
        <tr><td colspan="5" class="empty">{page ? t("audit.none") : t("common.loading")}</td></tr>
      {/each}
    </tbody>
  </table>
</div>
{#if page}
  <Pager total={page.total} limit={LIMIT} {offset} onchange={(o) => { offset = o; void load(); }} />
{/if}

<style>
  .nowrap {
    white-space: nowrap;
  }
  td.small div {
    word-break: break-word;
  }
</style>
