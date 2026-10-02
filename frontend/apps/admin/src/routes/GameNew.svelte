<script lang="ts">
  import PlayerPicker from "../components/PlayerPicker.svelte";
  import { api } from "../lib/api";
  import { fromLocalInput, toLocalInput } from "../lib/format";
  import { t } from "../lib/i18n.svelte";
  import { router } from "../lib/router.svelte";
  import { toasts } from "../lib/toast.svelte";
  import type { Game } from "../lib/types";

  let playerId = $state<number | null>(null);
  let score = $state<number | null>(null);
  let lines = $state<number | null>(null);
  let startLevel = $state<number | null>(18);
  let endLevel = $state<number | null>(null);
  let startedAt = $state(toLocalInput(new Date().toISOString()));
  let notes = $state("");
  let busy = $state(false);

  async function submit(event: SubmitEvent): Promise<void> {
    event.preventDefault();
    if (playerId === null || score === null) return;
    busy = true;
    try {
      const game = await api<Game>("/api/games", {
        method: "POST",
        body: {
          player_id: playerId,
          score,
          lines,
          start_level: startLevel,
          end_level: endLevel,
          started_at: fromLocalInput(startedAt),
          notes: notes.trim() || null,
        },
      });
      toasts.ok(t("common.saved"));
      router.go(`/games/${game.id}`);
    } catch (e) {
      toasts.error(e);
    } finally {
      busy = false;
    }
  }
</script>

<p><a href="#/games">‹ {t("games.title")}</a></p>
<h1>{t("game.create_title")}</h1>
<p class="hint">{t("game.create_hint")}</p>

<form class="panel grid" onsubmit={submit}>
  <div class="form-grid">
    <div class="field-like">
      <span class="muted small">{t("games.player")} *</span>
      <PlayerPicker value={playerId} onselect={(p) => (playerId = p.id)} />
    </div>
    <label class="field">{t("games.score")} *<input type="number" min="0" max="9999999" bind:value={score} required /></label>
    <label class="field">{t("games.lines")}<input type="number" min="0" max="9999" bind:value={lines} /></label>
    <label class="field">{t("game.start_level")}<input type="number" min="0" max="29" bind:value={startLevel} /></label>
    <label class="field">{t("game.end_level")}<input type="number" min="0" max="255" bind:value={endLevel} /></label>
    <label class="field">{t("game.started_at")}<input type="datetime-local" bind:value={startedAt} /></label>
  </div>
  <label class="field">{t("common.notes")}<textarea bind:value={notes}></textarea></label>
  <div class="row">
    <span class="spacer"></span>
    <button class="primary" type="submit" disabled={busy || playerId === null || score === null}>{t("common.save")}</button>
  </div>
</form>

<style>
  .field-like {
    display: grid;
    gap: 4px;
  }
</style>
