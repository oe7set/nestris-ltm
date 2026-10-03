import { describe, expect, it } from "vitest";
import { diffSeries } from "./graph";
import { clearedLines } from "./view";
import { levelColors, parseRows } from "./nes";
import { fmt, signed } from "./format";

describe("overlay helpers", () => {
  it("builds a step-interpolated diff series", () => {
    const a: [number, number][] = [[0, 0], [1000, 1200], [3000, 5000]];
    const b: [number, number][] = [[0, 0], [2000, 3000]];
    expect(diffSeries(a, b)).toEqual([[0, 0], [1000, 1200], [2000, -1800], [3000, 2000]]);
  });

  it("removes misread spikes", () => {
    const a: [number, number][] = [[0, 100], [1000, 90000], [2000, 200], [3000, 300]];
    expect(diffSeries(a, [])).toEqual([[0, 100], [1000, 200], [2000, 200], [3000, 300]]);
  });

  it("detects line clears between frames", () => {
    expect(clearedLines(10, 14)).toBe(4);
    expect(clearedLines(10, 10)).toBe(0);
    expect(clearedLines(10, 30)).toBe(0); // OCR jump, not a clear
    expect(clearedLines(null, 4)).toBe(0);
  });

  it("parses playfields and palettes", () => {
    expect(parseRows(["0".repeat(10)])).toBeNull();
    const rows = Array.from({ length: 20 }, () => "0123000000");
    expect(parseRows(rows)?.[0]?.slice(0, 4)).toEqual([0, 1, 2, 3]);
    expect(levelColors(18)).toEqual(levelColors(8));
  });

  it("formats numbers", () => {
    expect(fmt(216560)).toBe("216 560");
    expect(signed(-1200)).toBe("−1 200");
    expect(signed(0)).toBe("±0");
  });
});
