<script lang="ts">
  // Guide lines over a 16:9 stage preview (scene editor, layout builder):
  // centre cross, thirds, safe areas and own lines. Own lines are dragged out
  // of the rulers (top ruler = horizontal line, left ruler = vertical line),
  // moved by dragging, removed by dragging them back onto a ruler or by a
  // double click. Only the rulers and the lines take the mouse; everything
  // else goes through to the preview / builder below.
  import { snapToGrid, type Guide } from "../lib/editor/geometry";
  import { guides, MAX_GUIDES } from "../lib/guides.svelte";
  import { t } from "../lib/i18n.svelte";

  const W = 1920;
  const H = 1080;
  const RULER = 16; // screen px

  let box = $state<HTMLDivElement | null>(null);
  let width = $state(0);
  const scale = $derived(width > 0 ? width / W : 1);

  let drag: { index: number } | null = null;
  let live = $state<Guide | null>(null); // the line being dragged (for its label)

  function stagePoint(e: PointerEvent): { x: number; y: number; sx: number; sy: number } {
    const r = box!.getBoundingClientRect();
    const sx = e.clientX - r.left;
    const sy = e.clientY - r.top;
    return { x: sx / scale, y: sy / scale, sx, sy };
  }

  function position(axis: "x" | "y", e: PointerEvent): number {
    const p = stagePoint(e);
    const v = axis === "x" ? p.x : p.y;
    const max = axis === "x" ? W : H;
    return Math.min(Math.max(e.altKey ? Math.round(v) : snapToGrid(v), 0), max);
  }

  function start(e: PointerEvent, index: number): void {
    e.stopPropagation();
    e.preventDefault();
    try {
      (e.currentTarget as Element).setPointerCapture(e.pointerId);
    } catch {
      // ignore
    }
    drag = { index };
    live = guides.custom[index] ?? null;
  }

  function fromRuler(e: PointerEvent, axis: "x" | "y"): void {
    if (e.button !== 0 || guides.custom.length >= MAX_GUIDES) return;
    const guide: Guide = { axis, at: position(axis, e) };
    guides.setCustom([...guides.custom, guide]);
    start(e, guides.custom.length - 1);
  }

  function move(e: PointerEvent): void {
    if (!drag) return;
    const g = guides.custom[drag.index];
    if (!g) return;
    const next = { axis: g.axis, at: position(g.axis, e) };
    live = next;
    guides.custom = guides.custom.map((x, i) => (i === drag!.index ? next : x));
  }

  function end(e: PointerEvent): void {
    if (!drag) return;
    const g = guides.custom[drag.index];
    const p = stagePoint(e);
    // Dropped onto its ruler (or off the stage): remove it.
    const gone = g && (g.axis === "y" ? p.sy < RULER || p.sy > H * scale : p.sx < RULER || p.sx > W * scale);
    guides.setCustom(gone ? guides.custom.filter((_, i) => i !== drag!.index) : guides.custom);
    drag = null;
    live = null;
  }

  function remove(index: number): void {
    guides.setCustom(guides.custom.filter((_, i) => i !== index));
  }
</script>

