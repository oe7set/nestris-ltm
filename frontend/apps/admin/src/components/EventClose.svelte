<script lang="ts">
  // Closing an event: back up the database, download the results, end the
  // event's time window and optionally start the next event. The steps run
  // in this order (the exports still see the event as active).
  import { untrack } from "svelte";
  import Modal from "./Modal.svelte";
  import { api } from "../lib/api";
  import { fromLocalInput, toLocalInput } from "../lib/format";
  import { t } from "../lib/i18n.svelte";
  import { errorText } from "../lib/toast.svelte";
  import type { EventInfo } from "../lib/types";

  interface Props {
    event: EventInfo;
    onclose: () => void;
    ondone: () => void;
  }
  let { event, onclose, ondone }: Props = $props();

  type StepId = "backup" | "exports" | "end" | "next";
  // Starting values only: the event does not change while the dialog is open.
  let options = $state({ backup: true, exports: true, end: untrack(() => !event.ends_at), next: false });
  let nextName = $state("");
  let nextStart = $state(toLocalInput(new Date(Date.now() + 365 * 86400_000).toISOString()));
  let status = $state<Partial<Record<StepId, "run" | "ok" | string>>>({});
  let running = $state(false);
  let finished = $state(false);

  function download(url: string): void {
    const a = document.createElement("a");
    a.href = url;
    a.download = "";
    document.body.append(a);
    a.click();
    a.remove();
  }

  async function step(id: StepId, fn: () => Promise<unknown>): Promise<boolean> {
    status[id] = "run";
    try {
      await fn();
      status[id] = "ok";
      return true;
    } catch (e) {
      status[id] = errorText(e);
      return false;
    }
  }

  async function start(): Promise<void> {
    running = true;
    // A failed backup stops everything else: nothing is changed without one.
    if (options.backup && !(await step("backup", () => api("/api/db/backups", { method: "POST" })))) {
      running = false;
      return;
    }
    if (options.exports) {
      await step("exports", async () => {
        download("/api/export/highscore.csv");
        await new Promise((r) => setTimeout(r, 400));
        download("/api/export/games.csv");
      });
    }
    if (options.end) {
      await step("end", () =>
        api(`/api/events/${event.id}`, {
          method: "PATCH",
          body: { name: event.name, starts_at: event.starts_at, ends_at: new Date().toISOString() },
        }),
      );
    }
    if (options.next && nextName.trim()) {
      await step("next", async () => {
        const created = await api<EventInfo>("/api/events", {
          method: "POST",
          body: { name: nextName.trim(), starts_at: fromLocalInput(nextStart), ends_at: null },
        });
        if (!created.is_active) await api(`/api/events/${created.id}/activate`, { method: "POST" });
      });
    }
    running = false;
    finished = true;
    ondone();
  }

  const STEPS: { id: StepId; label: "close.backup" | "close.exports" | "close.end" | "close.next" }[] = [
    { id: "backup", label: "close.backup" },
    { id: "exports", label: "close.exports" },
    { id: "end", label: "close.end" },
    { id: "next", label: "close.next" },
  ];
</script>

<Modal title={t("close.title", { name: event.name })} onclose={() => !running && onclose()}>
  <p class="hint">{t("close.intro")}</p>
  <ul class="steps">
    {#each STEPS as s (s.id)}
      {@const st = status[s.id]}
      <li>
        <label class="check">
          <input type="checkbox" bind:checked={options[s.id]} disabled={running || finished} />
          {t(s.label)}
        </label>
        {#if st === "run"}<span class="muted small">…</span>
        {:else if st === "ok"}<span class="badge ok">✓</span>
        {:else if st}<span class="badge bad" title={st}>✗ {st}</span>{/if}
      </li>
    {/each}
  </ul>
  {#if options.next}
    <div class="form-grid">
      <label class="field">{t("common.name")}<input bind:value={nextName} maxlength="128" disabled={running || finished} /></label>
      <label class="field">{t("events.start")}<input type="datetime-local" bind:value={nextStart} disabled={running || finished} /></label>
    </div>
  {/if}
  {#if finished}<p class="info-box">{t("close.done")}</p>{/if}
  {#snippet footer()}
    {#if finished}
      <button class="primary" onclick={onclose}>{t("common.close")}</button>
    {:else}
      <button disabled={running} onclick={onclose}>{t("common.cancel")}</button>
      <button
        class="primary"
        disabled={running || (options.next && !nextName.trim()) || !Object.values(options).some(Boolean)}
        onclick={start}>{t("close.start")}</button
      >
    {/if}
  {/snippet}
</Modal>

<style>
  .steps {
    list-style: none;
    margin: 0;
    padding: 0;
    display: grid;
    gap: 8px;
  }
  .steps li {
    display: flex;
    gap: 10px;
    align-items: center;
    flex-wrap: wrap;
  }
  .badge.bad {
    max-width: 100%;
    white-space: normal;
  }
</style>
