<script lang="ts">
  // Station results that could not be stored (e.g. a payload this version
  // does not understand). They wait in the spool's failed/ folder: put them
  // back into the queue after a fix, or discard them.
  import { onMount } from "svelte";
  import { api, ApiError } from "../lib/api";
  import { confirmAsync } from "../lib/confirm.svelte";
  import { dateTime } from "../lib/format";
  import { i18n, t } from "../lib/i18n.svelte";
  import { errorText, toasts } from "../lib/toast.svelte";

  interface FailedEvent {
    name: string;
    station: string | null;
    kind: string | null;
    received_at: string | null;
    reason: string | null;
    payload: string | null;
    truncated?: boolean;
    unreadable?: string;
    size: number;
  }

  let items = $state<FailedEvent[] | null>(null);
  let pending = $state(0);
  let error = $state<string | null>(null);
  let busy = $state(false);

  async function load(): Promise<void> {
    try {
      const res = await api<{ items: FailedEvent[]; pending: number }>("/api/spool/failed");
      items = res.items;
      pending = res.pending;
      error = null;
    } catch (e) {
      error = errorText(e);
    }
  }

  async function retry(item: FailedEvent): Promise<void> {
    busy = true;
    try {
      await api(`/api/spool/failed/${item.name}/retry`, { method: "POST" });
      toasts.ok(t("spool.retried"));
      // The worker may fail it again at once; show the outcome.
      setTimeout(() => void load(), 1500);
      await load();
    } catch (e) {
      if (!(e instanceof ApiError && e.status === 404)) toasts.error(e);
      await load();
    } finally {
      busy = false;
    }
  }

  async function discard(item: FailedEvent): Promise<void> {
    const ok = await confirmAsync({
      title: t("spool.discard_confirm"),
      text: t("spool.discard_text"),
      danger: true,
      confirmLabel: t("spool.discard"),
    });
    if (!ok) return;
    busy = true;
    try {
      await api(`/api/spool/failed/${item.name}`, { method: "DELETE" });
      toasts.ok(t("common.deleted"));
      await load();
    } catch (e) {
      toasts.error(e);
    } finally {
      busy = false;
    }
  }

  onMount(() => {
    void load();
  });
</script>

<h1>{t("spool.title")}</h1>
<p class="hint">{t("spool.intro")}</p>
{#if pending}<p class="info-box small">{t("spool.pending", { n: pending })}</p>{/if}

{#if error}
  <div class="error-box row">
    <span>{error}</span><span class="spacer"></span><button onclick={load}>{t("common.retry")}</button>
  </div>
{:else if items === null}
  <p class="muted">{t("common.loading")}</p>
{:else if items.length === 0}
  <p class="panel ok">✓ {t("spool.none")}</p>
{:else}
  <div class="list">
    {#each items as item (item.name)}
      <section class="panel">
        <div class="row">
          <strong>{item.station ?? "?"}</strong>
          <span class="badge">{item.kind ?? "?"}</span>
          <span class="muted small">{dateTime(item.received_at, i18n.locale)}</span>
          <span class="spacer"></span>
          <button disabled={busy} onclick={() => retry(item)}>{t("spool.retry")}</button>
          <button class="danger" disabled={busy} onclick={() => discard(item)}>{t("spool.discard")}</button>
        </div>
        <p class="reason small"><span class="muted">{t("spool.reason")}:</span> {item.reason ?? item.unreadable ?? "–"}</p>
        {#if item.payload}
          <details>
            <summary class="small">{t("spool.payload")}</summary>
            <pre class="mono small">{item.payload}{item.truncated ? "\n…" : ""}</pre>
          </details>
        {/if}
      </section>
    {/each}
  </div>
{/if}

<style>
  .list {
    display: grid;
    gap: 10px;
  }
  .reason {
    margin: 8px 0 0;
    overflow-wrap: anywhere;
  }
  pre {
    white-space: pre-wrap;
    word-break: break-all;
    max-height: 240px;
    overflow: auto;
    background: #0e1528;
    padding: 8px;
    border-radius: 6px;
  }
  summary {
    cursor: pointer;
    color: var(--muted);
    margin-top: 6px;
  }
  .ok {
    color: #bbf7d0;
  }
</style>
