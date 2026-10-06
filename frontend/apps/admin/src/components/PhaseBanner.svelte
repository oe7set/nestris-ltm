<script lang="ts" module>
  export interface Phase {
    event: string | null;
    has_event: boolean;
    seeded: boolean;
    seeded_at: string | null;
    active_count: number;
    players: number;
    known: boolean;
  }
</script>

<script lang="ts">
  // Where the tournament stands: qualifying (the bracket fills live from the
  // highscore) or fixed. FIX / reset winners / UNSEED right here, so nobody
  // has to look for them inside the tournament console. Shared by Regie,
  // Turnier and the dashboard (compact).
  import { onMount } from "svelte";
  import { api } from "../lib/api";
  import { dateTime } from "../lib/format";
  import { i18n, t } from "../lib/i18n.svelte";
  import { toasts } from "../lib/toast.svelte";


  interface Props {
    compact?: boolean;
    /** Called after every load (pages react to a phase change). */
    onchange?: (phase: Phase) => void;
  }
  let { compact = false, onchange }: Props = $props();

  let phase = $state<Phase | null>(null);
  let busy = $state(false);

  async function load(): Promise<void> {
    try {
      phase = await api<Phase>("/api/tournament/phase");
      onchange?.(phase);
    } catch {
      phase = null;
    }
  }

  async function act(path: string, question: string): Promise<void> {
    if (busy || !confirm(question)) return;
    busy = true;
    try {
      await api(path, { method: "POST" });
      toasts.ok(t("common.saved"));
    } catch (e) {
      toasts.error(e);
    } finally {
      busy = false;
      await load();
    }
  }

  onMount(() => {
    void load();
    const timer = setInterval(() => void load(), 3000);
    return () => clearInterval(timer);
  });
</script>

{#if phase && !phase.has_event}
  <div class="banner warn" class:compact>
    <strong>{t("phase.no_event")}</strong>
    <span class="spacer"></span>
    <a class="button" href="#/events">{t("nav.events")} →</a>
  </div>
{:else if phase}
  <div class="banner" class:quali={!phase.seeded} class:fixed={phase.seeded} class:compact>
    <span class="dot"></span>
    <div class="text">
      <strong>{phase.seeded ? t("phase.fixed") : t("phase.quali")}</strong>
      <span class="muted small">
        {#if phase.seeded}
          {t("phase.fixed_hint", { n: phase.active_count, at: phase.seeded_at ? dateTime(phase.seeded_at, i18n.locale) : "–" })}
        {:else}
          {t("phase.quali_hint", { n: phase.active_count, players: phase.players })}
        {/if}
        {#if phase.event}· {phase.event}{/if}
      </span>
    </div>
    <span class="spacer"></span>
    {#if !phase.seeded}
      <button
        class="primary"
        disabled={busy || phase.players < 2}
        onclick={() => act("/api/tournament/fix", t("phase.fix_confirm", { n: phase?.active_count ?? 0 }))}
      >
        {t("phase.fix")}
      </button>
    {:else if !compact}
      <button disabled={busy} onclick={() => act("/api/tournament/reset", t("phase.reset_confirm"))}>{t("phase.reset")}</button>
      <button class="danger" disabled={busy} onclick={() => act("/api/tournament/unseed", t("phase.unseed_confirm"))}>
        {t("phase.unseed")}
      </button>
    {/if}
    {#if compact}<a class="button" href="#/tournament">{t("nav.tournament")} →</a>{/if}
  </div>
{/if}

<style>
  .banner {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 12px 16px;
    border: 1px solid var(--line);
    border-radius: 10px;
    background: var(--panel);
    margin-bottom: 14px;
    flex-wrap: wrap;
  }
  .banner.compact {
    padding: 8px 12px;
  }
  .banner.quali {
    border-color: #3cbcfc;
  }
  .banner.fixed {
    border-color: var(--accent);
  }
  .banner.warn {
    border-color: var(--bad, #f83800);
  }
  .text {
    display: grid;
    gap: 2px;
  }
  .dot {
    width: 12px;
    height: 12px;
    border-radius: 50%;
    flex: none;
  }
  .quali .dot {
    background: #3cbcfc;
    box-shadow: 0 0 8px #3cbcfc;
  }
  .fixed .dot {
    background: var(--accent);
  }
</style>
