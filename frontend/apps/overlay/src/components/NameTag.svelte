<script lang="ts">
  // Name box above a player's camera: nickname, hearts, match result, round.
  import { text, type Lang } from "../lib/format";
  import type { SlotView } from "../lib/view";
  import Hearts from "./Hearts.svelte";

  interface Props {
    view: SlotView;
    lang?: Lang;
    align?: "left" | "right";
    compact?: boolean;
    showRound?: boolean;
  }
  let { view, lang = "de", align = "left", compact = false, showRound = false }: Props = $props();
</script>

<div class="tag {align}" class:compact class:won={view.match_result === "won"} class:lost={view.match_result === "lost"}>
  <span class="nick">{view.name ?? "—"}</span>
  <span class="extra">
    {#if view.match_result}
      <span class="result {view.match_result}">{text(lang, view.match_result === "won" ? "winner" : "eliminated")}</span>
    {/if}
    {#if view.lives}
      <Hearts current={view.lives.current} max={view.lives.max} size={compact ? 2 : 3} {align} />
    {/if}
    {#if showRound && view.round}<span class="round">{text(lang, "round")} {view.round}</span>{/if}
  </span>
</div>

<style>
  .tag {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 14px;
    padding: 10px 16px;
    background: var(--panel);
    border: 2px solid var(--frame);
    border-radius: 8px;
    min-width: 0;
  }
  .tag.right {
    flex-direction: row-reverse;
  }
  .tag.won {
    border-color: var(--accent);
  }
  .tag.lost .nick {
    opacity: 0.55;
  }
  .nick {
    font-size: 32px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    min-width: 0;
  }
  .compact {
    padding: 6px 12px;
  }
  .compact .nick {
    font-size: 24px;
  }
  .extra {
    display: flex;
    align-items: center;
    gap: 10px;
    flex: none;
  }
  .right .extra {
    flex-direction: row-reverse;
  }
  .result {
    font-size: 15px;
    letter-spacing: 2px;
    padding: 3px 8px;
    border-radius: 4px;
    color: #000;
  }
  .result.won {
    background: var(--accent);
  }
  .result.lost {
    background: #e8203a;
    color: #fff;
  }
  .round {
    font-size: 14px;
    letter-spacing: 2px;
    color: var(--muted);
  }
</style>
