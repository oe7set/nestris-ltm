<script lang="ts">
  import ErrorBox from "../components/ErrorBox.svelte";
  import { onMount } from "svelte";
  import Modal from "../components/Modal.svelte";
  import { confirmAsync } from "../lib/confirm.svelte";
  import { api } from "../lib/api";
  import { dateTime, fromLocalInput, num, toLocalInput } from "../lib/format";
  import { i18n, t } from "../lib/i18n.svelte";
  import { errorText, toasts } from "../lib/toast.svelte";
  import type { EventInfo } from "../lib/types";

  let formBase = $state("");
  let events = $state<EventInfo[] | null>(null);
  let editing = $state<EventInfo | null>(null);
  let creating = $state(false);
  let form = $state({ name: "", starts_at: "", ends_at: "" });

  let loadError = $state<string | null>(null);

  async function load(): Promise<void> {
    try {
      loadError = null;
      events = await api<EventInfo[]>("/api/events");
    } catch (e) {
      loadError = errorText(e);
    }
  }

  function openNew(): void {
    const start = new Date();
    start.setHours(0, 0, 0, 0);
    form = { name: "", starts_at: toLocalInput(start.toISOString()), ends_at: "" };
    editing = null;
    creating = true;
    formBase = JSON.stringify(form);
  }

  function openEdit(event: EventInfo): void {
    form = { name: event.name, starts_at: toLocalInput(event.starts_at), ends_at: toLocalInput(event.ends_at) };
    editing = event;
    creating = true;
    formBase = JSON.stringify(form);
  }

  async function save(): Promise<void> {
    const body = {
      name: form.name.trim(),
      starts_at: fromLocalInput(form.starts_at),
      ends_at: fromLocalInput(form.ends_at),
    };
    try {
      if (editing) await api(`/api/events/${editing.id}`, { method: "PATCH", body });
      else await api("/api/events", { method: "POST", body });
      creating = false;
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

  onMount(() => {
    void load();
  });
</script>

<div class="row">
  <h1>{t("events.title")}</h1>
  <span class="spacer"></span>
  <button class="primary" onclick={openNew}>+ {t("events.new")}</button>
</div>
<p class="hint">{t("events.window_hint")}</p>

{#if loadError}<ErrorBox text={loadError} onretry={() => void load()} />{/if}
<div class="table-wrap">
  <table>
    <thead>
      <tr>
        <th>{t("events.name")}</th>
        <th>{t("events.start")}</th>
        <th>{t("events.end")}</th>
        <th class="num">{t("events.games")}</th>
        <th class="num">{t("events.players")}</th>
        <th>{t("events.hidden_stations")}</th>
        <th>{t("common.actions")}</th>
      </tr>
    </thead>
    <tbody>
      {#each events ?? [] as e (e.id)}
        <tr>
          <td>
            <strong>{e.name}</strong>
            {#if e.is_active}<span class="badge ok">{t("events.active")}</span>{/if}
            <div class="muted small mono">{e.slug}</div>
          </td>
          <td>{dateTime(e.starts_at, i18n.locale)}</td>
          <td>{e.ends_at ? dateTime(e.ends_at, i18n.locale) : t("events.open_end")}</td>
          <td class="num">{num(e.games, i18n.locale)}</td>
          <td class="num">{num(e.players, i18n.locale)}</td>
          <td>{e.hidden_stations.join(", ") || "–"}</td>
          <td><div class="row">
            {#if !e.is_active}
              <button onclick={() => run(() => api(`/api/events/${e.id}/activate`, { method: "POST" }))}>{t("events.activate")}</button>
            {/if}
            <button onclick={() => openEdit(e)}>{t("common.edit")}</button>
            {#if !e.is_active}
              <button
                class="danger"
                onclick={async () => (await confirmAsync({ title: t("events.delete_confirm", { name: e.name }), danger: true, confirmLabel: t("common.delete") })) && run(() => api(`/api/events/${e.id}`, { method: "DELETE" }))}
              >
                {t("common.delete")}
              </button>
            {/if}
          </div></td>
        </tr>
      {:else}
        <tr><td colspan="7" class="empty">{events ? t("events.none") : loadError ? "–" : t("common.loading")}</td></tr>
      {/each}
    </tbody>
  </table>
</div>

{#if creating}
  <Modal title={editing ? editing.name : t("events.new")} dirty={JSON.stringify(form) !== formBase} onclose={() => (creating = false)}>
    <label class="field">{t("events.name")}<input bind:value={form.name} required maxlength="128" /></label>
    <div class="form-grid">
      <label class="field">{t("events.start")}<input type="datetime-local" bind:value={form.starts_at} required /></label>
      <label class="field">{t("events.end_label")}<input type="datetime-local" bind:value={form.ends_at} /></label>
    </div>
    <p class="hint">{t("events.window_hint")}</p>
    {#snippet footer()}
      <button onclick={() => (creating = false)}>{t("common.cancel")}</button>
      <button class="primary" disabled={!form.name.trim() || !form.starts_at} onclick={save}>{t("common.save")}</button>
    {/snippet}
  </Modal>
{/if}
