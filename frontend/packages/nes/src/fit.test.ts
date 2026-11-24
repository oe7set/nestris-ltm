import { describe, expect, it } from "vitest";
import { NAME_CHARS, STAT_CHARS, textMode, textPx, type TextFit } from "./fit";

const box = { w: 240, h: 90, share: 0.5 };

function px(over: Partial<TextFit>): number {
  return textPx({ reserved: 7, actual: 1, ...box, nes: true, ...over });
}

describe("textPx", () => {
  it("stable: the size does not follow the text up to the reservation", () => {
    const sizes = ["0", "1,234", "99,999", "999,999"].map((v) => px({ actual: v.length }));
    expect(new Set(sizes).size).toBe(1);
  });

  it("stable: text longer than reserved shrinks, never grows", () => {
    expect(px({ actual: 11 })).toBeLessThan(px({ actual: 7 }));
    expect(px({ actual: 11 })).toBeLessThanOrEqual(px({ mode: "fit", actual: 11 }));
  });

  it("fit: follows the text (old behaviour)", () => {
    expect(px({ mode: "fit", actual: 1 })).toBeGreaterThan(px({ mode: "fit", actual: 7 }));
  });

  it("fixed: the given size, on the 8 px grid in the NES style", () => {
    expect(px({ mode: "fixed", size: 30 })).toBe(24);
    expect(px({ mode: "fixed", size: 30, nes: false })).toBe(30);
    expect(px({ mode: "fixed", size: 3 })).toBe(8);
  });

  it("unknown or missing modes are stable", () => {
    expect(textMode(undefined)).toBe("stable");
    expect(textMode("glow")).toBe("stable");
    expect(px({ mode: "fixed" })).toBe(px({})); // fixed without a size
  });

  it("reserves room for the longest usual values", () => {
    expect(STAT_CHARS.score).toBe("999,999".length);
    expect(NAME_CHARS).toBeGreaterThanOrEqual(8);
  });
});
