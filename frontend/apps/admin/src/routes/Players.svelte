<script lang="ts">
  import { onMount } from "svelte";
  import BulkBar from "../components/BulkBar.svelte";
  import Modal from "../components/Modal.svelte";
  import Pager from "../components/Pager.svelte";
  import { api } from "../lib/api";
  import { num } from "../lib/format";
  import { format, i18n, t, tDynamic } from "../lib/i18n.svelte";
  import { router } from "../lib/router.svelte";
  import { Selection } from "../lib/selection.svelte";
  import { toasts } from "../lib/toast.svelte";
  import type { Page, Player } from "../lib/types";

  interface BulkResult {
    affected: number;
    skipped: { id: number; reason: string; nickname?: string }[];
  }

  const LIMIT = 50;
  const query = router.current.query;
  let q = $state(query.get("q") ?? "");
  let includeDeleted = $state(query.get("deleted") === "true");
  let onlyAuto = $state(query.get("auto") === "true");
  let offset = $state(Number(query.get("offset") ?? 0));
  let page = $state<Page<Player> | null>(null);
  let creating = $state(false);
  let newNickname = $state("");
  let timer: ReturnType<typeof setTimeout> | undefined;

  const selection = new Selection<Player>();
  let confirmDelete = $state(false);
  let bulkBusy = $state(false);
  let pageBox = $state<HTMLInputElement>();

  const rows = $derived(page?.items ?? []);
  const pageState = $derived(selection.pageState(rows));
  const anyDeleted = $derived(selection.rows.some((p) => p.deleted_at));
  const anyActive = $derived(selection.rows.some((p) => !p.deleted_at));

  $effect(() => {
    if (pageBox) pageBox.indeterminate = pageState === "some";
  });

  async function load(): Promise<void> {
    router.setQuery({ q, deleted: includeDeleted, auto: onlyAuto, offset: offset || null });
    try {
      page = await api<Page<Player>>("/api/players", {
        query: { q, include_deleted: includeDeleted, only_auto_created: onlyAuto, limit: LIMIT, offset },
      });
    } catch (e) {
      toasts.error(e);
    }
  }

  function searchSoon(): void {
    clearTimeout(timer);
    offset = 0;
    selection.clear();
    timer = setTimeout(load, 250);
  }

  async function create(event: SubmitEvent): Promise<void> {
    event.preventDefault();
    try {
      const player = await api<Player>("/api/players", { method: "POST", body: { nickname: newNickname } });
      creating = false;
      newNickname = "";
      router.go(`/players/${player.id}`);
    } catch (e) {
      toasts.error(e);
    }
  }

  function toggleRow(p: Player): void {
    if (!selection.toggle(p)) toasts.error(t("bulk.limit", { max: selection.max }));
  }

  async function bulk(action: "delete" | "restore"): Promise<void> {
    bulkBusy = true;
    try {
      const res = await api<BulkResult>("/api/players/bulk", {
        method: "POST",
        body: { ids: selection.ids, action },
      });
      toasts.ok(format(tDynamic(`bulk.players_done.${action}`, action), { n: res.affected }));
      if (res.skipped.length) {
        const names = new Map(selection.rows.map((p) => [p.id, p.nickname]));
        const list = res.skipped
          .map((s) => `${names.get(s.id) ?? s.nickname ?? `#${s.id}`} (${tDynamic(`bulk.reason.${s.reason}`, s.reason)})`)
          .join(", ");
        toasts.error(t("bulk.skipped", { n: res.skipped.length, list }));
      }
      selection.clear();
      confirmDelete = false;
      await load();
    } catch (e) {
      toasts.error(e);
    } finally {
      bulkBusy = false;
    }
  }

  // onMount, not $effect: load() reads state that must not re-trigger it.
  onMount(() => {
    void load();
  });
</script>

<div class="row head">
  <h1>{t("players.title")}</h1>
  <span class="spacer"></span>
  <button class="primary" onclick={() => (creating = true)}>+ {t("players.new")}</button>
</div>

<div class="row filters">
  <input type="search" placeholder={t("players.search")} bind:value={q} oninput={searchSoon} />
  <label class="check"><input type="checkbox" bind:checked={onlyAuto} onchange={searchSoon} /> {t("players.only_auto")}</label>
  <label class="check"><input type="checkbox" bind:checked={includeDeleted} onchange={searchSoon} /> {t("players.include_deleted")}</label>
</div>

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
            onchange={() => selection.setMany(rows, pageState !== "all")}
            aria-label={t("bulk.select_page")}
            title={t("bulk.select_page")}
          />
        </th>
        <th>{t("players.nickname")}</th>
        <th>{t("players.name")}</th>
        <th class="num">{t("players.games")}</th>
        <th class="num">{t("players.best")}</th>
        <th class="num">{t("players.best_event")}</th>
        <th></th>
      </tr>
    </thead>
    <tbody>
      {#each rows as p (p.id)}
        <tr class="clickable" class:selected={selection.has(p.id)} onclick={() => router.go(`/players/${p.id}`)}>
          <td class="sel" onclick={(e) => e.stopPropagation()}>
            <input
              type="checkbox"
              checked={selection.has(p.id)}
              onchange={() => toggleRow(p)}
              aria-label={`${t("bulk.select_row")}: ${p.nickname}`}
            />
          </td>
          <td class="card-title" data-label={t("players.nickname")}><a href={`#/players/${p.id}`}>{p.nickname}</a></td>
          <td class="card-sub" data-label={t("players.name")}>{[p.first_name, p.last_name].filter(Boolean).join(" ") || "–"}</td>
          <td class="num" data-label={t("players.games")}>{num(p.games_total, i18n.locale)}</td>
          <td class="num" data-label={t("players.best")}>{num(p.best_score, i18n.locale)}</td>
          <td class="num" data-label={t("players.best_event")}>{num(p.best_score_event, i18n.locale)}</td>
          <td class="card-badges"><div class="badges">
            {#if p.auto_created}<span class="badge warn">{t("players.auto")}</span>{/if}
            {#if p.hide_everywhere}<span class="badge bad">{t("players.hidden")}</span>{/if}
            {#if p.hide_from_bracket && !p.hide_everywhere}<span class="badge">{t("players.hidden_bracket")}</span>{/if}
            {#if p.deleted_at}<span class="badge bad">{t("players.deleted")}</span>{/if}
          </div></td>
        </tr>
      {:else}
        <tr><td colspan="7" class="empty">{page ? t("players.none") : t("common.loading")}</td></tr>
      {/each}
    </tbody>
  </table>
</div>
{#if page}
  <Pager total={page.total} limit={LIMIT} {offset} onchange={(o) => { offset = o; void load(); }} />
{/if}

<BulkBar count={selection.size} onclear={() => selection.clear()}>
  {#if anyDeleted}
    <button disabled={bulkBusy} onclick={() => bulk("restore")}>{t("bulk.restore")}</button>
  {/if}
  {#if anyActive}
    <button class="danger" disabled={bulkBusy} onclick={() => (confirmDelete = true)}>{t("bulk.delete")}</button>
  {/if}
</BulkBar>

{#if confirmDelete}
  <Modal title={t("bulk.players_delete_title", { n: selection.rows.filter((p) => !p.deleted_at).length })} onclose={() => (confirmDelete = false)}>
    <p>{t("bulk.players_delete_text")}</p>
    <ul class="small picked">
      {#each selection.rows.filter((p) => !p.deleted_at).slice(0, 8) as p (p.id)}<li>{p.nickname}</li>{/each}
      {#if selection.rows.filter((p) => !p.deleted_at).length > 8}
        <li class="muted">{t("bulk.and_more", { n: selection.rows.filter((p) => !p.deleted_at).length - 8 })}</li>
      {/if}
    </ul>
    {#snippet footer()}
      <button onclick={() => (confirmDelete = false)}>{t("common.cancel")}</button>
      <button class="danger" disabled={bulkBusy} onclick={() => bulk("delete")}>{t("bulk.delete")}</button>
    {/snippet}
  </Modal>
{/if}

{#if creating}
  <Modal title={t("players.new")} onclose={() => (creating = false)}>
    <form id="new-player" onsubmit={create}>
      <label class="field">
        {t("players.nickname")}
        <!-- svelte-ignore a11y_autofocus -->
        <input bind:value={newNickname} required maxlength="64" autofocus />
      </label>
    </form>
    {#snippet footer()}
      <button onclick={() => (creating = false)}>{t("common.cancel")}</button>
      <button class="primary" type="submit" form="new-player">{t("common.create")}</button>
    {/snippet}
  </Modal>
{/if}

<style>
  .filters {
    margin-bottom: 12px;
    gap: 16px;
  }
  .filters input[type="search"] {
    width: min(320px, 100%);
  }
  .badges {
    display: flex;
    gap: 4px;
    flex-wrap: wrap;
  }
  .picked {
    margin: 0;
    padding-left: 18px;
  }
  @media (max-width: 640px) {
    .filters {
      gap: 8px 16px;
    }
    .filters input[type="search"] {
      width: 100%;
    }
  }
</style>
