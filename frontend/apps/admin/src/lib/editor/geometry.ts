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
  const moved = { ...box, x, y };
  const sx = nearest([x, x + box.w / 2, x + box.w], lines("x", opts.targets), opts.threshold);
  // Equal spacing: only where no edge or centre line is near.
  const gx = sx ? null : nearest([x], gapCandidates(moved, opts.targets, "x"), opts.threshold);
  if (sx) {
    x += sx.offset;
    guides.push({ axis: "x", at: sx.at });
  } else if (gx) x += gx.offset;
  else x = snapToGrid(x, opts.grid ?? GRID);
  const sy = nearest([y, y + box.h / 2, y + box.h], lines("y", opts.targets), opts.threshold);
  const gy = sy ? null : nearest([y], gapCandidates({ ...moved, x }, opts.targets, "y"), opts.threshold);
  if (sy) {
    y += sy.offset;
    guides.push({ axis: "y", at: sy.at });
  } else if (gy) y += gy.offset;
  else y = snapToGrid(y, opts.grid ?? GRID);
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

export interface ResizeMode {
  /** Keep the aspect ratio (corners and edges). */
  keepRatio?: boolean;
  /** Grow and shrink around the centre (the opposite edge moves too). */
  fromCenter?: boolean;
}

/**
 * Resize a rectangle by dragging a handle by dx/dy. The dragged edges snap;
 * the opposite edges stay put (or mirror the move ``fromCenter``); the size
 * never drops below MIN_SIZE. ``keepRatio`` keeps the aspect ratio: at a
 * corner the axis that changed more leads, at an edge the other axis
 * follows around its centre. ``true`` alone means keepRatio (Shift).
 */
