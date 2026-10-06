// Layout builder geometry: snapping, resizing, alignment. All coordinates are
// stage pixels (1920x1080); the bounds mirror core/overlay_layout.py.

export const CANVAS_W = 1920;
export const CANVAS_H = 1080;
export const MARGIN_W = CANVAS_W / 10;
export const MARGIN_H = CANVAS_H / 10;
export const MIN_SIZE = 8;
export const GRID = 8;

export interface Rect {
  x: number;
  y: number;
  w: number;
  h: number;
}

/** A snap line drawn while dragging: vertical (x) or horizontal (y). */
export interface Guide {
  axis: "x" | "y";
  at: number;
}

export type Handle = "n" | "s" | "e" | "w" | "ne" | "nw" | "se" | "sw";
export const HANDLES: Handle[] = ["nw", "n", "ne", "e", "se", "s", "sw", "w"];

export interface SnapOptions {
  /** Other elements to snap to (edges and centres). */
  targets: Rect[];
  /** Snap distance in stage pixels (depends on the zoom). */
  threshold: number;
  /** Grid size; 0 = no grid. */
  grid?: number;
  /** Alt held: no snapping at all. */
  free?: boolean;
}

export function snapToGrid(v: number, grid = GRID): number {
  return grid > 0 ? Math.round(v / grid) * grid : Math.round(v);
}

/** The bounding box of rectangles (null for none). */
export function bounds(rects: Rect[]): Rect | null {
  if (!rects.length) return null;
  const x = Math.min(...rects.map((r) => r.x));
  const y = Math.min(...rects.map((r) => r.y));
  const right = Math.max(...rects.map((r) => r.x + r.w));
  const bottom = Math.max(...rects.map((r) => r.y + r.h));
  return { x, y, w: right - x, h: bottom - y };
}

/** Lines an edge may snap to on one axis: stage edges + centre, target edges + centres. */
function lines(axis: "x" | "y", targets: Rect[]): number[] {
  const size = axis === "x" ? CANVAS_W : CANVAS_H;
  const out = [0, size / 2, size];
  for (const t of targets) {
    const start = axis === "x" ? t.x : t.y;
    const len = axis === "x" ? t.w : t.h;
    out.push(start, start + len / 2, start + len);
  }
  return out;
}

/** Best snap of some candidate positions to lines: the offset to apply, or null. */
function nearest(candidates: number[], targets: number[], threshold: number): { offset: number; at: number } | null {
  let best: { offset: number; at: number } | null = null;
  for (const c of candidates) {
    for (const t of targets) {
      const d = t - c;
      if (Math.abs(d) <= threshold && (!best || Math.abs(d) < Math.abs(best.offset))) best = { offset: d, at: t };
    }
  }
  return best;
}

/**
 * Snap a move of a box (the selection's bounding box) by dx/dy: its edges and
 * centre snap to other elements and the stage, otherwise its corner to the grid.
 */
export function snapMove(box: Rect, dx: number, dy: number, opts: SnapOptions): { dx: number; dy: number; guides: Guide[] } {
  let x = box.x + dx;
  let y = box.y + dy;
  if (opts.free) return { dx: Math.round(dx), dy: Math.round(dy), guides: [] };
  const guides: Guide[] = [];
  const sx = nearest([x, x + box.w / 2, x + box.w], lines("x", opts.targets), opts.threshold);
  if (sx) {
    x += sx.offset;
    guides.push({ axis: "x", at: sx.at });
  } else x = snapToGrid(x, opts.grid ?? GRID);
  const sy = nearest([y, y + box.h / 2, y + box.h], lines("y", opts.targets), opts.threshold);
  if (sy) {
    y += sy.offset;
    guides.push({ axis: "y", at: sy.at });
  } else y = snapToGrid(y, opts.grid ?? GRID);
  return { dx: Math.round(x - box.x), dy: Math.round(y - box.y), guides };
}

/** Snap one moving edge position (resize). */
function snapEdge(v: number, axis: "x" | "y", opts: SnapOptions, guides: Guide[]): number {
  if (opts.free) return Math.round(v);
  const s = nearest([v], lines(axis, opts.targets), opts.threshold);
  if (s) {
    guides.push({ axis, at: s.at });
    return Math.round(v + s.offset);
  }
  return snapToGrid(v, opts.grid ?? GRID);
}

/**
 * Resize a rectangle by dragging a handle by dx/dy. The dragged edges snap;
 * the opposite edges stay put; the size never drops below MIN_SIZE. With
 * ``keepRatio`` (Shift) corner handles keep the aspect ratio.
 */
