import { readFileSync, existsSync } from "node:fs";
import { gunzipSync } from "node:zlib";
import { describe, expect, it } from "vitest";
import { decodeFrame, decodeNgf, rowsFromCells, splitGames } from "./ngf";
import { Timeline } from "./replay";

/** Build a v3 frame like core/ngf.py's encode_frame. */
function v3(ctime: number, score: number, lines: number, level: number, gameid = 1): Uint8Array {
  const out = new Uint8Array(73);
  out[0] = (3 << 5) | (1 << 3);
  out[1] = gameid >> 8;
  out[2] = gameid & 0xff;
  out[3] = (ctime >> 20) & 0xff;
  out[4] = (ctime >> 12) & 0xff;
  out[5] = (ctime >> 4) & 0xff;
  out[6] = ((ctime & 0x0f) << 4) | (lines >> 8);
  out[7] = lines & 0xff;
  out[8] = level;
  out[9] = (score >> 16) & 0xff;
  out[10] = (score >> 8) & 0xff;
  out[11] = score & 0xff;
  out[12] = (0x1f << 3) | 6; // DAS unknown, next = I
  out[13] = (0x1f << 3) | 7;
  // counts: T=5, others unknown (0x3ff)
  let acc = 5n;
  for (let i = 1; i < 7; i++) acc = (acc << 10n) | 0x3ffn;
  acc <<= 2n;
  for (let i = 8; i >= 0; i--) {
    out[14 + i] = Number(acc & 0xffn);
    acc >>= 8n;
  }
  out[23] = 0b11_00_00_01; // first cells: 3,0,0,1
  return out;
}

describe("NGF decoder", () => {
  it("decodes a v3 frame", () => {
    const [f, size] = decodeFrame(v3(0x0abcdef, 216560, 134, 18), 0);
    expect(size).toBe(73);
    expect(f.ctimeMs).toBe(0x0abcdef);
    expect([f.score, f.lines, f.level]).toEqual([216560, 134, 18]);
    expect(f.preview).toBe("I");
    expect(f.curPiece).toBeNull();
    expect(f.counts).toEqual([5, null, null, null, null, null, null]);
    expect(Array.from(f.cells.subarray(0, 4))).toEqual([3, 0, 0, 1]);
    expect(rowsFromCells(f.cells)[0]).toBe("3001000000");
  });

  it("splits games and drives the timeline", () => {
    const parts = [v3(0, 0, 0, 18), v3(1000, 100, 1, 18), v3(2000, 200, 2, 18), v3(0, 0, 0, 19, 2)];
    const raw = new Uint8Array(parts.reduce((n, p) => n + p.length, 0));
    let o = 0;
    for (const p of parts) {
      raw.set(p, o);
      o += p.length;
    }
    const games = splitGames(decodeNgf(raw));
    expect(games.map((g) => g.length)).toEqual([3, 1]);

    const t = new Timeline(games[0]!);
    expect(t.duration).toBe(2000);
    t.play(0);
    expect(t.tick(1500)).toBe(1);
    t.speed = 2;
    expect(t.tick(2000)).toBe(2); // 1500 + 500*2 = 2500 -> clamped, ended
    expect(t.playing).toBe(false);
    t.seek(999);
    expect(t.index()).toBe(0);
    t.step(1);
    expect(t.index()).toBe(1);
  });

  const sample = "../../../../0QR5AJ2RRDPNMZK5FT53K.ngf";
  it.skipIf(!existsSync(sample))("decodes a real recording", () => {
    let data = new Uint8Array(readFileSync(sample));
    if (data[0] === 0x1f) data = new Uint8Array(gunzipSync(data));
    const frames = decodeNgf(data);
    expect(frames.length).toBe(18261);
    expect(frames[frames.length - 1]!.score).toBe(216560);
  });
});
