// Sizes for builder widgets, shared by the overlay widgets and the studio:
// everything is derived from the element's box, so a widget fills any
// rectangle without overflowing it. In the NES style font
// sizes snap down to the 8 px grid of the pixel font (crisp pixels).

/** Font size for ``chars`` characters in a w x h box using ``share`` of the height. */
export function fitFont(chars: number, w: number, h: number, share: number, nes: boolean): number {
  const byHeight = h * share;
  // Advance width per character: Press Start 2P is square, Share Tech Mono about half.
  const perChar = nes ? 1.0 : 0.56;
  const byWidth = (w * 0.9) / Math.max(1, chars * perChar);
  const size = Math.min(byHeight, byWidth);
  if (nes) return Math.max(8, Math.floor(size / 8) * 8);
  return Math.max(10, Math.floor(size));
}

/** Cell size of a 10x20 playfield (with its frame) inside a w x h box. */
export function boardCell(w: number, h: number): number {
  // Well: 10 or 20 cells + a quarter cell padding on each side + ~8 px frame.
  return Math.max(4, Math.floor(Math.min((w - 8) / 10.5, (h - 8) / 20.5)));
}

/** Outer size of a playfield (well, padding, frame) drawn with ``cell`` px cells. */
export function boardSize(cell: number): { w: number; h: number } {
  return { w: Math.ceil(cell * 10.5 + 8), h: Math.ceil(cell * 20.5 + 8) };
}

/** Pixel size of the heart artwork (11x10 pixels per heart, 6 px gaps). */
export function heartPixel(max: number, w: number, h: number): number {
  const n = Math.max(1, max);
  return Math.max(1, Math.floor(Math.min(h / 10, (w - (n - 1) * 6) / (11 * n))));
}

/**
 * How a widget sizes its text (prop ``text_mode``):
 * - "stable" (default): from a reserved number of characters, so the size
 *   does not jump while scores grow or names change; only text longer than
 *   the reservation shrinks to fit.
 * - "fixed": ``text_size`` pixels (NES: on the 8 px grid).
 * - "fit": from the current text (the behaviour before 0.7).
 */
export type TextMode = "stable" | "fixed" | "fit";

export interface TextFit {
  mode?: unknown;
  /** Fixed size in px (mode "fixed"). */
  size?: unknown;
  /** Reserved characters (mode "stable"). */
  reserved: number;
  /** Characters of the text shown now. */
  actual: number;
  w: number;
  h: number;
  share: number;
  nes: boolean;
}

export function textMode(mode: unknown): TextMode {
  return mode === "fixed" || mode === "fit" ? mode : "stable";
}

/** Font size of a widget text according to its mode. */
export function textPx(o: TextFit): number {
  const mode = textMode(o.mode);
  if (mode === "fixed" && typeof o.size === "number" && o.size > 0) {
    return o.nes ? Math.max(8, Math.floor(o.size / 8) * 8) : Math.max(8, Math.round(o.size));
  }
  if (mode === "fit") return fitFont(o.actual, o.w, o.h, o.share, o.nes);
  const stable = fitFont(Math.max(1, o.reserved), o.w, o.h, o.share, o.nes);
  return o.actual > o.reserved ? Math.min(stable, fitFont(o.actual, o.w, o.h, o.share, o.nes)) : stable;
}

/** Reserved characters of a stat value (mode "stable"), by field. */
export const STAT_CHARS: Record<string, number> = {
  score: 7, // 999,999
  lines: 3,
  level: 2,
  start_level: 2,
  trt: 4, // 100%
  drought: 3,
  burn: 3,
  pace: 9, // 1,234,567
  pieces: 3,
  gap: 8, // +123,456
  to_advance: 9, // 12 Tetris / −123,456
};

/** Reserved characters of a player name (mode "stable"). */
export const NAME_CHARS = 10;
