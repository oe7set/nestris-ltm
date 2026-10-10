<script lang="ts">
  // Tournament: where it stands (qualifying / fixed, FIX right here), the
  // bracket (the console ported from TournamentHigscore: players, size,
  // click-to-win) and the hearts of the 1-vs-1 matches. The highscore
  // display's settings are in Einstellungen → Highscore-Anzeige.
  //
  // The bracket gets the room: the help is folded away, the console fills the
  // window down to its bottom edge, and focus mode hides everything else
  // (admin sidebar included, see App.svelte); full screen goes one step further.
  import MatchesPanel from "../components/MatchesPanel.svelte";
  import PhaseBanner from "../components/PhaseBanner.svelte";
  import { fillHeight } from "../lib/fillHeight";
  import { t } from "../lib/i18n.svelte";
  import { router } from "../lib/router.svelte";
  import { uiPrefs } from "../lib/uiPrefs.svelte";

  type Tab = "bracket" | "matches";
  let tab = $state<Tab>(router.current.query.get("tab") === "matches" ? "matches" : "bracket");
  let frameBox = $state<HTMLElement>();

  const focus = $derived(uiPrefs.tournamentFocus && tab === "bracket");

  function setTab(next: Tab): void {
    tab = next;
    router.setQuery({ tab: next === "bracket" ? null : next });
  }

  function fullscreen(): void {
    void frameBox?.requestFullscreen?.().catch(() => {});
  }

  function onkeydown(e: KeyboardEvent): void {
    if (e.key === "Escape" && uiPrefs.tournamentFocus && !document.fullscreenElement) {
      uiPrefs.toggle("tournamentFocus");
    }
  }
</script>

<svelte:window {onkeydown} />

{#if !focus}
  <div class="head row">
    <h1>{t("tournament.title")}</h1>
    <span class="spacer"></span>
    <a class="button" href="/view/highscore" target="_blank" rel="noopener">{t("tournament.open_view")} ↗</a>
    <a class="button" href="/view/tournament-admin" target="_blank" rel="noopener">{t("tournament.fullscreen")} ↗</a>
  </div>
{/if}

{#snippet tools()}
  <button
    class:on={uiPrefs.tournamentHelp}
    aria-expanded={uiPrefs.tournamentHelp}
    onclick={() => uiPrefs.toggle("tournamentHelp")}>? {t("tournament.help_toggle")}</button
  >
  <button class:on={focus} title={t("tournament.focus_title")} onclick={() => uiPrefs.toggle("tournamentFocus")}>
    {focus ? t("tournament.focus_end") : t("tournament.focus")}
  </button>
  <button onclick={fullscreen}>⛶ {t("tournament.fullscreen_now")}</button>
{/snippet}

{#if focus}
  <!-- One slim line: phase (FIX stays reachable) and the tools. -->
  <div class="focus-bar">
    <div class="phase"><PhaseBanner compact link={false} /></div>
    {@render tools()}
  </div>
{:else}
  <PhaseBanner />
  <div class="tabs row">
    <button class:on={tab === "bracket"} onclick={() => setTab("bracket")}>{t("tournament.tab_bracket")}</button>
    <button class:on={tab === "matches"} onclick={() => setTab("matches")}>{t("tournament.tab_matches")}</button>
    {#if tab === "bracket"}
      <span class="spacer"></span>
      {@render tools()}
    {/if}
  </div>
{/if}

{#if tab === "bracket"}
  {#if uiPrefs.tournamentHelp}
    <div class="help panel small">
      <p>{t("tournament.hint")}</p>
      <p>{t("tournament.console_hint")}</p>
    </div>
  {/if}
  <div class="frame fill-page" bind:this={frameBox} use:fillHeight>
    <iframe src="/view/tournament-admin?embedded=1" title={t("tournament.title")}></iframe>
  </div>
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
    gap: 6px;
    margin-bottom: 8px;
  }
  .tabs button.on,
  .focus-bar button.on {
    border-color: var(--accent);
    color: var(--accent);
  }
  .focus-bar {
    display: flex;
    align-items: center;
    gap: 6px;
    margin-bottom: 8px;
  }
  .focus-bar .phase {
    flex: 1;
    min-width: 0;
  }
  .focus-bar .phase :global(.banner) {
    margin: 0;
    flex-wrap: nowrap;
  }
  .help {
    margin-bottom: 8px;
    color: var(--muted);
  }
  .help p {
    margin: 0 0 6px;
  }
  .help p:last-child {
    margin: 0;
  }
  .frame {
    height: var(--fill-h, calc(100vh - 160px));
    min-height: 420px;
  }
  .frame:fullscreen {
    height: 100%;
  }
  iframe {
    display: block;
    width: 100%;
    height: 100%;
    border: 1px solid var(--line);
    border-radius: var(--radius);
    background: #111827;
  }
  .frame:fullscreen iframe {
    border: none;
    border-radius: 0;
  }
</style>
