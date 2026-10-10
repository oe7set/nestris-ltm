import { describe, expect, it } from "vitest";
import { duration, fromLocalInput, num, parseScore, pct, toLocalInput } from "./format";

describe("format", () => {
  it("formats numbers and percentages", () => {
    expect(num(null)).toBe("–");
    expect(num(216560, "en")).toBe("216,560");
    expect(pct(0.5373, "en")).toBe("53.7 %");
  });

  it("formats durations", () => {
    expect(duration(431.2)).toBe("7:11");
    expect(duration(null)).toBe("–");
  });

  it("round-trips datetime-local values", () => {
    const iso = "2026-10-02T14:30:00.000Z";
    expect(fromLocalInput(toLocalInput(iso))).toBe(iso);
    expect(fromLocalInput("")).toBeNull();
  });

  it("reads scores typed into a filter", () => {
    expect(parseScore("")).toBeNull();
    expect(parseScore("  ")).toBeNull();
    expect(parseScore("250000")).toBe(250000);
    expect(parseScore("250.000")).toBe(250000);
    expect(parseScore("1,000,000")).toBe(1000000);
    expect(parseScore("250 000")).toBe(250000);
    expect(parseScore("250k")).toBe(250000);
    expect(parseScore("1,5M")).toBe(1500000);
    expect(parseScore("1.25m")).toBe(1250000);
    expect(parseScore("12.5")).toBeUndefined();
    expect(parseScore("-5")).toBeUndefined();
    expect(parseScore("abc")).toBeUndefined();
  });
});
