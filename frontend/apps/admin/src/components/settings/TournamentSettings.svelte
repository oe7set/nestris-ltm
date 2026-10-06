<script lang="ts">
  // Einstellungen → Turnier & Szenen: how the scenes run and the hearts
  // defaults. The same switches sit on the Regie page for quick access.
  import { onMount } from "svelte";
  import { api } from "../../lib/api";
  import { t } from "../../lib/i18n.svelte";
  import { toasts } from "../../lib/toast.svelte";

  interface LivesSettings {
    default_lives: number;
    auto_bind: boolean;
    auto_deduct: boolean;
  }

  let nextRound = $state<"manual" | "auto">("manual");
  let lives = $state<LivesSettings | null>(null);
  let noEvent = $state(false);

  async function load(): Promise<void> {
    try {
      nextRound = (await api<{ next_round: "manual" | "auto" }>("/api/settings/scenes")).next_round;
    } catch (e) {
      toasts.error(e);
    }
    try {
      lives = (await api<{ settings: LivesSettings }>("/api/tournament/matches")).settings;
      noEvent = false;
    } catch {
      lives = null;
      noEvent = true;
    }
  }

  async function save(fn: () => Promise<unknown>): Promise<void> {
    try {
      await fn();
      toasts.ok(t("common.saved"));
    } catch (e) {
      toasts.error(e);
    }
    await load();
  }

  const setNextRound = (value: "manual" | "auto") =>
    save(() => api("/api/settings/scenes", { method: "PUT", body: { next_round: value } }));
  const setLives = (change: Partial<LivesSettings>) =>
    save(() => api("/api/tournament/lives/settings", { method: "PUT", body: change }));

  onMount(() => void load());
</script>

<section class="panel block">
  <h2>{t("settings.flow_title")}</h2>
  <p class="hint">{t("settings.flow_hint")}</p>
  <label class="field">
    {t("regie.next_round")}
    <div class="seg">
      <button class:on={nextRound === "manual"} onclick={() => setNextRound("manual")}>{t("regie.next_round_manual")}</button>
      <button class:on={nextRound === "auto"} onclick={() => setNextRound("auto")}>{t("regie.next_round_auto")}</button>
    </div>
  </label>
  <p class="muted small">{t("settings.flow_per_scene")} <a href="#/regie">{t("nav.regie")} →</a></p>
</section>

<section class="panel block">
  <h2>{t("settings.hearts_title")}</h2>
  <p class="hint">{t("settings.hearts_hint")}</p>
  {#if lives}
    <div class="grid">
      <label class="field">
        {t("matches.default_lives")}
        <select value={lives.default_lives} onchange={(e) => setLives({ default_lives: Number(e.currentTarget.value) })}>
          {#each [1, 2, 3, 4, 5] as n (n)}<option value={n}>{n}</option>{/each}
        </select>
      </label>
      <label class="check" title={t("regie.auto_bind_hint")}>
        <input type="checkbox" checked={lives.auto_bind} onchange={(e) => setLives({ auto_bind: e.currentTarget.checked })} />
        {t("matches.auto_bind")}
      </label>
      <label class="check" title={t("matches.auto_deduct_hint")}>
        <input type="checkbox" checked={lives.auto_deduct} onchange={(e) => setLives({ auto_deduct: e.currentTarget.checked })} />
        {t("matches.auto_deduct")}
      </label>
    </div>
  {:else if noEvent}
    <p class="info-box">{t("phase.no_event")} <a href="#/events">{t("nav.events")} →</a></p>
  {/if}
</section>

<style>
  .block {
    margin-bottom: 16px;
    display: grid;
    gap: 10px;
  }
  .block h2 {
    margin: 0;
  }
  .grid {
    display: flex;
    flex-wrap: wrap;
    gap: 24px;
    align-items: end;
  }
  .seg {
    display: inline-flex;
    border: 1px solid var(--line);
    border-radius: 8px;
    overflow: hidden;
    width: fit-content;
  }
  .seg button {
    border: 0;
    border-radius: 0;
  }
  .seg button.on {
    background: var(--accent);
    color: var(--accent-ink);
  }
</style>
