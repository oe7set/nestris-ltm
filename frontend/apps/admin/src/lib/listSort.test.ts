import { describe, expect, it } from "vitest";
import { defaultDir, nextSort, readSort, sortParams } from "./listSort";

const TEXT = ["player"];

describe("listSort", () => {
  it("starts names A-Z and numbers high first", () => {
    expect(defaultDir("player", TEXT)).toBe("asc");
    expect(defaultDir("score", TEXT)).toBe("desc");
  });

  it("turns the direction on the same column only", () => {
    const s = { key: "score", dir: "desc" as const };
    expect(nextSort(s, "score", TEXT)).toEqual({ key: "score", dir: "asc" });
    expect(nextSort(s, "player", TEXT)).toEqual({ key: "player", dir: "asc" });
    expect(nextSort({ key: "player", dir: "asc" }, "lines", TEXT)).toEqual({ key: "lines", dir: "desc" });
  });

  it("reads and writes the URL", () => {
    const keys = ["started_at", "score", "player"];
    expect(readSort(new URLSearchParams(""), keys, "started_at", TEXT)).toEqual({ key: "started_at", dir: "desc" });
    expect(readSort(new URLSearchParams("sort=player"), keys, "started_at", TEXT)).toEqual({ key: "player", dir: "asc" });
    expect(readSort(new URLSearchParams("sort=x&dir=up"), keys, "started_at", TEXT)).toEqual({ key: "started_at", dir: "desc" });
    expect(sortParams({ key: "started_at", dir: "desc" }, "started_at", TEXT)).toEqual({ sort: null, dir: null });
    expect(sortParams({ key: "score", dir: "asc" }, "started_at", TEXT)).toEqual({ sort: "score", dir: "asc" });
  });
});
