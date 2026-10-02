<script lang="ts">
  // The tournament console ported from TournamentHigscore (bracket with
  // click-to-win, FLIP animations, display remote control) runs as its own
  // page; it is embedded here so it sits inside the admin navigation.
  import { t } from "../lib/i18n.svelte";
</script>

<div class="head row">
  <h1>{t("tournament.title")}</h1>
  <span class="spacer"></span>
  <a class="button" href="/view/highscore" target="_blank" rel="noopener">{t("tournament.open_view")} ↗</a>
  <a class="button" href="/view/tournament-admin" target="_blank" rel="noopener">{t("tournament.fullscreen")} ↗</a>
</div>
<p class="hint">{t("tournament.hint")}</p>
<iframe src="/view/tournament-admin" title={t("tournament.title")}></iframe>

<style>
  .head h1 {
    margin: 0;
  }
  .head {
    margin-bottom: 6px;
  }
  iframe {
    width: 100%;
    height: calc(100vh - 140px);
    min-height: 520px;
    border: 1px solid var(--line);
    border-radius: var(--radius);
    background: #111827;
  }
</style>
