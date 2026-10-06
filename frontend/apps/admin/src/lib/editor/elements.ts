// Layout builder: element catalogue (palette, defaults) and document edits
// that keep a definition valid (ids, slots, pairs). Pure functions: every
// edit returns a new definition.

import type { ElementType, LayoutDefinition, LayoutElement } from "../studio";
import { CANVAS_H, CANVAS_W, clamp, intersects, type Rect } from "./geometry";

export const MAX_ELEMENTS = 300;
export const MAX_SLOTS = 8;
export const MAX_PAIRS = 4;

export const SLOT_TYPES: ReadonlySet<ElementType> = new Set(["board", "next", "stat", "name", "hearts", "nametag", "camera"]);
export const PAIR_TYPES: ReadonlySet<ElementType> = new Set(["versus", "diff_graph"]);
/** May name a pair (its round), else the scene's round. */
export const OPTIONAL_PAIR_TYPES: ReadonlySet<ElementType> = new Set(["round"]);

export const STAT_FIELDS = ["score", "lines", "level", "start_level", "trt", "drought", "burn", "pace", "gap", "pieces"] as const;

/** Palette order and the size a new element gets. */
export const CATALOGUE: { type: ElementType; w: number; h: number; props?: Record<string, unknown> }[] = [
  { type: "board", w: 336, h: 696 },
  { type: "next", w: 264, h: 136 },
  { type: "stat", w: 264, h: 104, props: { field: "score" } },
  { type: "nametag", w: 296, h: 112 },
  { type: "name", w: 296, h: 64 },
  { type: "hearts", w: 200, h: 56 },
  { type: "camera", w: 480, h: 272 },
  { type: "versus", w: 320, h: 256 },
  { type: "diff_graph", w: 352, h: 184 },
  { type: "title", w: 688, h: 56 },
  { type: "round", w: 256, h: 56 },
  { type: "text", w: 400, h: 56, props: { text: "Text", size: 32 } },
  { type: "frame", w: 400, h: 304 },
];

export function emptyDefinition(slots = 2): LayoutDefinition {
  const pairs: [number, number][] = slots === 2 ? [[0, 1]] : [];
  return { schema: 1, slots, pairs, elements: [] };
}

/** A fresh id like "board-3" that the definition does not use yet. */
export function uniqueId(def: LayoutDefinition, base: string): string {
  const used = new Set(def.elements.map((e) => e.id));
  const stem = base.replace(/[^A-Za-z0-9_-]/g, "").replace(/-\d+$/, "").slice(0, 24) || "el";
  for (let n = 1; ; n++) {
    const id = `${stem}-${n}`;
    if (!used.has(id)) return id;
  }
}

/** The topmost z (new elements go on top). */
function topZ(def: LayoutDefinition): number {
  return def.elements.reduce((z, e) => Math.max(z, e.z ?? 0), 0);
}

/** A new element of a type, centred on (cx, cy), with a valid slot/pair. */
export function newElement(def: LayoutDefinition, type: ElementType, cx = CANVAS_W / 2, cy = CANVAS_H / 2, slot = 0): LayoutElement {
  const spec = CATALOGUE.find((c) => c.type === type) ?? { type, w: 200, h: 100 };
  const r = clamp({ x: Math.round(cx - spec.w / 2), y: Math.round(cy - spec.h / 2), w: spec.w, h: spec.h });
  const el: LayoutElement = { id: uniqueId(def, type.replace("_", "")), type, ...r, z: topZ(def) + 1 };
  if (SLOT_TYPES.has(type)) el.slot = Math.min(Math.max(slot, 0), def.slots - 1);
  if (PAIR_TYPES.has(type)) el.pair = 0;
  if (spec.props) el.props = { ...spec.props };
  return el;
}

/** Can this type be placed now (pair elements need a pair)? */
export function placeable(def: LayoutDefinition, type: ElementType): boolean {
  return !PAIR_TYPES.has(type) || def.pairs.length > 0;
}

export function addElements(def: LayoutDefinition, elements: LayoutElement[]): LayoutDefinition {
  return { ...def, elements: [...def.elements, ...elements].slice(0, MAX_ELEMENTS) };
}

export function removeElements(def: LayoutDefinition, ids: Iterable<string>): LayoutDefinition {
  const drop = new Set(ids);
  return { ...def, elements: def.elements.filter((e) => !drop.has(e.id)) };
}

export function updateElement(def: LayoutDefinition, id: string, change: Partial<LayoutElement>): LayoutDefinition {
  return { ...def, elements: def.elements.map((e) => (e.id === id ? { ...e, ...change } : e)) };
}

export function updateElements(def: LayoutDefinition, change: (e: LayoutElement) => LayoutElement | null, ids: Iterable<string>): LayoutDefinition {
  const pick = new Set(ids);
  return { ...def, elements: def.elements.map((e) => (pick.has(e.id) ? (change(e) ?? e) : e)) };
}

