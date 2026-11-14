<script lang="ts">
  // The 1920x1080 stage of the studio, like the canvas of OBS: the overlay
  // app renders the scene (iframe with demo or live data, exactly as in OBS),
  // this component draws selection, handles and snap guides on top of it.
  // Zoom: "fit" shows the whole stage; Ctrl + mouse wheel zooms around the
  // pointer, Space or the middle mouse button + drag moves the view. The
  // status bar shows the real stage size and positions in stage pixels.
  import type { Snippet } from "svelte";
  import { CATALOGUE, inMarquee } from "../../lib/editor/elements";
  import {
    CANVAS_H,
    CANVAS_W,
    clampMove,
    fromPoints,
    HANDLES,
    resize,
    snapMove,
    bounds,
    type Guide,
    type Handle,
    type Rect,
  } from "../../lib/editor/geometry";
  import { DRAG_TYPE, rectOf, slotColor, type LayoutEditor } from "../../lib/editor/layoutEditor.svelte";
  import { updateElement } from "../../lib/editor/elements";
  import { guides as guideLines } from "../../lib/guides.svelte";
  import { t, tDynamic } from "../../lib/i18n.svelte";
  import type { ElementType, LayoutDefinition, LayoutElement, PreviewConfig } from "../../lib/studio";
  import GuideOverlay from "../GuideOverlay.svelte";
  import Thumb from "../Thumb.svelte";

  interface Props {
    editor: LayoutEditor;
    preview: PreviewConfig | null;
    background?: "dark" | "checker";
    showGrid?: boolean;
    zoom?: "fit" | number;
    /** Live data of the saved scene instead of demo data (hidden elements vanish). */
    live?: boolean;
    /** Shown over the stage (e.g. "built-in layout: adapt to move"). */
    notice?: Snippet;
  }
  let { editor, preview, background = "checker", showGrid = $bindable(false), zoom = $bindable("fit"), live = false, notice }: Props = $props();

  const PAD = 24; // screen px around the stage in "fit"
  const ZOOMS = [0.1, 0.25, 0.33, 0.5, 0.67, 0.75, 1, 1.25, 1.5, 2, 3];

  let viewW = $state(1200);
  let viewH = $state(700);
  let viewport = $state<HTMLDivElement | null>(null);
  let layer = $state<HTMLDivElement | null>(null);
  let pan = $state({ x: 0, y: 0 }); // stage origin in viewport px when zoomed
  let cursor = $state<{ x: number; y: number } | null>(null);
  let spaceDown = $state(false);
  let panning: { sx: number; sy: number; px: number; py: number } | null = null;
  let snapGuides = $state<Guide[]>([]);
  let marquee = $state<Rect | null>(null);

  const fitScale = $derived(Math.max(0.05, Math.min((viewW - 2 * PAD) / CANVAS_W, (viewH - 2 * PAD) / CANVAS_H)));
  const scale = $derived(zoom === "fit" ? fitScale : zoom);
  // In "fit" the stage is centred; zoomed, it sits where the user panned it.
  const origin = $derived(
    zoom === "fit" ? { x: (viewW - CANVAS_W * scale) / 2, y: (viewH - CANVAS_H * scale) / 2 } : pan,
  );
  const selBox = $derived(bounds(editor.sel.map(rectOf)));

  // ---- zoom and pan

  function setZoom(next: number, around?: { x: number; y: number }): void {
    const z = Math.min(4, Math.max(0.05, next));
    const at = around ?? { x: viewW / 2, y: viewH / 2 };
    const o = origin;
    // Keep the stage point under ``at`` where it is.
    const sx = (at.x - o.x) / scale;
    const sy = (at.y - o.y) / scale;
    pan = { x: at.x - sx * z, y: at.y - sy * z };
    zoom = z;
  }

  export function zoomStep(dir: 1 | -1): void {
    const current = scale;
    const next = dir > 0 ? ZOOMS.find((z) => z > current + 0.001) : [...ZOOMS].reverse().find((z) => z < current - 0.001);
    setZoom(next ?? current);
  }

  export function zoomTo(z: "fit" | number): void {
    if (z === "fit") zoom = "fit";
    else setZoom(z);
  }

  function onWheel(event: WheelEvent): void {
    if (event.ctrlKey || event.metaKey) {
      event.preventDefault();
      const r = viewport!.getBoundingClientRect();
      setZoom(scale * Math.exp(-event.deltaY * 0.0015), { x: event.clientX - r.left, y: event.clientY - r.top });
    } else if (zoom !== "fit") {
      event.preventDefault();
      pan = { x: pan.x - event.deltaX, y: pan.y - event.deltaY };
    }
  }

  // Wheel listeners from the template are passive in Svelte 5: Ctrl + wheel
  // must be able to stop the page zoom, so attach it by hand.
  $effect(() => {
    const el = viewport;
    if (!el) return;
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  });

  function startPan(event: PointerEvent): boolean {
    if (!(event.button === 1 || (event.button === 0 && spaceDown))) return false;
    event.preventDefault();
    event.stopPropagation();
    if (zoom === "fit") {
      pan = { ...origin };
      zoom = scale;
    }
    panning = { sx: event.clientX, sy: event.clientY, px: pan.x, py: pan.y };
    viewport?.setPointerCapture(event.pointerId);
    return true;
  }

  function onViewportDown(event: PointerEvent): void {
    if (startPan(event)) return;
    // A click beside the stage clears the selection.
    if (event.button === 0 && event.target === viewport && !event.shiftKey) editor.selected = [];
  }

  function onViewportMove(event: PointerEvent): void {
    if (panning) {
      pan = { x: panning.px + event.clientX - panning.sx, y: panning.py + event.clientY - panning.sy };
      return;
    }
    const r = viewport!.getBoundingClientRect();
    const x = Math.round((event.clientX - r.left - origin.x) / scale);
    const y = Math.round((event.clientY - r.top - origin.y) / scale);
    cursor = x >= 0 && y >= 0 && x <= CANVAS_W && y <= CANVAS_H ? { x, y } : null;
  }

  function onViewportUp(): void {
    panning = null;
  }

  function onKeyDown(event: KeyboardEvent): void {
    const target = event.target as HTMLElement | null;
    if (target && ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName)) return;
    if (event.key === " " && !spaceDown) {
      spaceDown = true;
      event.preventDefault();
    } else if (!event.ctrlKey && !event.metaKey && !event.altKey) {
      if (event.key === "0") zoom = "fit";
      else if (event.key === "1") setZoom(1);
      else if (event.key === "+" || event.key === "=") zoomStep(1);
      else if (event.key === "-") zoomStep(-1);
    }
  }

  function onKeyUp(event: KeyboardEvent): void {
    if (event.key === " ") spaceDown = false;
  }

  // ---- element gestures

  type Gesture =
    | { kind: "move"; start: LayoutDefinition; px: number; py: number; origin: Map<string, Rect>; box: Rect; moved: boolean; collapseTo: string | null }
    | { kind: "resize"; start: LayoutDefinition; px: number; py: number; id: string; handle: Handle; rect: Rect; moved: boolean }
    | { kind: "marquee"; px: number; py: number; base: string[] };
  let gesture: Gesture | null = null;

  function point(e: { clientX: number; clientY: number }): { x: number; y: number } {
    const r = layer!.getBoundingClientRect();
    return { x: (e.clientX - r.left) / scale, y: (e.clientY - r.top) / scale };
  }

  function others(ids: Set<string>): Rect[] {
    const rects = editor.def.elements.filter((e) => !ids.has(e.id) && !e.hidden).map(rectOf);
    // The stage edges and centre lines snap too, and shown guide lines.
    rects.push({ x: 0, y: 0, w: CANVAS_W, h: CANVAS_H });
    for (const g of guideLines.snapLines()) {
      rects.push(g.axis === "x" ? { x: g.at, y: 0, w: 0, h: CANVAS_H } : { x: 0, y: g.at, w: CANVAS_W, h: 0 });
    }
    return rects;
  }

  function capture(event: PointerEvent): void {
    try {
      layer?.setPointerCapture(event.pointerId);
    } catch {
      // pointer already gone (e.g. released during a re-render): no capture needed
    }
  }

  function onBoxDown(event: PointerEvent, el: LayoutElement): void {
    if (startPan(event)) return;
    if (event.button !== 0 || el.locked) return; // locked: the click goes through (marquee)
    event.stopPropagation();
    capture(event);
    const p = point(event);
    let collapseTo: string | null = null;
    if (event.shiftKey) {
      if (editor.selected.includes(el.id)) {
        editor.selected = editor.selected.filter((s) => s !== el.id);
        return;
      }
      editor.selected = [...editor.selected, el.id];
    } else if (!editor.selected.includes(el.id)) {
      editor.selected = [el.id];
    } else {
      collapseTo = el.id; // a click without moving selects just this one
    }
    const moving = editor.def.elements.filter((e) => editor.selected.includes(e.id) && !e.locked);
    gesture = {
      kind: "move",
      start: editor.def,
      px: p.x,
      py: p.y,
      origin: new Map(moving.map((e) => [e.id, rectOf(e)])),
      box: bounds(moving.map(rectOf)) ?? rectOf(el),
      moved: false,
      collapseTo,
    };
  }

  function onHandleDown(event: PointerEvent, el: LayoutElement, handle: Handle): void {
    if (event.button !== 0) return;
    event.stopPropagation();
    capture(event);
    const p = point(event);
    gesture = { kind: "resize", start: editor.def, px: p.x, py: p.y, id: el.id, handle, rect: rectOf(el), moved: false };
  }

  function onLayerDown(event: PointerEvent): void {
    if (startPan(event)) return;
    if (event.button !== 0) return;
    event.stopPropagation();
    capture(event);
    layer?.focus();
    const p = point(event);
    if (!event.shiftKey) editor.selected = [];
    gesture = { kind: "marquee", px: p.x, py: p.y, base: [...editor.selected] };
  }

  function onMove(event: PointerEvent): void {
    const g = gesture;
    if (!g) return;
    const p = point(event);
    const opts = { threshold: 6 / scale, grid: showGrid ? 8 : 1, free: event.altKey };
    if (g.kind === "move") {
      const raw = { dx: p.x - g.px, dy: p.y - g.py };
      if (!g.moved && Math.hypot(raw.dx, raw.dy) * scale < 3) return; // a click, not a drag
      g.moved = true;
      const snapped = snapMove(g.box, raw.dx, raw.dy, { ...opts, targets: others(new Set(g.origin.keys())) });
      const d = clampMove(g.box, snapped.dx, snapped.dy);
      snapGuides = snapped.guides;
      editor.def = {
        ...g.start,
        elements: g.start.elements.map((e) => {
          const o = g.origin.get(e.id);
          return o ? { ...e, x: o.x + d.dx, y: o.y + d.dy } : e;
        }),
      };
    } else if (g.kind === "resize") {
      g.moved = true;
      const r = resize(g.rect, g.handle, p.x - g.px, p.y - g.py, { ...opts, targets: others(new Set([g.id])) }, event.shiftKey);
      snapGuides = r.guides;
      editor.def = updateElement(g.start, g.id, r.rect);
    } else {
      marquee = fromPoints(g.px, g.py, p.x, p.y);
      const hit = marquee.w > 2 || marquee.h > 2 ? inMarquee(editor.def, marquee) : [];
      editor.selected = [...new Set([...g.base, ...hit])];
    }
  }

  function onUp(): void {
    const g = gesture;
    gesture = null;
    snapGuides = [];
    marquee = null;
    if (!g) return;
    if ((g.kind === "move" || g.kind === "resize") && g.moved) editor.commitGesture(g.start);
    else if (g.kind === "move" && !g.moved && g.collapseTo) editor.selected = [g.collapseTo];
  }

  function onDragOver(event: DragEvent): void {
    if (editor.editable && event.dataTransfer?.types.includes(DRAG_TYPE)) event.preventDefault();
  }

  function onDrop(event: DragEvent): void {
    const type = event.dataTransfer?.getData(DRAG_TYPE) as ElementType | undefined;
    if (!type || !CATALOGUE.some((c) => c.type === type)) return;
    event.preventDefault();
    const p = point(event);
    editor.add(type, p.x, p.y);
  }

  function boxLabel(e: LayoutElement): string {
    let label = tDynamic(`builder.type_${e.type}`, e.type);
    if (e.type === "stat") label = tDynamic(`builder.field_${String(e.props?.field ?? "score")}`, label);
    if (e.slot !== undefined && e.slot !== null) label += ` · S${e.slot + 1}`;
    if (e.pair !== undefined && e.pair !== null) label += ` · P${e.pair + 1}`;
    return label;
  }
