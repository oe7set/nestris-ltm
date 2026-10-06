<script lang="ts">
  // One element of an own layout (layout builder), filling its box w x h.
  import { NextPiece } from "@nestris-ltm/nes";
  import { boardCell, fitFont, heartPixel } from "../lib/fit";
  import { fmt, hud, pct, text, type Lang, type TextKey } from "../lib/format";
  import type { LayoutElement, StatField } from "../lib/layoutdef";
  import { look } from "../lib/look.svelte";
  import { scene } from "../lib/scene.svelte";
  import type { SceneState } from "../lib/types";
  import type { SlotView } from "../lib/view";
  import Board from "./Board.svelte";
  import Camera from "./Camera.svelte";
  import DiffGraph from "./DiffGraph.svelte";
  import Hearts from "./Hearts.svelte";
  import Num from "./Num.svelte";
  import Versus from "./Versus.svelte";

  interface Props {
    el: LayoutElement;
    state: SceneState;
    views: SlotView[];
    lang: Lang;
  }
  let { el, state, views, lang }: Props = $props();

  const p = $derived((el.props ?? {}) as Record<string, unknown>);
  const view = $derived(el.slot !== null && el.slot !== undefined ? views[el.slot] : undefined);
  const pair = $derived(
    el.pair !== null && el.pair !== undefined ? state.scene.pairs[el.pair] : undefined,
  );
  const align = $derived((p.align as string | undefined) ?? "left");
  const nes = $derived(look.nes);

  // ---- stat
  const field = $derived((p.field as StatField | undefined) ?? "score");
  const statLabel = $derived(
    (p.label as string | undefined) ?? hud(lang, (field === "drought" ? "drought" : field) as TextKey),
  );
  const gap = $derived(view?.vs_partner);
  const statValue = $derived.by((): string => {
    const v = view;
    if (!v) return "–";
    switch (field) {
      case "score": return fmt(v.score);
      case "lines": return fmt(v.lines);
      case "level": return fmt(v.level);
      case "start_level": return fmt(v.start_level);
      case "trt": return pct(v.tetris_rate);
      case "drought": return v.status === "playing" ? fmt(v.drought) : fmt(v.max_drought);
      case "burn": return fmt(v.burn);
      case "pace": return fmt(v.pace);
      case "pieces": return fmt(v.pieces);
      case "gap": return gap && gap.points !== 0 ? (gap.points < 0 ? "+" : "−") + fmt(Math.abs(gap.points)) : "±0";
    }
  });
  const showLabel = $derived(p.show_label !== false);
  const labelPx = $derived(fitFont(statLabel.length, el.w - 16, el.h, showLabel ? 0.26 : 0, nes));
  const valuePx = $derived(fitFont(Math.max(statValue.length, 3), el.w - 16, el.h, showLabel ? 0.5 : 0.7, nes));

  // ---- names, title, round, text
  const name = $derived(view?.name ?? `Slot ${(el.slot ?? 0) + 1}`);
  const roundOf = $derived.by((): number => {
    if (el.pair !== null && el.pair !== undefined) {
      return state.groups?.find((g) => g.group === el.pair)?.round ?? state.round;
    }
    return state.round;
  });
  const roundText = $derived(`${text(lang, "round")} ${roundOf}`);
  const titleText = $derived(
    (p.text as string | undefined) ?? state.scene.settings.title ?? state.matches?.[0]?.round_name ?? state.scene.name,
  );
  const hearts = $derived(view?.lives);

  // ---- next piece: label on top, the piece in the rest of the box
  const nextLabelPx = $derived(p.show_label !== false ? fitFont(4, el.w - 24, el.h, 0.22, nes) : 0);
  const nextCell = $derived(
    Math.max(4, Math.floor(Math.min((el.w - 28) / 4, (el.h - 24 - nextLabelPx - (nextLabelPx ? 6 : 0)) / 2))),
  );
</script>

