// Text sizes of studio elements as the overlay computes them (shared
// formulas in @nestris-ltm/nes), for the "keep this size" button of the
// properties panel: it turns the stable size into a fixed one.

import { fitFont, NAME_CHARS, STAT_CHARS, textPx } from "@nestris-ltm/nes";
import type { LayoutElement } from "../studio";

/** Element types whose text size can be set (props text_mode / text_size / chars). */
export const TEXT_SIZE_TYPES: ReadonlySet<string> = new Set(["stat", "name", "nametag", "title", "round", "ranking"]);

/** Reserved characters an element uses when it sets none (mode "stable"). */
export function defaultChars(e: LayoutElement): number {
  const p = e.props ?? {};
  switch (e.type) {
    case "stat":
      return STAT_CHARS[String(p.field ?? "score")] ?? 4;
    case "name":
      return NAME_CHARS + (p.show_rank ? 2 : 0);
    case "nametag":
      return NAME_CHARS;
    case "round":
      return 10;
    case "title":
      return typeof p.text === "string" && p.text ? p.text.length : 16;
    default:
      return 15;
  }
}

/** The main text size of an element in its stable mode, in px. */
export function stableTextPx(e: LayoutElement, nes: boolean): number {
  const p = e.props ?? {};
  const reserved = typeof p.chars === "number" ? p.chars : defaultChars(e);
  const at = (w: number, share: number): number =>
    textPx({ mode: "stable", reserved, actual: reserved, w, h: e.h, share, nes });
  switch (e.type) {
    case "stat":
      return at(e.w - 16, p.show_label !== false ? 0.5 : 0.7);
    case "name":
      return at(e.w - 24, 0.55);
    case "nametag":
      return at(e.w - 24, p.rows === "collapse" ? 0.55 : 0.34);
    case "title":
      return at(e.w - 24, 0.5);
    case "round":
      return at(e.w - 24, 0.45);
    default:
      return fitFont(15, e.w - 48, e.h, 0.42, nes);
  }
}
