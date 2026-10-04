<script lang="ts">
  import { untrack } from "svelte";
  // Playfield with frame, NEXT box, status overlays and the tetris flash.
  import { hud, text, type Lang } from "../lib/format";
  import { clearedLines, type SlotView } from "../lib/view";
  import { NextPiece, Playfield } from "@nestris-ltm/nes";

  interface Props {
    view: SlotView;
    cell?: number;
    lang?: Lang;
    showNext?: boolean;
    nextSide?: "left" | "right";
  }
  let { view, cell = 32, lang = "de", showNext = true, nextSide = "right" }: Props = $props();

  let flash = $state(0); // increments on every tetris -> restarts the animation
  let prevLines: number | null = null;

  $effect(() => {
    const lines = view.lines;
    if (view.status === "playing" && clearedLines(prevLines, lines) === 4) {
      untrack(() => (flash += 1));
    }
    prevLines = lines ?? null;
  });

  const overlay = $derived(
    view.status === "waiting"
      ? text(lang, "waiting")
      : view.paused
        ? text(lang, "paused")
        : null,
  );
</script>

<div class="board" class:mirror={nextSide === "left"} style:--cell="{cell}px">
  <div class="well">
    <Playfield
      rows={view.frame?.playfield}
      level={view.level}
      {cell}
      dim={view.status === "finished" || view.status === "waiting"}
    />
    {#key flash}
      {#if flash > 0}<div class="flash"></div>{/if}
    {/key}
    {#if overlay}<div class="overlay">{overlay}</div>{/if}
    {#if view.outcome}
      <div class="stamp {view.outcome}">{text(lang, view.outcome)}</div>
    {:else if view.status === "finished"}
      <div class="stamp done">{text(lang, "finished")}</div>
    {/if}
  </div>
  {#if showNext}
    <div class="next">
      <span>{hud(lang, "next")}</span>
      <NextPiece piece={view.next_piece} level={view.level} cell={Math.round(cell * 0.75)} />
    </div>
  {/if}
</div>

<style>
  .board {
    display: flex;
    gap: 10px;
    align-items: flex-start;
  }
  .board.mirror {
    flex-direction: row-reverse;
  }
  .well {
    position: relative;
    padding: calc(var(--cell) / 4);
    background: var(--well-bg);
    border: 3px solid var(--frame);
    border-radius: 6px;
    box-shadow: 0 0 0 2px #000a, 0 10px 30px #0008;
    overflow: hidden;
  }
  .next {
    display: grid;
    gap: 6px;
    justify-items: center;
    padding: 10px 8px;
    background: var(--panel);
    border: 2px solid var(--frame);
    border-radius: 6px;
    min-width: calc(var(--cell) * 3.4);
  }
  .next span {
    font-size: 14px;
    letter-spacing: 2px;
    color: var(--muted);
  }
  .overlay {
    position: absolute;
    inset: 0;
    display: grid;
    place-items: center;
    font-size: calc(var(--cell) * 0.8);
    letter-spacing: 4px;
    color: var(--muted);
    text-shadow: 0 2px 8px #000;
  }
  .flash {
    position: absolute;
    inset: 0;
    background: #fff;
    pointer-events: none;
    animation: tetris-flash 0.6s steps(6) forwards;
  }
  @keyframes tetris-flash {
    0%, 33%, 67% { opacity: 0.85; }
    17%, 50%, 83% { opacity: 0; }
    100% { opacity: 0; }
  }
  .stamp {
    position: absolute;
    left: 50%;
    top: 42%;
    transform: translate(-50%, -50%) rotate(-12deg);
    padding: 6px 18px;
    border: 4px solid currentColor;
    border-radius: 8px;
    font-size: calc(var(--cell) * 0.95);
    font-weight: 700;
    letter-spacing: 4px;
    background: #000c;
    animation: stamp-in 0.45s cubic-bezier(0.2, 1.6, 0.4, 1) both;
    white-space: nowrap;
  }
  .stamp.advanced { color: var(--good); }
  .stamp.winner { color: var(--accent); }
  .stamp.eliminated { color: var(--bad); }
  .stamp.done { color: var(--muted); font-size: calc(var(--cell) * 0.7); }
  @keyframes stamp-in {
    from { transform: translate(-50%, -50%) rotate(-12deg) scale(2.4); opacity: 0; }
  }
</style>