<div class="w {el.type} a-{align}" class:nes data-type={el.type}>
  {#if el.type === "board" && view}
    <div class="center">
      <Board {view} cell={boardCell(el.w, el.h)} {lang} showNext={false} />
    </div>
  {:else if el.type === "next" && view}
    <div class="wbox col next">
      {#if nextLabelPx}
        <span class="label" style:font-size="{nextLabelPx}px">{hud(lang, "next")}</span>
      {/if}
      <NextPiece piece={view.next_piece} level={view.level} cell={nextCell} />
    </div>
  {:else if el.type === "stat"}
    <div class="wbox col stat" class:ahead={field === "gap" && (gap?.points ?? 0) < 0} class:behind={field === "gap" && (gap?.points ?? 0) > 0}>
      {#if showLabel}<span class="label" style:font-size="{labelPx}px">{statLabel}</span>{/if}
      <b class="value" style:font-size="{valuePx}px" style:color={(p.color as string | undefined) ?? null}>
        {#if field === "score" && view}<Num value={view.score} />{:else}{statValue}{/if}
      </b>
    </div>
  {:else if el.type === "name"}
    <div class="wbox row name">
      {#if p.show_rank && view?.rank}<span class="rank">{view.rank}</span>{/if}
      <span class="nick" style:font-size="{fitFont(name.length + (p.show_rank ? 2 : 0), el.w - 24, el.h, 0.55, nes)}px">{name}</span>
    </div>
  {:else if el.type === "hearts"}
    {#if hearts}
      <div class="row hearts-row"><Hearts current={hearts.current} max={hearts.max} size={heartPixel(hearts.max, el.w, el.h)} align={align === "right" ? "right" : "left"} /></div>
    {/if}
  {:else if el.type === "nametag"}
    <div class="wbox col nametag" class:won={view?.match_result === "won"} class:lost={view?.match_result === "lost"}>
      <span class="nick" style:font-size="{fitFont(name.length, el.w - 24, el.h, hearts ? 0.34 : 0.55, nes)}px">{name}</span>
      {#if hearts}
        <span class="row">
          <Hearts current={hearts.current} max={hearts.max} size={heartPixel(hearts.max, el.w * 0.6, el.h * 0.32)} />
          {#if view?.match_result}<span class="result {view.match_result}">{text(lang, view.match_result === "won" ? "winner" : "eliminated")}</span>{/if}
        </span>
      {/if}
      {#if p.show_round}<span class="small">{roundText}</span>{/if}
    </div>
  {:else if el.type === "camera"}
    <Camera width={el.w} height={el.h} framed={p.framed !== false} />
  {:else if el.type === "versus" && pair && views[pair[0]] && views[pair[1]]}
    <div class="fit-versus" style:--w="{el.w}px">
      <Versus a={views[pair[0]]!} b={views[pair[1]]!} {lang} />
    </div>
  {:else if el.type === "diff_graph" && pair}
    <div class="wbox graph">
      <DiffGraph a={scene.history[String(pair[0])]} b={scene.history[String(pair[1])]} width={Math.max(10, el.w - 12)} height={Math.max(10, el.h - 12)} />
    </div>
  {:else if el.type === "title"}
    <div class="wbox row title"><span style:font-size="{fitFont(titleText.length, el.w - 24, el.h, 0.5, nes)}px">{titleText}</span></div>
  {:else if el.type === "round"}
    <div class="wbox row round"><span style:font-size="{fitFont(roundText.length, el.w - 24, el.h, 0.45, nes)}px">{roundText}</span></div>
  {:else if el.type === "text"}
    <div class="row free" style:font-size="{nes ? Math.max(8, Math.floor(Number(p.size ?? 24) / 8) * 8) : Number(p.size ?? 24)}px" style:color={(p.color as string | undefined) ?? null}>
      {String(p.text ?? "")}
    </div>
  {:else if el.type === "frame"}
    <div class="wbox" class:panel={p.style === "panel"}></div>
  {/if}
</div>

<style>
  .w {
    position: absolute;
    inset: 0;
    display: flex;
    min-width: 0;
    min-height: 0;
    overflow: hidden;
    color: var(--text);
  }
  .wbox {
    flex: 1;
    min-width: 0;
    min-height: 0;
    background: var(--panel);
    border: 2px solid var(--frame);
    border-radius: 8px;
    padding: 6px 10px;
    box-sizing: border-box;
    overflow: hidden;
  }
  .col {
    display: flex;
    flex-direction: column;
    justify-content: center;
    gap: 4px;
  }
  .row {
    display: flex;
    align-items: center;
    gap: 10px;
    flex: 1;
    min-width: 0;
  }
  .center {
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: center;
  }
  .a-center .col,
  .a-center .row,
  .a-center.nametag .col {
    align-items: center;
    justify-content: center;
    text-align: center;
  }
  .a-right .col {
    align-items: flex-end;
    text-align: right;
  }
  .a-right .row {
    justify-content: flex-end;
  }
  .nametag,
  .next {
    align-items: center;
    text-align: center;
  }
  .label {
    color: var(--muted);
    letter-spacing: 1px;
    line-height: 1;
    white-space: nowrap;
  }
  .nes .label {
    color: var(--text);
    letter-spacing: 0;
  }
  .value {
    font-weight: 400;
    line-height: 1.05;
    white-space: nowrap;
    font-variant-numeric: tabular-nums;
  }
  .ahead .value {
    color: var(--good);
  }
  .behind .value {
    color: var(--bad);
  }
  .nick {
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    line-height: 1.1;
  }
  .lost .nick {
    opacity: 0.55;
  }
  .won {
    border-color: var(--accent);
  }
  .rank {
    display: grid;
    place-items: center;
    min-width: 1.6em;
    padding: 2px 6px;
    background: var(--frame);
    border-radius: 4px;
  }
  .result {
    font-size: 14px;
    padding: 3px 6px;
    color: #000;
    background: var(--accent);
  }
  .result.lost {
    background: var(--bad);
    color: #fff;
  }
  .small {
    font-size: 14px;
    color: var(--muted);
  }
  .title span {
    color: var(--accent);
    white-space: nowrap;
  }
  .round span {
    white-space: nowrap;
  }
  .row.title,
  .row.round {
    justify-content: center;
  }
  .free {
    white-space: pre-wrap;
    line-height: 1.2;
    align-items: flex-start;
  }
  .a-center .free {
    justify-content: center;
    text-align: center;
  }
  .a-right .free {
    justify-content: flex-end;
    text-align: right;
  }
  .panel {
    background: var(--panel);
  }
  .graph {
    padding: 4px;
    display: flex;
    align-items: center;
    justify-content: center;
  }
  .fit-versus {
    width: var(--w);
  }
  .fit-versus :global(.versus) {
    height: 100%;
    box-sizing: border-box;
  }
  .hearts-row {
    justify-content: flex-start;
  }
  .a-center .hearts-row {
    justify-content: center;
  }
  .a-right .hearts-row {
    justify-content: flex-end;
  }
</style>
