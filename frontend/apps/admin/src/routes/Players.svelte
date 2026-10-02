<script lang="ts">
  import { onMount } from "svelte";
  import Modal from "../components/Modal.svelte";
  import Pager from "../components/Pager.svelte";
  import { api } from "../lib/api";
  import { num } from "../lib/format";
  import { i18n, t } from "../lib/i18n.svelte";
  import { router } from "../lib/router.svelte";
  import { toasts } from "../lib/toast.svelte";
  import type { Page, Player } from "../lib/types";

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

  // onMount, not $effect: load() reads state that must not re-trigger it.
  onMount(() => {
    void load();
  });
</script>

<div class="row">
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
  <table>
    <thead>
      <tr>
        <th>{t("players.nickname")}</th>
        <th>{t("players.name")}</th>
        <th class="num">{t("players.games")}</th>
        <th class="num">{t("players.best")}</th>
        <th class="num">{t("players.best_event")}</th>
        <th></th>
      </tr>
    </thead>
    <tbody>
      {#each page?.items ?? [] as p (p.id)}
        <tr class="clickable" onclick={() => router.go(`/players/${p.id}`)}>
          <td><a href={`#/players/${p.id}`}>{p.nickname}</a></td>
          <td>{[p.first_name, p.last_name].filter(Boolean).join(" ") || "–"}</td>
          <td class="num">{num(p.games_total, i18n.locale)}</td>
          <td class="num">{num(p.best_score, i18n.locale)}</td>
          <td class="num">{num(p.best_score_event, i18n.locale)}</td>
          <td><div class="badges">
            {#if p.auto_created}<span class="badge warn">{t("players.auto")}</span>{/if}
            {#if p.hide_everywhere}<span class="badge bad">{t("players.hidden")}</span>{/if}
            {#if p.hide_from_bracket && !p.hide_everywhere}<span class="badge">{t("players.hidden_bracket")}</span>{/if}
            {#if p.deleted_at}<span class="badge bad">{t("players.deleted")}</span>{/if}
          </div></td>
        </tr>
      {:else}
        <tr><td colspan="6" class="empty">{page ? t("players.none") : t("common.loading")}</td></tr>
      {/each}
    </tbody>
  </table>
</div>
{#if page}
  <Pager total={page.total} limit={LIMIT} {offset} onchange={(o) => { offset = o; void load(); }} />
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
</style>
