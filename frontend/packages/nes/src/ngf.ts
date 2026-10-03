// NestrisChamps NGF decoder (frame versions 1-3) for replays in the browser.
// Port of src/nestris_ltm/core/ngf.py; see nestris-core/docs/NGF.md.

const PIECES = "TJZOSLI"; // codes 0..6; 7 = none
const FRAME_SIZES: Record<number, number> = { 1: 71, 2: 72, 3: 73 };

export interface NgfFrame {
  version: number;
  gameid: number;
  ctimeMs: number;
  score: number | null;
  lines: number | null;
  level: number | null;
  preview: string | null;
  curPiece: string | null;
  counts: (number | null)[]; // T J Z O S L I
  cells: Uint8Array; // 200 cell ids, row-major from the top-left
}

const orNull = (value: number, sentinel: number): number | null => (value === sentinel ? null : value);
const piece = (code: number): string | null => PIECES[code] ?? null;

function unpackField(f: Uint8Array, start: number): Uint8Array {
  const cells = new Uint8Array(200);
  for (let i = 0; i < 50; i++) {
    const b = f[start + i]!;
    cells[i * 4] = (b >> 6) & 3;
    cells[i * 4 + 1] = (b >> 4) & 3;
    cells[i * 4 + 2] = (b >> 2) & 3;
    cells[i * 4 + 3] = b & 3;
  }
  return cells;
}

/** Unpack ``n`` counters of ``width`` bits from ``bytes`` (MSB first). */
function unpackCounts(bytes: Uint8Array, width: number, n: number): number[] {
  let acc = 0n;
  for (const b of bytes) acc = (acc << 8n) | BigInt(b);
  const total = BigInt(bytes.length * 8);
  const mask = (1n << BigInt(width)) - 1n;
  return Array.from({ length: n }, (_, i) =>
    Number((acc >> (total - BigInt(width * (i + 1)))) & mask),
  );
}

export function decodeFrame(buf: Uint8Array, offset: number): [NgfFrame, number] {
  const version = (buf[offset]! & 0b1110_0000) >> 5;
  const size = FRAME_SIZES[version];
  if (!size) throw new Error(`unknown NGF frame version ${version} at ${offset}`);
  if (buf.length - offset < size) throw new Error(`truncated NGF frame at ${offset}`);
  const f = buf.subarray(offset, offset + size);
  const frame: NgfFrame = {
    version,
    gameid: (f[1]! << 8) | f[2]!,
    ctimeMs: f[3]! * 0x100000 + (f[4]! << 12) + (f[5]! << 4) + ((f[6]! & 0xf0) >> 4),
    score: null,
    lines: null,
    level: null,
    preview: piece(f[12]! & 0b111),
    curPiece: piece(f[13]! & 0b111),
    counts: [],
    cells: new Uint8Array(200),
  };
  let fieldStart: number;
  if (version >= 2) {
    frame.lines = orNull(((f[6]! & 0x0f) << 8) | f[7]!, 0xfff);
    frame.level = orNull(f[8]!, 0xff);
    frame.score = orNull(f[9]! * 0x10000 + (f[10]! << 8) + f[11]!, 0xffffff);
    const counts =
      version === 3 ? unpackCounts(f.subarray(14, 23), 10, 7) : unpackCounts(f.subarray(14, 22), 9, 7);
    const sentinel = version === 3 ? 0x3ff : 0x1ff;
    frame.counts = counts.map((c) => orNull(c, sentinel));
    fieldStart = version === 3 ? 23 : 22;
  } else {
    const score = (f[7]! & 0x0f) * 0x20000 + (f[8]! << 9) + (f[9]! << 1) + ((f[10]! & 0x80) >> 7);
    frame.score = orNull(score, 0x1fffff);
    frame.lines = orNull(((f[10]! & 0x7f) << 2) | ((f[11]! & 0xc0) >> 6), 0x1ff);
    frame.level = orNull(f[11]! & 0x3f, 0x3f);
    frame.counts = Array.from({ length: 7 }, (_, i) => orNull(f[14 + i]!, 0xff));
    fieldStart = 21;
  }
  frame.cells = unpackField(f, fieldStart);
  return [frame, size];
}

export function decodeNgf(raw: Uint8Array): NgfFrame[] {
  const frames: NgfFrame[] = [];
  let offset = 0;
  while (offset < raw.length) {
    const [frame, size] = decodeFrame(raw, offset);
    frames.push(frame);
    offset += size;
  }
  return frames;
}

/** A new gameid or a ctime reset starts a new game. */
export function splitGames(frames: NgfFrame[]): NgfFrame[][] {
  const games: NgfFrame[][] = [];
  for (const f of frames) {
    const current = games[games.length - 1];
    const last = current?.[current.length - 1];
    if (!current || !last || f.gameid !== last.gameid || f.ctimeMs < last.ctimeMs) games.push([f]);
    else current.push(f);
  }
  return games;
}

export async function gunzipIfNeeded(data: Uint8Array): Promise<Uint8Array> {
  if (data[0] !== 0x1f || data[1] !== 0x8b) return data;
  const stream = new Blob([data as BlobPart]).stream().pipeThrough(new DecompressionStream("gzip"));
  return new Uint8Array(await new Response(stream).arrayBuffer());
}

/** Fetch and decode a game's recording (``/api/games/<id>/recording``). */
export async function loadRecording(url: string): Promise<{ frames: NgfFrame[]; source: string }> {
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) throw new Error(`recording: ${response.status}`);
  const raw = await gunzipIfNeeded(new Uint8Array(await response.arrayBuffer()));
  const games = splitGames(decodeNgf(raw));
  // A game's recording holds one game; take the longest just in case.
  const frames = games.sort((a, b) => b.length - a.length)[0] ?? [];
  return { frames, source: response.headers.get("X-Recording-Source") ?? "recording" };
}

/** Playfield rows ("0123..." per row) as used by <Playfield>. */
export function rowsFromCells(cells: Uint8Array): string[] {
  const rows: string[] = [];
  for (let y = 0; y < 20; y++) rows.push(Array.from(cells.subarray(y * 10, y * 10 + 10)).join(""));
  return rows;
}