</script>

<svelte:window onkeydown={onKeyDown} onkeyup={onKeyUp} />

<div class="stage-wrap">
  <div
    class="viewport {background}"
    class:pan={spaceDown}
    bind:this={viewport}
    bind:clientWidth={viewW}
    bind:clientHeight={viewH}
    onpointerdown={onViewportDown}
    onpointermove={onViewportMove}
    onpointerup={onViewportUp}
    onpointercancel={onViewportUp}
    onpointerleave={() => (cursor = null)}
    role="presentation"
  >
    <div
      class="canvas"
      style:left="{origin.x}px"
      style:top="{origin.y}px"
      style:width="{CANVAS_W * scale}px"
      style:height="{CANVAS_H * scale}px"
    >
      {#if preview}
        <Thumb config={preview} still={false} edit={editor.editable && !live} background={background === "dark" ? "dark" : "checker"} />
      {/if}
      {#if editor.editable}
        <div
          class="layer"
          bind:this={layer}
          role="application"
          tabindex="-1"
          aria-label={t("studio.stage")}
          onpointerdown={onLayerDown}
          onpointermove={onMove}
          onpointerup={onUp}
          onpointercancel={onUp}
          ondragover={onDragOver}
          ondrop={onDrop}
        >
          <div class="inner" style:transform="scale({scale})" style:--s={scale}>
            {#if showGrid}<div class="grid" class:coarse={scale < 0.6}></div>{/if}
            {#each editor.ordered as el (el.id)}
              {@const isSel = editor.selected.includes(el.id)}
              <div
                class="box"
                class:sel={isSel}
                class:locked={el.locked}
                class:ghost={el.hidden}
                class:err={editor.errorIds.includes(el.id) || editor.problems.has(el.id)}
                style:left="{el.x}px"
                style:top="{el.y}px"
                style:width="{el.w}px"
                style:height="{el.h}px"
                style:--c={slotColor(el)}
                onpointerdown={(e) => onBoxDown(e, el)}
                role="presentation"
              >
                <span class="tag">{boxLabel(el)}</span>
                {#if isSel && editor.one?.id === el.id && !el.locked}
                  {#each HANDLES as h (h)}
                    <div class="handle {h}" onpointerdown={(e) => onHandleDown(e, el, h)} role="presentation"></div>
                  {/each}
                {/if}
              </div>
            {/each}
            {#each snapGuides as g, i (i)}
              <div class="guide {g.axis}" style:left={g.axis === "x" ? `${g.at}px` : "0"} style:top={g.axis === "y" ? `${g.at}px` : "0"}></div>
            {/each}
            {#if marquee}
              <div class="marquee" style:left="{marquee.x}px" style:top="{marquee.y}px" style:width="{marquee.w}px" style:height="{marquee.h}px"></div>
            {/if}
          </div>
        </div>
      {/if}
      <GuideOverlay />
    </div>
    {#if notice}<div class="notice">{@render notice()}</div>{/if}
  </div>

  <div class="status">
    <span class="size" title={t("studio.canvas_hint")}>{t("studio.canvas")} <b>{CANVAS_W} × {CANVAS_H}</b></span>
    <span>{t("studio.zoom")} <b>{Math.round(scale * 100)} %</b></span>
    <span class="mono">{t("studio.mouse")} {cursor ? `${cursor.x}, ${cursor.y}` : "–"}</span>
    {#if selBox}
      <span class="mono">{t("studio.selection")} {selBox.x}, {selBox.y} · {selBox.w} × {selBox.h}</span>
    {/if}
    <span class="spacer"></span>
    <div class="seg zoom">
      <button class:on={zoom === "fit"} aria-pressed={zoom === "fit"} title={t("studio.zoom_fit_hint")} onclick={() => (zoom = "fit")}>{t("builder.zoom_fit")}</button>
      <button class:on={zoom === 0.5} aria-pressed={zoom === 0.5} onclick={() => setZoom(0.5)}>50 %</button>
      <button class:on={zoom === 1} aria-pressed={zoom === 1} title="1:1" onclick={() => setZoom(1)}>100 %</button>
      <button aria-label={t("studio.zoom_out")} title={t("studio.zoom_out")} onclick={() => zoomStep(-1)}>−</button>
      <button aria-label={t("studio.zoom_in")} title={t("studio.zoom_in")} onclick={() => zoomStep(1)}>+</button>
    </div>
  </div>
</div>

<style>
  .stage-wrap {
    display: grid;
    grid-template-rows: minmax(0, 1fr) auto;
    min-height: 0;
    min-width: 0;
    height: 100%;
  }
  .viewport {
    position: relative;
    overflow: hidden;
    min-height: 240px;
    background: #070a14;
    border: 1px solid var(--line);
    border-radius: 8px 8px 0 0;
    touch-action: none;
  }
  .viewport.pan,
  .viewport.pan * {
    cursor: grab !important;
  }
  .canvas {
    position: absolute;
    /* The stage edge, like the red-less frame of the OBS canvas. */
    outline: 1px solid color-mix(in srgb, var(--accent) 55%, transparent);
    box-shadow: 0 0 0 9999px rgb(0 0 0 / 0.35);
  }
  .canvas :global(.thumb) {
    position: absolute;
    inset: 0;
    border-radius: 0;
    border: 0;
  }
  .notice {
    position: absolute;
    left: 50%;
    bottom: 16px;
    transform: translateX(-50%);
    max-width: calc(100% - 32px);
  }
  .status {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 6px 16px;
    padding: 6px 10px;
    font-size: 13px;
    color: var(--muted);
    background: var(--panel);
    border: 1px solid var(--line);
    border-top: 0;
    border-radius: 0 0 8px 8px;
  }
  .status b {
    color: var(--text, #e5e7eb);
    font-weight: 600;
  }
  .size b {
    color: var(--accent);
  }
  .mono {
    font-variant-numeric: tabular-nums;
  }
  .zoom button {
    padding: 2px 10px;
    font-size: 13px;
  }
  .layer {
    position: absolute;
    inset: 0;
    outline: none;
    user-select: none;
  }
  .inner {
    position: absolute;
    left: 0;
    top: 0;
    width: 1920px;
    height: 1080px;
    transform-origin: 0 0;
  }
  .grid {
    position: absolute;
    inset: 0;
    pointer-events: none;
    background-image:
      linear-gradient(to right, rgb(255 255 255 / 0.06) 1px, transparent 1px),
      linear-gradient(to bottom, rgb(255 255 255 / 0.06) 1px, transparent 1px);
    background-size: 8px 8px;
  }
  .grid.coarse {
    background-size: 40px 40px;
  }
  .box {
    position: absolute;
    box-sizing: border-box;
    outline: calc(1px / var(--s)) dashed color-mix(in srgb, var(--c) 45%, transparent);
    cursor: move;
  }
  .box:hover {
    outline: calc(1px / var(--s)) solid var(--c);
    background: color-mix(in srgb, var(--c) 8%, transparent);
  }
  .box.sel {
    outline: calc(2px / var(--s)) solid var(--accent);
    background: color-mix(in srgb, var(--accent) 10%, transparent);
  }
  .box.locked {
    cursor: default;
    outline-style: dotted;
  }
  .box.ghost {
    opacity: 0.6;
  }
  .box.err {
    outline: calc(3px / var(--s)) solid var(--bad, #f83800);
  }
  .tag {
    position: absolute;
    left: 0;
    top: 0;
    transform-origin: 0 0;
    transform: scale(calc(1 / var(--s)));
    font: 600 11px/1.3 system-ui, sans-serif;
    white-space: nowrap;
    padding: 1px 5px;
    color: #000;
    background: var(--c);
    opacity: 0.9;
    pointer-events: none;
  }
  .box:not(.sel):not(:hover):not(.err) .tag {
    display: none;
  }
  .handle {
    --hs: calc(10px / var(--s));
    position: absolute;
    width: var(--hs);
    height: var(--hs);
    background: var(--accent);
    border: calc(1px / var(--s)) solid #000;
    box-sizing: border-box;
  }
  .handle.nw { left: calc(var(--hs) / -2); top: calc(var(--hs) / -2); cursor: nwse-resize; }
  .handle.n { left: calc(50% - var(--hs) / 2); top: calc(var(--hs) / -2); cursor: ns-resize; }
  .handle.ne { right: calc(var(--hs) / -2); top: calc(var(--hs) / -2); cursor: nesw-resize; }
  .handle.e { right: calc(var(--hs) / -2); top: calc(50% - var(--hs) / 2); cursor: ew-resize; }
  .handle.se { right: calc(var(--hs) / -2); bottom: calc(var(--hs) / -2); cursor: nwse-resize; }
  .handle.s { left: calc(50% - var(--hs) / 2); bottom: calc(var(--hs) / -2); cursor: ns-resize; }
  .handle.sw { left: calc(var(--hs) / -2); bottom: calc(var(--hs) / -2); cursor: nesw-resize; }
  .handle.w { left: calc(var(--hs) / -2); top: calc(50% - var(--hs) / 2); cursor: ew-resize; }
  .guide {
    position: absolute;
    background: #ff3df0;
    pointer-events: none;
  }
  .guide.x {
    width: calc(1px / var(--s));
    height: 1080px;
  }
  .guide.y {
    height: calc(1px / var(--s));
    width: 1920px;
  }
  .marquee {
    position: absolute;
    border: calc(1px / var(--s)) solid var(--accent);
    background: color-mix(in srgb, var(--accent) 12%, transparent);
    pointer-events: none;
  }
</style>