export function resize(
  r: Rect,
  handle: Handle,
  dx: number,
  dy: number,
  opts: SnapOptions,
  keepRatio = false,
): { rect: Rect; guides: Guide[] } {
  const guides: Guide[] = [];
  let left = r.x;
  let top = r.y;
  let right = r.x + r.w;
  let bottom = r.y + r.h;
  if (handle.includes("w")) left = Math.min(snapEdge(left + dx, "x", opts, guides), right - MIN_SIZE);
  if (handle.includes("e")) right = Math.max(snapEdge(right + dx, "x", opts, guides), left + MIN_SIZE);
  if (handle.includes("n")) top = Math.min(snapEdge(top + dy, "y", opts, guides), bottom - MIN_SIZE);
  if (handle.includes("s")) bottom = Math.max(snapEdge(bottom + dy, "y", opts, guides), top + MIN_SIZE);
  if (keepRatio && handle.length === 2 && r.w > 0 && r.h > 0) {
    const ratio = r.w / r.h;
    const w = right - left;
    const h = Math.max(MIN_SIZE, Math.round(w / ratio));
    if (handle.includes("n")) top = bottom - h;
    else bottom = top + h;
    guides.length = 0;
  }
  return { rect: clamp({ x: left, y: top, w: right - left, h: bottom - top }), guides };
}

/** Keep a rectangle within what the server accepts (stage plus margin). */
export function clamp(r: Rect): Rect {
  const w = Math.min(Math.max(Math.round(r.w), MIN_SIZE), CANVAS_W + 2 * MARGIN_W);
  const h = Math.min(Math.max(Math.round(r.h), MIN_SIZE), CANVAS_H + 2 * MARGIN_H);
  const x = Math.min(Math.max(Math.round(r.x), -MARGIN_W), CANVAS_W + MARGIN_W - w);
  const y = Math.min(Math.max(Math.round(r.y), -MARGIN_H), CANVAS_H + MARGIN_H - h);
  return { x, y, w, h };
}

/** Limit a move so that the box stays within the accepted area. */
export function clampMove(box: Rect, dx: number, dy: number): { dx: number; dy: number } {
  const minX = -MARGIN_W - box.x;
  const maxX = CANVAS_W + MARGIN_W - box.w - box.x;
  const minY = -MARGIN_H - box.y;
  const maxY = CANVAS_H + MARGIN_H - box.h - box.y;
  return { dx: Math.min(Math.max(dx, minX), maxX), dy: Math.min(Math.max(dy, minY), maxY) };
}

export type AlignMode = "left" | "hcenter" | "right" | "top" | "vcenter" | "bottom";

/** Align rectangles to their common bounding box (one rect: to the stage). */
export function align(rects: Rect[], mode: AlignMode): Rect[] {
  const box = rects.length === 1 ? { x: 0, y: 0, w: CANVAS_W, h: CANVAS_H } : bounds(rects);
  if (!box) return rects;
  return rects.map((r) => {
    switch (mode) {
      case "left": return { ...r, x: box.x };
      case "hcenter": return { ...r, x: Math.round(box.x + (box.w - r.w) / 2) };
      case "right": return { ...r, x: box.x + box.w - r.w };
      case "top": return { ...r, y: box.y };
      case "vcenter": return { ...r, y: Math.round(box.y + (box.h - r.h) / 2) };
      case "bottom": return { ...r, y: box.y + box.h - r.h };
    }
  });
}

/** Spread three or more rectangles evenly (equal gaps) along an axis; order kept. */
export function distribute(rects: Rect[], axis: "x" | "y"): Rect[] {
  if (rects.length < 3) return rects;
  const pos = (r: Rect): number => (axis === "x" ? r.x : r.y);
  const len = (r: Rect): number => (axis === "x" ? r.w : r.h);
  const order = rects.map((r, i) => ({ r, i })).sort((a, b) => pos(a.r) - pos(b.r));
  const first = order[0]!.r;
  const last = order[order.length - 1]!.r;
  const total = pos(last) + len(last) - pos(first);
  const used = order.reduce((sum, { r }) => sum + len(r), 0);
  const gap = (total - used) / (order.length - 1);
  const out = [...rects];
  let at = pos(first);
  for (const { r, i } of order) {
    out[i] = axis === "x" ? { ...r, x: Math.round(at) } : { ...r, y: Math.round(at) };
    at += len(r) + gap;
  }
  return out;
}

/** Do two rectangles overlap (touching counts)? */
export function intersects(a: Rect, b: Rect): boolean {
  return a.x <= b.x + b.w && b.x <= a.x + a.w && a.y <= b.y + b.h && b.y <= a.y + a.h;
}

/** A rectangle from two corner points (marquee). */
export function fromPoints(x1: number, y1: number, x2: number, y2: number): Rect {
  return { x: Math.min(x1, x2), y: Math.min(y1, y2), w: Math.abs(x2 - x1), h: Math.abs(y2 - y1) };
}
