// Linked slots: the elements of one slot (or pair) are the master, the
// linked slots get copies of them, mirrored at the stage's centre lines
// and/or moved, and follow every change live. Build one quadrant of a
// 4-player scene and the other three arrange themselves.
//
// The definition stores the expanded elements (the overlay just draws
// them) plus ``links``, which only the editor uses. Pure functions: every
// change returns a new definition.

import type { LayoutDefinition, LayoutElement, SlotLink } from "../studio";
import { CANVAS_H, CANVAS_W, clamp, type Rect } from "./geometry";
import { uniqueId } from "./elements";

export const MAX_LINKS = 16;

const FLIP: Record<string, string> = { left: "right", right: "left" };

/** Copies of a slot link, or of a pair link (pair elements: versus, diff graph, round). */
function kindOf(l: SlotLink): "slot" | "pair" {
  return l.pair ? "pair" : "slot";
}

function belongs(e: LayoutElement, kind: "slot" | "pair", n: number): boolean {
  return kind === "slot" ? e.slot === n : e.slot == null && e.pair === n;
}

/** Where a rectangle goes: mirrored at the centre lines, then moved. */
export function linkRect(r: Rect, l: SlotLink): Rect {
  const x = l.flip_x ? CANVAS_W - r.x - r.w : r.x;
  const y = l.flip_y ? CANVAS_H - r.y - r.h : r.y;
  return clamp({ x: x + (l.dx ?? 0), y: y + (l.dy ?? 0), w: r.w, h: r.h });
}

/** Stable id of a copy: "score-s0" -> "score-s2", else "<id>-l2" (pairs: p / m). */
export function linkedId(id: string, l: SlotLink): string {
  const tok = l.pair ? "p" : "s";
  const renamed = id.replace(new RegExp(`(^|[-_])${tok}${l.from}($|[-_])`), `$1${tok}${l.to}$2`);
  if (renamed !== id) return renamed.slice(0, 32);
  return `${id.slice(0, 28)}-${l.pair ? "m" : "l"}${l.to}`;
}

/** The copy of a master element for a link. */
function copyFor(e: LayoutElement, l: SlotLink): LayoutElement {
  const out: LayoutElement = { ...structuredClone(e), ...linkRect(e, l), locked: false };
  if (l.pair) out.pair = l.to;
  else out.slot = l.to;
  const align = out.props?.align;
  if (l.flip_x && typeof align === "string" && FLIP[align]) out.props = { ...out.props, align: FLIP[align] };
  return out;
}

/** Drop links that point at slots or pairs that no longer exist. */
export function pruneLinks(def: LayoutDefinition): LayoutDefinition {
  if (!def.links?.length) return def;
  const ok = (l: SlotLink): boolean => {
    const max = l.pair ? def.pairs.length : def.slots;
    return l.from !== l.to && l.from >= 0 && l.to >= 0 && l.from < max && l.to < max;
  };
  const links = def.links.filter(ok);
  if (links.length === def.links.length) return def;
  return withLinks(def, links);
}

function withLinks(def: LayoutDefinition, links: SlotLink[]): LayoutDefinition {
  if (links.length) return { ...def, links };
  const { links: _gone, ...rest } = def;
  return rest;
}

/** Ids of all copies (derived from a master) -> id of their master element. */
export function linkOrigins(def: LayoutDefinition): Map<string, string> {
  const out = new Map<string, string>();
  for (const l of def.links ?? []) {
    for (const e of def.elements) if (belongs(e, kindOf(l), l.from)) out.set(linkedId(e.id, l), e.id);
  }
  return out;
}

/**
 * Rebuild every linked slot/pair from its master. Elements of the targets
 * are replaced; everything else stays where it is.
 */
