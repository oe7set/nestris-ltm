// NES Tetris look: level colour palettes, block drawing and piece shapes.

/** [colour A, colour B] per level % 10, as rendered by the NES (NTSC). */
export const LEVEL_COLORS: [string, string][] = [
  ["#4a32ff", "#4aaffe"],
  ["#009600", "#6adc00"],
  ["#b000d4", "#ff56ff"],
  ["#4a32ff", "#00e900"],
  ["#c8007f", "#00e678"],
  ["#00e678", "#968dff"],
  ["#c41e0e", "#666666"],
  ["#8200ff", "#780041"],
  ["#4a32ff", "#fb1c0d"],
  ["#c41e0e", "#f69b00"],
];

export function levelColors(level: number | null | undefined): [string, string] {
  const l = Math.max(0, level ?? 0);
  return LEVEL_COLORS[l % 10] ?? LEVEL_COLORS[0]!;
}

/**
 * Draw one NES block at (x, y) with size s.
 * Cell ids: 1 = white block with colour-A frame (I, O, T), 2 = colour A
 * (J, S), 3 = colour B (L, Z). Both solid kinds carry the white shine pixel.
 */
export function drawBlock(
  ctx: CanvasRenderingContext2D,
  cell: number,
  x: number,
  y: number,
  s: number,
  colors: [string, string],
): void {
  const px = Math.max(1, Math.round(s / 8)); // one NES pixel
  const inner = s - px; // 1px gap like the console
  if (cell === 1) {
    ctx.fillStyle = colors[0];
    ctx.fillRect(x, y, inner, inner);
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(x + px, y + px, inner - 2 * px, inner - 2 * px);
    ctx.fillRect(x, y, px, px);
    return;
  }
  ctx.fillStyle = cell === 2 ? colors[0] : colors[1];
  ctx.fillRect(x, y, inner, inner);
  ctx.fillStyle = "#ffffff";
  ctx.fillRect(x, y, px, px);
  ctx.fillRect(x + px, y + px, 2 * px, px);
  ctx.fillRect(x + px, y + 2 * px, px, px);
}

/** Piece shapes in a 4x2 box, as shown in the NEXT box. */
export const PIECES: Record<string, { cells: [number, number][]; kind: number }> = {
  T: { cells: [[0, 0], [1, 0], [2, 0], [1, 1]], kind: 1 },
  J: { cells: [[0, 0], [1, 0], [2, 0], [2, 1]], kind: 2 },
  Z: { cells: [[0, 0], [1, 0], [1, 1], [2, 1]], kind: 3 },
  O: { cells: [[0, 0], [1, 0], [0, 1], [1, 1]], kind: 1 },
  S: { cells: [[1, 0], [2, 0], [0, 1], [1, 1]], kind: 2 },
  L: { cells: [[0, 0], [1, 0], [2, 0], [0, 1]], kind: 3 },
  I: { cells: [[0, 0], [1, 0], [2, 0], [3, 0]], kind: 1 },
};

export function parseRows(rows: string[] | null | undefined): number[][] | null {
  if (!rows || rows.length !== 20) return null;
  return rows.map((r) => Array.from(r, (c) => c.charCodeAt(0) - 48));
}
