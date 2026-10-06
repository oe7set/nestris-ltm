<script lang="ts">
  // Tournament: where it stands (qualifying / fixed, FIX right here), the
  // bracket (the console ported from TournamentHigscore: players, size,
  // click-to-win) and the hearts of the 1-vs-1 matches. The highscore
  // display's settings are in Einstellungen → Highscore-Anzeige.
  import MatchesPanel from "../components/MatchesPanel.svelte";
  import PhaseBanner from "../components/PhaseBanner.svelte";
  import { t } from "../lib/i18n.svelte";
  import { router } from "../lib/router.svelte";

  type Tab = "bracket" | "matches";
  let tab = $state<Tab>(router.current.query.get("tab") === "matches" ? "matches" : "bracket");

  function setTab(next: Tab): void {
    tab = next;
    router.setQuery({ tab: next === "bracket" ? null : next });
  }
</script>

<div class="head row">
  <h1>{t("tournament.title")}</h1>
  <span class="spacer"></span>
  <a class="button" href="/view/highscore" target="_blank" rel="noopener">{t("tournament.open_view")} ↗</a>
  <a class="button" href="/view/tournament-admin" target="_blank" rel="noopener">{t("tournament.fullscreen")} ↗</a>
</div>

<PhaseBanner />

<div class="tabs">
  <button class:on={tab === "bracket"} onclick={() => setTab("bracket")}>{t("tournament.tab_bracket")}</button>
  <button class:on={tab === "matches"} onclick={() => setTab("matches")}>{t("tournament.tab_matches")}</button>
</div>

{#if tab === "bracket"}
  <p class="hint">{t("tournament.hint")}</p>
  <iframe src="/view/tournament-admin" title={t("tournament.title")}></iframe>
{:else}
  <MatchesPanel />
{/if}

<style>
  .head h1 {
    margin: 0;
  }
  .head {
    margin-bottom: 10px;
  }
  .tabs {
    display: flex;
    gap: 6px;
    margin-bottom: 10px;
  }
  .tabs button.on {
    border-color: var(--accent);
    color: var(--accent);
  }
  iframe {
    width: 100%;
    height: calc(100vh - 250px);
    min-height: 520px;
    border: 1px solid var(--line);
    border-radius: var(--radius);
    background: #111827;
  }
</style>