export function applyLinks(input: LayoutDefinition): LayoutDefinition {
  const def = pruneLinks(input);
  const links = def.links ?? [];
  if (!links.length) return def;
  const isTarget = (e: LayoutElement): boolean => links.some((l) => belongs(e, kindOf(l), l.to));
  const kept = def.elements.filter((e) => !isTarget(e));
  const used = new Set(kept.map((e) => e.id));
  const copies: LayoutElement[] = [];
  for (const l of links) {
    for (const e of def.elements) {
      if (!belongs(e, kindOf(l), l.from) || isTarget(e)) continue;
      let id = linkedId(e.id, l);
      if (used.has(id)) id = uniqueId({ ...def, elements: [...kept, ...copies] }, id);
      used.add(id);
      copies.push({ ...copyFor(e, l), id });
    }
  }
  const next = [...kept, ...copies];
  // Nothing changed (the common case while dragging something unlinked): keep the object.
  const same =
    next.length === input.elements.length &&
    next.every((e) => {
      const old = input.elements.find((o) => o.id === e.id);
      return old !== undefined && JSON.stringify(old) === JSON.stringify(e);
    });
  if (same && def === input) return input;
  return { ...def, elements: next };
}

/** How many elements a new link would replace on its target. */
export function replacedBy(def: LayoutDefinition, l: SlotLink): number {
  return def.elements.filter((e) => belongs(e, kindOf(l), l.to)).length;
}

/** Add or replace the link of a target (each slot/pair has at most one master). */
export function setLink(def: LayoutDefinition, l: SlotLink): LayoutDefinition {
  const clean: SlotLink = { from: l.from, to: l.to };
  if (l.pair) clean.pair = true;
  if (l.flip_x) clean.flip_x = true;
  if (l.flip_y) clean.flip_y = true;
  if (l.dx) clean.dx = Math.round(l.dx);
  if (l.dy) clean.dy = Math.round(l.dy);
  const others = (def.links ?? []).filter((x) => !(kindOf(x) === kindOf(clean) && x.to === clean.to));
  // A master is never a copy itself (no chains): links into the new master go.
  const links = [...others.filter((x) => !(kindOf(x) === kindOf(clean) && x.to === clean.from)), clean];
  return applyLinks(withLinks(def, links.slice(0, MAX_LINKS)));
}

/** Remove a link; its copies stay as ordinary elements. */
export function removeLink(def: LayoutDefinition, index: number): LayoutDefinition {
  return withLinks(def, (def.links ?? []).filter((_, i) => i !== index));
}

export interface LinkPreset {
  id: string;
  /** Slots the layout needs at least. */
  slots: number;
  links: (def: LayoutDefinition) => SlotLink[];
}

const H = CANVAS_H / 2;
const W = CANVAS_W / 2;

/** Pair 0 -> pair 1 below it, when the layout has two pairs (2 x 1 vs 1). */
function pairBelow(def: LayoutDefinition): SlotLink[] {
  return def.pairs.length >= 2 ? [{ from: 0, to: 1, pair: true, dy: H }] : [];
}

export const LINK_PRESETS: LinkPreset[] = [
  { id: "mirror_lr", slots: 2, links: () => [{ from: 0, to: 1, flip_x: true }] },
  {
    id: "quad_mirror",
    slots: 4,
    links: (def) => [
      { from: 0, to: 1, flip_x: true },
      { from: 0, to: 2, dy: H },
      { from: 0, to: 3, flip_x: true, dy: H },
      ...pairBelow(def),
    ],
  },
  {
    id: "quad_same",
    slots: 4,
    links: (def) => [
      { from: 0, to: 1, dx: W },
      { from: 0, to: 2, dy: H },
      { from: 0, to: 3, dx: W, dy: H },
      ...pairBelow(def),
    ],
  },
  { id: "below_same", slots: 2, links: () => [{ from: 0, to: 1, dy: H }] },
  { id: "below_mirror", slots: 2, links: () => [{ from: 0, to: 1, flip_y: true }] },
];

/** Apply a preset (replaces all links). */
export function applyPreset(def: LayoutDefinition, preset: LinkPreset): LayoutDefinition {
  let out = withLinks(def, []);
  for (const l of preset.links(def)) out = setLink(out, l);
  return out;
}

/** How many elements a preset would replace. */
export function presetReplaces(def: LayoutDefinition, preset: LinkPreset): number {
  const targets = preset.links(def);
  return def.elements.filter((e) => targets.some((l) => belongs(e, kindOf(l), l.to))).length;
}
