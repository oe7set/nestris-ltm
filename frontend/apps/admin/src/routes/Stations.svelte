<script lang="ts">
  import { onMount } from "svelte";
  import { confirmAsync } from "../lib/confirm.svelte";
  import { api } from "../lib/api";
  import { dateTime, num } from "../lib/format";
  import { i18n, t } from "../lib/i18n.svelte";
  import { toasts } from "../lib/toast.svelte";
  import type { EventInfo, StationRow } from "../lib/types";

  let stations = $state<StationRow[] | null>(null);
  let active = $state<EventInfo | null>(null);
  let names = $state<Record<string, string>>({});

  async function load(): Promise<void> {
    try {
      const previous = new Map((stations ?? []).map((s) => [s.id, s.name ?? ""]));
      stations = await api<StationRow[]>("/api/stations");
      // Keep names typed but not saved yet (another action reloads the list).
      names = Object.fromEntries(
        stations.map((s) => {
          const typed = names[s.id];
          const edited = typed !== undefined && typed !== previous.get(s.id);
          return [s.id, edited ? typed : (s.name ?? "")];
        }),
      );
      const events = await api<EventInfo[]>("/api/events");
      active = events.find((e) => e.is_active) ?? null;
    } catch (e) {
      toasts.error(e);
    }
  }

  async function run(fn: () => Promise<unknown>, message?: string): Promise<void> {
    try {
      await fn();
      if (message) toasts.ok(message);
      await load();
    } catch (e) {
      toasts.error(e);
    }
  }

  function toggleHidden(id: string, hide: boolean): void {
    if (!active) return;
    void run(() => api(`/api/events/${active!.id}/hidden-stations/${encodeURIComponent(id)}`, { method: hide ? "PUT" : "DELETE" }));
  }

  onMount(() => {
    void load();
  });
</script>

<h1>{t("stations.title")}</h1>

<div class="table-wrap">
  <table>
    <thead>
      <tr>
        <th>{t("stations.id")}</th>
        <th>{t("stations.rename")}</th>
        <th>{t("games.status")}</th>
        <th>{t("stations.version")}</th>
        <th class="num">{t("stations.games")}</th>
        <th>{t("stations.last_seen")}</th>
        {#if active}<th>{t("stations.hide")}</th>{/if}
        <th></th>
      </tr>
    </thead>
    <tbody>
      {#each stations ?? [] as s (s.id)}
        <tr>
          <td class="mono">{s.id}</td>
          <td>
            <form class="row" onsubmit={(e) => { e.preventDefault(); void run(() => api(`/api/stations/${encodeURIComponent(s.id)}`, { method: "PATCH", body: { name: names[s.id]?.trim() || null } }), t("common.saved")); }}>
              <input bind:value={names[s.id]} maxlength="128" aria-label={t("stations.name")} />
              <button type="submit">{t("common.save")}</button>
            </form>
          </td>
          <td>
            {#if s.live}
              <span class="dot {s.live.online && !s.live.stale ? 'ok' : s.live.online ? 'warn' : 'bad'}"></span>
              {s.live.online ? t("dash.online") : t("dash.offline")}
            {:else}–{/if}
          </td>
          <td class="small">{String(s.live?.status?.version ?? "–")}</td>
          <td class="num">{num(s.games, i18n.locale)}</td>
          <td>{dateTime(s.last_seen_at, i18n.locale)}</td>
          {#if active}
            <td>
              <input
                type="checkbox"
                checked={active.hidden_stations.includes(s.id)}
                onchange={(e) => toggleHidden(s.id, e.currentTarget.checked)}
                aria-label={t("stations.hide")}
              />
            </td>
          {/if}
          <td>
            <button
              class="danger"
              disabled={s.live?.online}
              onclick={async () => (await confirmAsync({ title: t("stations.delete_confirm", { id: s.id }), danger: true, confirmLabel: t("common.delete") })) && run(() => api(`/api/stations/${encodeURIComponent(s.id)}`, { method: "DELETE" }), t("common.deleted"))}
            >
              {t("common.delete")}
            </button>
          </td>
        </tr>
      {:else}
        <tr><td colspan="8" class="empty">{stations ? t("stations.none") : t("common.loading")}</td></tr>
      {/each}
    </tbody>
  </table>
</div>

<style>
  td form input {
    width: 160px;
  }
</style>