/** Copies of elements (new ids, shifted by ``offset``), on top of everything. */
export function cloneElements(def: LayoutDefinition, elements: LayoutElement[], offset = 16): LayoutElement[] {
  let working = def;
  let z = topZ(def);
  const out: LayoutElement[] = [];
  for (const e of elements) {
    const copy: LayoutElement = {
      ...structuredClone(e),
      id: uniqueId(working, e.id),
      ...clamp({ x: e.x + offset, y: e.y + offset, w: e.w, h: e.h }),
      z: ++z,
      locked: false,
    };
    // Pasted from another layout: slot/pair may not exist here.
    if (copy.slot !== undefined && copy.slot !== null && copy.slot >= def.slots) copy.slot = def.slots - 1;
    if (copy.pair !== undefined && copy.pair !== null && copy.pair >= def.pairs.length) {
      if (PAIR_TYPES.has(copy.type)) {
        if (!def.pairs.length) continue;
        copy.pair = 0;
      } else copy.pair = null;
    }
    out.push(copy);
    working = { ...working, elements: [...working.elements, copy] };
  }
  return out;
}

/** Change the number of slots: drops pairs and elements of removed slots. */
export function setSlots(def: LayoutDefinition, slots: number): { def: LayoutDefinition; removed: number } {
  const n = Math.min(Math.max(Math.round(slots), 1), MAX_SLOTS);
  const keptPairs = def.pairs.filter(([a, b]) => a < n && b < n);
  const { def: paired, removed: droppedByPairs } = setPairs({ ...def, slots: n }, keptPairs);
  const elements = paired.elements.filter((e) => e.slot === undefined || e.slot === null || e.slot < n);
  return { def: { ...paired, elements }, removed: droppedByPairs + paired.elements.length - elements.length };
}

/**
 * Replace the pairs. Pair elements follow their pair by its slots; elements of
 * a pair that no longer exists are removed (a round element shows the scene's round).
 */
export function setPairs(def: LayoutDefinition, pairs: [number, number][]): { def: LayoutDefinition; removed: number } {
  const key = (p: [number, number]): string => [...p].sort().join(":");
  const newIndex = new Map(pairs.map((p, i) => [key(p), i]));
  let removed = 0;
  const elements: LayoutElement[] = [];
  for (const e of def.elements) {
    if (e.pair === undefined || e.pair === null) {
      elements.push(e);
      continue;
    }
    const old = def.pairs[e.pair];
    const to = old ? newIndex.get(key(old)) : undefined;
    if (to !== undefined) elements.push({ ...e, pair: to });
    else if (OPTIONAL_PAIR_TYPES.has(e.type)) elements.push({ ...e, pair: null });
    else removed++;
  }
  return { def: { ...def, pairs, elements }, removed };
}

/** Slots not yet in a pair (for the pair editor). */
export function unpairedSlots(def: LayoutDefinition): number[] {
  const used = new Set(def.pairs.flat());
  return Array.from({ length: def.slots }, (_, i) => i).filter((s) => !used.has(s));
}

/** Ids of the visible elements a marquee touches (locked ones excluded). */
export function inMarquee(def: LayoutDefinition, area: Rect): string[] {
  return def.elements.filter((e) => !e.locked && intersects(e, area)).map((e) => e.id);
}

/** Bring forward/backward: swap z with the neighbour in paint order. */
export function restack(def: LayoutDefinition, id: string, where: "up" | "down" | "top" | "bottom"): LayoutDefinition {
  const order = def.elements
    .map((e, i) => ({ e, i }))
    .sort((a, b) => (a.e.z ?? 0) - (b.e.z ?? 0) || a.i - b.i)
    .map(({ e }) => e.id);
  const at = order.indexOf(id);
  if (at < 0) return def;
  order.splice(at, 1);
  const to = where === "top" ? order.length : where === "bottom" ? 0 : where === "up" ? Math.min(at + 1, order.length) : Math.max(at - 1, 0);
  order.splice(to, 0, id);
  // Renumber 0..n-1: z stays small and the order is explicit.
  const z = new Map(order.map((eid, i) => [eid, i]));
  return { ...def, elements: def.elements.map((e) => ({ ...e, z: z.get(e.id) ?? 0 })) };
}

/** Errors of a definition the builder can see before saving (server checks the rest). */
export function localProblems(def: LayoutDefinition): Map<string, string> {
  const out = new Map<string, string>();
  for (const e of def.elements) {
    if (SLOT_TYPES.has(e.type) && (e.slot === undefined || e.slot === null || e.slot >= def.slots)) out.set(e.id, "slot");
    if (PAIR_TYPES.has(e.type) && (e.pair === undefined || e.pair === null || e.pair >= def.pairs.length)) out.set(e.id, "pair");
    if (e.type === "text" && !String(e.props?.text ?? "").trim()) out.set(e.id, "text");
  }
  return out;
}
