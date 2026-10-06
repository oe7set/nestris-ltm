// Layout builder: build the other side of a 1 vs 1 by mirroring one slot's
// elements across the stage's vertical centre line.

import type { LayoutDefinition, LayoutElement } from "../studio";
import { clamp, CANVAS_W } from "./geometry";
import { uniqueId } from "./elements";

const FLIP: Record<string, string> = { left: "right", right: "left" };

/** An element mirrored horizontally (position and text alignment). */
export function mirrorElement(e: LayoutElement): LayoutElement {
  const out: LayoutElement = { ...structuredClone(e), ...clamp({ x: CANVAS_W - e.x - e.w, y: e.y, w: e.w, h: e.h }) };
  const align = out.props?.align;
  if (typeof align === "string" && FLIP[align]) out.props = { ...out.props, align: FLIP[align] };
  return out;
}

/** Id for the mirrored copy: "score-s0" -> "score-s1", else a fresh id. */
function mirroredId(def: LayoutDefinition, id: string, from: number, to: number): string {
  const renamed = id.replace(new RegExp(`(^|[-_])s${from}($|[-_])`), `$1s${to}$2`);
  const used = new Set(def.elements.map((e) => e.id));
  return renamed !== id && !used.has(renamed) ? renamed : uniqueId(def, id);
}

/**
 * Replace everything of slot ``to`` with a mirror image of slot ``from``.
 * Returns the new definition and how many elements of ``to`` were replaced.
 */
export function mirrorSlot(def: LayoutDefinition, from: number, to: number): { def: LayoutDefinition; replaced: number } {
  if (from === to || from >= def.slots || to >= def.slots) return { def, replaced: 0 };
  const kept = def.elements.filter((e) => e.slot !== to);
  let working: LayoutDefinition = { ...def, elements: kept };
  for (const e of def.elements.filter((x) => x.slot === from)) {
    const copy = { ...mirrorElement(e), id: mirroredId(working, e.id, from, to), slot: to };
    working = { ...working, elements: [...working.elements, copy] };
  }
  return { def: working, replaced: def.elements.length - kept.length };
}