{#if guides.visible}
  <div class="guides" bind:this={box} bind:clientWidth={width} style:--s={scale}>
    <div class="inner" style:transform="scale({scale})">
      {#if guides.safe}
        <div class="safe action" title={t("guides.safe")}></div>
        <div class="safe title"></div>
      {/if}
      {#if guides.thirds}
        {#each [640, 1280] as x (x)}<div class="line fixed x" style:left="{x}px"></div>{/each}
        {#each [360, 720] as y (y)}<div class="line fixed y" style:top="{y}px"></div>{/each}
      {/if}
      {#if guides.center}
        <div class="line center x" style:left="960px"></div>
        <div class="line center y" style:top="540px"></div>
      {/if}
      {#each guides.custom as g, i (i)}
        <div
          class="line own {g.axis}"
          style:left={g.axis === "x" ? `${g.at}px` : "0"}
          style:top={g.axis === "y" ? `${g.at}px` : "0"}
          role="separator"
          aria-orientation={g.axis === "x" ? "vertical" : "horizontal"}
          aria-valuenow={g.at}
          title={t("guides.own_hint")}
          onpointerdown={(e) => start(e, i)}
          onpointermove={move}
          onpointerup={end}
          onpointercancel={end}
          ondblclick={() => remove(i)}
        ></div>
      {/each}
    </div>
    {#if live}
      <span
        class="readout"
        style:left={live.axis === "x" ? `${live.at * scale + 6}px` : `${RULER + 4}px`}
        style:top={live.axis === "y" ? `${live.at * scale + 4}px` : `${RULER + 4}px`}
      >
        {live.axis === "x" ? "x" : "y"} = {live.at}
      </span>
    {/if}
    <div
      class="ruler top"
      title={t("guides.ruler_top")}
      role="presentation"
      onpointerdown={(e) => fromRuler(e, "y")}
      onpointermove={move}
      onpointerup={end}
      onpointercancel={end}
    ></div>
    <div
      class="ruler left"
      title={t("guides.ruler_left")}
      role="presentation"
      onpointerdown={(e) => fromRuler(e, "x")}
      onpointermove={move}
      onpointerup={end}
      onpointercancel={end}
    ></div>
  </div>
{/if}

<style>
  .guides {
    position: absolute;
    inset: 0;
    pointer-events: none;
    overflow: hidden;
    z-index: 5;
  }
  .inner {
    position: absolute;
    left: 0;
    top: 0;
    width: 1920px;
    height: 1080px;
    transform-origin: 0 0;
  }
  .line {
    position: absolute;
  }
  .line.x {
    top: 0;
    height: 1080px;
    width: calc(1px / var(--s));
  }
  .line.y {
    left: 0;
    width: 1920px;
    height: calc(1px / var(--s));
  }
  .line.center {
    background: rgb(0 229 255 / 0.85);
  }
  .line.fixed {
    background: rgb(0 229 255 / 0.4);
  }
  /* Own lines: a transparent 9 px grab area with the 1 px line in its middle. */
  .line.own {
    pointer-events: auto;
    background: none;
  }
  .line.own::after {
    content: "";
    position: absolute;
    background: #00e5ff;
  }
  .line.own.x {
    width: calc(9px / var(--s));
    margin-left: calc(-4px / var(--s));
    cursor: ew-resize;
  }
  .line.own.x::after {
    left: calc(4px / var(--s));
    top: 0;
    bottom: 0;
    width: calc(1px / var(--s));
  }
  .line.own.y {
    height: calc(9px / var(--s));
    margin-top: calc(-4px / var(--s));
    cursor: ns-resize;
  }
  .line.own.y::after {
    top: calc(4px / var(--s));
    left: 0;
    right: 0;
    height: calc(1px / var(--s));
  }
  .safe {
    position: absolute;
    border: calc(1px / var(--s)) dashed rgb(0 229 255 / 0.55);
  }
  .safe.action {
    left: 96px;
    top: 54px;
    width: 1728px;
    height: 972px;
  }
  .safe.title {
    left: 192px;
    top: 108px;
    width: 1536px;
    height: 864px;
    border-color: rgb(255 214 0 / 0.5);
  }
  .ruler {
    position: absolute;
    pointer-events: auto;
    background:
      repeating-linear-gradient(var(--dir), rgb(255 255 255 / 0.35) 0 1px, transparent 1px 10px),
      rgb(8 12 24 / 0.75);
  }
  .ruler.top {
    --dir: to right;
    left: 0;
    right: 0;
    top: 0;
    height: 16px;
    cursor: ns-resize;
  }
  .ruler.left {
    --dir: to bottom;
    left: 0;
    top: 0;
    bottom: 0;
    width: 16px;
    cursor: ew-resize;
  }
  .readout {
    position: absolute;
    padding: 1px 6px;
    font: 600 11px/1.4 system-ui, sans-serif;
    color: #000;
    background: #00e5ff;
    border-radius: 3px;
    pointer-events: none;
    white-space: nowrap;
  }
</style>
