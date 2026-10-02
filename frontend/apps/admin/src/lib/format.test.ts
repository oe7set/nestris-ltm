import { describe, expect, it } from "vitest";
import { duration, fromLocalInput, num, pct, toLocalInput } from "./format";

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
});
