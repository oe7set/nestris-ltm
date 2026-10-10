<script lang="ts">
  // Results of the active event: podium (once the bracket is decided), the
  // full highscore, exports and a print layout (Strg+P prints this page
  // without menu and buttons).
  import { onMount } from "svelte";
  import ErrorBox from "../components/ErrorBox.svelte";
  import { api } from "../lib/api";
  import { dateTime, num, pct } from "../lib/format";
  import { i18n, t } from "../lib/i18n.svelte";
  import { errorText } from "../lib/toast.svelte";

  interface Entry {
    rank: number;
    user_id: number;
    nickname: string;
    score: number;
    lines: number | null;
    level: number | null;
    tetris_rate: number | null;
    game_id: number | null;
  }
  interface ResultsData {
    event: { id: number; name: string; starts_at: string; ends_at: string | null } | null;
    leaderboard: Entry[];
    stats: { total_games?: number; total_score?: number; players?: number } & Record<string, unknown>;
    podium: { champion: string | null; runner_up: string | null; third: string | null } | null;
  }

  let data = $state<ResultsData | null>(null);
  let error = $state<string | null>(null);
  let withContact = $state(false);

  async function load(): Promise<void> {
    try {
      data = await api<ResultsData>("/api/results");
      error = null;
    } catch (e) {
      error = errorText(e);
    }
  }

  onMount(() => {
    void load();
  });
</script>

<div class="row head no-print">
  <h1>{t("results.title")}</h1>
  <span class="spacer"></span>
  <button class="primary" onclick={() => window.print()}>🖶 {t("results.print")}</button>
</div>

{#if error}
  <ErrorBox text={error} onretry={load} />
{:else if !data}
  <p class="muted">{t("common.loading")}</p>
{:else}
  <section class="panel exports no-print">
    <h2>{t("results.exports")}</h2>
    <div class="row">
      <a class="button" href="/api/export/highscore.csv" download>CSV {t("results.highscore")}</a>
      <a class="button" href="/api/export/games.csv" download>CSV {t("nav.games")}</a>
      <a class="button" href={`/api/export/players.csv${withContact ? "?contact=true" : ""}`} download>CSV {t("nav.players")}</a>
      <label class="check small">
        <input type="checkbox" bind:checked={withContact} />
        {t("results.with_contact")}
      </label>
    </div>
    <p class="hint">{t("results.exports_hint")}</p>
    <p class="small">
      <a href="/view/tournament-admin" target="_blank" rel="noopener">{t("results.print_bracket")} ↗</a>
    </p>
  </section>

  <header class="print-head">
    <h1>{data.event?.name ?? t("results.no_event")}</h1>
    {#if data.event}
      <p class="muted">{dateTime(data.event.starts_at, i18n.locale)}{data.event.ends_at ? ` – ${dateTime(data.event.ends_at, i18n.locale)}` : ""}</p>
    {/if}
  </header>

  {#if data.podium && (data.podium.champion || data.podium.runner_up || data.podium.third)}
    <section class="podium">
      {#each [["champion", "🏆"], ["runner_up", "🥈"], ["third", "🥉"]] as [place, icon] (place)}
        {@const name = data.podium[place as "champion" | "runner_up" | "third"]}
        <div class="panel place {place}">
          <span class="icon" aria-hidden="true">{icon}</span>
          <span class="muted small">{t(`results.${place}` as "results.champion")}</span>
          <strong>{name ?? "–"}</strong>
        </div>
      {/each}
    </section>
  {/if}

  <h2>{t("results.highscore")}</h2>
  <div class="table-wrap">
    <table class="table-cards">
      <thead>
        <tr>
          <th class="num">#</th>
          <th>{t("games.player")}</th>
          <th class="num">{t("games.score")}</th>
          <th class="num">{t("games.lines")}</th>
          <th class="num">{t("games.levels")}</th>
          <th class="num">{t("games.trt")}</th>
        </tr>
      </thead>
      <tbody>
        {#each data.leaderboard as e (e.user_id)}
          <tr>
            <td class="num card-sub" data-label="#">{e.rank}.</td>
            <td class="card-title" data-label={t("games.player")}>
              <a href={`#/players/${e.user_id}`}>{e.nickname}</a>
            </td>
            <td class="num card-score" data-label={t("games.score")}><strong>{num(e.score, i18n.locale)}</strong></td>
            <td class="num" data-label={t("games.lines")}>{num(e.lines, i18n.locale)}</td>
            <td class="num" data-label={t("games.levels")}>{e.level ?? "–"}</td>
            <td class="num" data-label={t("games.trt")}>{pct(e.tetris_rate, i18n.locale)}</td>
          </tr>
        {:else}
          <tr><td colspan="6" class="empty">{t("results.none")}</td></tr>
        {/each}
      </tbody>
    </table>
  </div>
  <p class="muted small print-foot">NestrisLTM · {dateTime(new Date().toISOString(), i18n.locale)}</p>
{/if}

<style>
  .exports {
    margin-bottom: 16px;
  }
  .exports .row {
    gap: 8px 12px;
  }
  .print-head {
    display: none;
  }
  .podium {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 12px;
    margin-bottom: 16px;
  }
  .place {
    display: grid;
    justify-items: center;
    gap: 4px;
    text-align: center;
  }
  .place .icon {
    font-size: 32px;
  }
  .place strong {
    font-size: 20px;
  }
  .place.champion {
    border-color: var(--accent);
  }
  .print-foot {
    display: none;
  }
  @media print {
    .print-head,
    .print-foot {
      display: block;
    }
    .print-head h1 {
      margin: 0;
    }
  }
</style>