export function resize(
  r: Rect,
  handle: Handle,
  dx: number,
  dy: number,
  opts: SnapOptions,
  mode: boolean | ResizeMode = false,
): { rect: Rect; guides: Guide[] } {
  const { keepRatio = false, fromCenter = false } = typeof mode === "boolean" ? { keepRatio: mode } : mode;
  const guides: Guide[] = [];
  const cx = r.x + r.w / 2;
  const cy = r.y + r.h / 2;
  let left = r.x;
  let top = r.y;
  let right = r.x + r.w;
  let bottom = r.y + r.h;
  if (handle.includes("w")) left = snapEdge(left + dx, "x", opts, guides);
  if (handle.includes("e")) right = snapEdge(right + dx, "x", opts, guides);
  if (handle.includes("n")) top = snapEdge(top + dy, "y", opts, guides);
  if (handle.includes("s")) bottom = snapEdge(bottom + dy, "y", opts, guides);
  if (fromCenter) {
    if (handle.includes("w")) right = 2 * cx - left;
    if (handle.includes("e")) left = 2 * cx - right;
    if (handle.includes("n")) bottom = 2 * cy - top;
    if (handle.includes("s")) top = 2 * cy - bottom;
  }
  let w = Math.max(MIN_SIZE, right - left);
  let h = Math.max(MIN_SIZE, bottom - top);
  const horizontal = handle.includes("e") || handle.includes("w");
  const vertical = handle.includes("n") || handle.includes("s");
  if (keepRatio && r.w > 0 && r.h > 0) {
    const ratio = r.w / r.h;
    const widthLeads = horizontal && (!vertical || Math.abs(w / r.w - 1) >= Math.abs(h / r.h - 1));
    if (widthLeads) h = Math.max(MIN_SIZE, w / ratio);
    else w = Math.max(MIN_SIZE, h * ratio);
    // Only the leading axis' snap is still true.
    for (let i = guides.length - 1; i >= 0; i--) if (guides[i]!.axis === (widthLeads ? "y" : "x")) guides.splice(i, 1);
  }
  // Where the rectangle is anchored: the edge opposite the handle, else its centre.
  const x = fromCenter || !horizontal ? cx - w / 2 : handle.includes("w") ? r.x + r.w - w : r.x;
  const y = fromCenter || !vertical ? cy - h / 2 : handle.includes("n") ? r.y + r.h - h : r.y;
  return { rect: clamp({ x, y, w, h }), guides };
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

export const STAGE: Rect = { x: 0, y: 0, w: CANVAS_W, h: CANVAS_H };

/**
 * Align rectangles to a reference box: ``ref``, else their common bounding
 * box (one rect alone: the stage).
 */
export function align(rects: Rect[], mode: AlignMode, ref?: Rect): Rect[] {
  const box = ref ?? (rects.length === 1 ? STAGE : bounds(rects));
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

/**
 * Spread rectangles along an axis, order kept: equal gaps between the first
 * and the last (three or more), or a fixed ``gap`` from the first one on.
 */
export function distribute(rects: Rect[], axis: "x" | "y", gap?: number): Rect[] {
  if (gap !== undefined && rects.length >= 2) return spaced(rects, axis, gap);
  if (rects.length < 3) return rects;
  const pos = (r: Rect): number => (axis === "x" ? r.x : r.y);
  const len = (r: Rect): number => (axis === "x" ? r.w : r.h);
  const order = rects.map((r, i) => ({ r, i })).sort((a, b) => pos(a.r) - pos(b.r));
  const first = order[0]!.r;
  const last = order[order.length - 1]!.r;
  const total = pos(last) + len(last) - pos(first);
  const used = order.reduce((sum, { r }) => sum + len(r), 0);
  const even = (total - used) / (order.length - 1);
  const out = [...rects];
  let at = pos(first);
  for (const { r, i } of order) {
    out[i] = axis === "x" ? { ...r, x: Math.round(at) } : { ...r, y: Math.round(at) };
    at += len(r) + even;
  }
  return out;
}

function spaced(rects: Rect[], axis: "x" | "y", gap: number): Rect[] {
  const pos = (r: Rect): number => (axis === "x" ? r.x : r.y);
  const len = (r: Rect): number => (axis === "x" ? r.w : r.h);
  const order = rects.map((r, i) => ({ r, i })).sort((a, b) => pos(a.r) - pos(b.r));
  const out = [...rects];
  let at = pos(order[0]!.r);
  for (const { r, i } of order) {
    out[i] = axis === "x" ? { ...r, x: Math.round(at) } : { ...r, y: Math.round(at) };
    at += len(r) + gap;
  }
  return out;
}

export type Arrangement = "row" | "column" | "grid";

/**
 * Line rectangles up in a row, a column or a grid (``columns`` wide) with
 * ``gap`` between them, in reading order, starting at their bounding box's
 * top left. In a row they share a centre line, in a column a centre axis;
 * grid cells are as large as the largest element of their row/column.
 */
export function arrange(rects: Rect[], kind: Arrangement, gap: number, columns = 2): Rect[] {
  const box = bounds(rects);
  if (!box || rects.length < 2) return rects;
  const order = rects
    .map((r, i) => ({ r, i }))
    .sort((a, b) => (kind === "column" ? a.r.y - b.r.y || a.r.x - b.r.x : kind === "row" ? a.r.x - b.r.x || a.r.y - b.r.y : rowOrder(a.r, b.r)));
  const cols = kind === "row" ? order.length : kind === "column" ? 1 : Math.max(1, Math.min(columns, order.length));
  const rowsN = Math.ceil(order.length / cols);
  const colW = Array.from({ length: cols }, (_, c) => Math.max(0, ...order.filter((_, k) => k % cols === c).map(({ r }) => r.w)));
  const rowH = Array.from({ length: rowsN }, (_, row) => Math.max(0, ...order.slice(row * cols, row * cols + cols).map(({ r }) => r.h)));
  const out = [...rects];
  order.forEach(({ r, i }, k) => {
    const c = k % cols;
    const row = Math.floor(k / cols);
    const cellX = box.x + colW.slice(0, c).reduce((s, w) => s + w + gap, 0);
    const cellY = box.y + rowH.slice(0, row).reduce((s, h) => s + h + gap, 0);
    out[i] = { ...r, x: Math.round(cellX + (colW[c]! - r.w) / 2), y: Math.round(cellY + (rowH[row]! - r.h) / 2) };
  });
  return out;
}

/** Reading order: rows first (rectangles whose centres are close in y), then x. */
function rowOrder(a: Rect, b: Rect): number {
  const dy = a.y + a.h / 2 - (b.y + b.h / 2);
  return Math.abs(dy) > Math.min(a.h, b.h) / 2 ? dy : a.x - b.x;
}

/** Give rectangles the width and/or height of ``ref``, each keeping its centre. */
export function matchSize(rects: Rect[], ref: Rect, dim: "w" | "h" | "both"): Rect[] {
  return rects.map((r) => {
    const w = dim === "h" ? r.w : ref.w;
    const h = dim === "w" ? r.h : ref.h;
    return clamp({ x: r.x + (r.w - w) / 2, y: r.y + (r.h - h) / 2, w, h });
  });
}

/** Does ``outer`` contain ``inner`` completely? */
export function contains(outer: Rect, inner: Rect): boolean {
  return inner.x >= outer.x && inner.y >= outer.y && inner.x + inner.w <= outer.x + outer.w && inner.y + inner.h <= outer.y + outer.h;
}

/** A distance shown while dragging: from..to on ``axis`` at the other axis' ``at``. */
export interface Measure {
  axis: "x" | "y";
  from: number;
  to: number;
  at: number;
}

/**
 * Distances from ``box`` to its nearest neighbour in each direction (only
 * neighbours beside it, overlapping on the other axis), else to the stage edge.
 */
export function measure(box: Rect, others: Rect[]): Measure[] {
  const out: Measure[] = [];
  const overlapY = (o: Rect): boolean => o.y < box.y + box.h && box.y < o.y + o.h;
  const overlapX = (o: Rect): boolean => o.x < box.x + box.w && box.x < o.x + o.w;
  const midY = box.y + box.h / 2;
  const midX = box.x + box.w / 2;
  const left = Math.max(0, ...others.filter((o) => overlapY(o) && o.x + o.w <= box.x).map((o) => o.x + o.w));
  const right = Math.min(CANVAS_W, ...others.filter((o) => overlapY(o) && o.x >= box.x + box.w).map((o) => o.x));
  const top = Math.max(0, ...others.filter((o) => overlapX(o) && o.y + o.h <= box.y).map((o) => o.y + o.h));
  const bottom = Math.min(CANVAS_H, ...others.filter((o) => overlapX(o) && o.y >= box.y + box.h).map((o) => o.y));
  if (box.x > left) out.push({ axis: "x", from: left, to: box.x, at: midY });
  if (right > box.x + box.w) out.push({ axis: "x", from: box.x + box.w, to: right, at: midY });
  if (box.y > top) out.push({ axis: "y", from: top, to: box.y, at: midX });
  if (bottom > box.y + box.h) out.push({ axis: "y", from: box.y + box.h, to: bottom, at: midX });
  return out;
}

/** Distances between two rectangles (Alt + hover): the gaps on both axes. */
export function measureBetween(a: Rect, b: Rect): Measure[] {
  const out: Measure[] = [];
  const at = (lo1: number, hi1: number, lo2: number, hi2: number): number => {
    const lo = Math.max(lo1, lo2);
    const hi = Math.min(hi1, hi2);
    return lo <= hi ? (lo + hi) / 2 : (Math.min(hi1, hi2) + Math.max(lo1, lo2)) / 2;
  };
  if (a.x + a.w <= b.x) out.push({ axis: "x", from: a.x + a.w, to: b.x, at: at(a.y, a.y + a.h, b.y, b.y + b.h) });
  else if (b.x + b.w <= a.x) out.push({ axis: "x", from: b.x + b.w, to: a.x, at: at(a.y, a.y + a.h, b.y, b.y + b.h) });
  if (a.y + a.h <= b.y) out.push({ axis: "y", from: a.y + a.h, to: b.y, at: at(a.x, a.x + a.w, b.x, b.x + b.w) });
  else if (b.y + b.h <= a.y) out.push({ axis: "y", from: b.y + b.h, to: a.y, at: at(a.x, a.x + a.w, b.x, b.x + b.w) });
  return out;
}

/**
 * Positions on one axis where ``box`` would have the same gap to a
 * neighbour as two other neighbours in its row/column have to each other,
 * or sit exactly in the middle between two neighbours (smart spacing).
 */
export function gapCandidates(box: Rect, others: Rect[], axis: "x" | "y"): number[] {
  const pos = (r: Rect): number => (axis === "x" ? r.x : r.y);
  const len = (r: Rect): number => (axis === "x" ? r.w : r.h);
  const across = (o: Rect): boolean =>
    axis === "x" ? o.y < box.y + box.h && box.y < o.y + o.h : o.x < box.x + box.w && box.x < o.x + o.w;
  const row = others.filter(across).sort((a, b) => pos(a) - pos(b));
  const gaps: number[] = [];
  for (let i = 1; i < row.length; i++) {
    const g = pos(row[i]!) - (pos(row[i - 1]!) + len(row[i - 1]!));
    if (g > 0) gaps.push(g);
  }
  const out: number[] = [];
  for (const o of row) {
    for (const g of gaps) {
      out.push(pos(o) + len(o) + g); // right of / below o
      out.push(pos(o) - g - len(box)); // left of / above o
    }
  }
  for (let i = 1; i < row.length; i++) {
    const a = row[i - 1]!;
    const b = row[i]!;
    const free = pos(b) - (pos(a) + len(a));
    if (free > len(box)) out.push(pos(a) + len(a) + (free - len(box)) / 2);
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
