// Sizes for builder widgets: everything is derived from the element's box, so
// a widget fills any rectangle without overflowing it. In the NES style font
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

/** Pixel size of the heart artwork (11x10 pixels per heart, 6 px gaps). */
export function heartPixel(max: number, w: number, h: number): number {
  const n = Math.max(1, max);
  return Math.max(1, Math.floor(Math.min(h / 10, (w - (n - 1) * 6) / (11 * n))));
}
