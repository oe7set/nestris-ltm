import { describe, expect, it } from "vitest";
import { newProblems, type AttentionItem } from "./attention.svelte";

const item = (code: string, count: number, severity: AttentionItem["severity"] = "warn"): AttentionItem => ({
  code,
  count,
  severity,
  link: "/",
  names: [],
});

describe("newProblems", () => {
  it("announces nothing on the first load", () => {
    expect(newProblems(null, [item("spool_failed", 3, "error")])).toEqual([]);
  });

  it("announces new and growing problems, not hints or shrinking ones", () => {
    const before = [item("spool_failed", 1, "error"), item("unassigned_games", 4)];
    const now = [
      item("spool_failed", 2, "error"),
      item("unassigned_games", 9),
      item("stations_offline", 1, "error"),
      item("auto_players", 5, "info"),
    ];
    expect(newProblems(before, now).map((i) => i.code)).toEqual(["spool_failed", "stations_offline"]);
    expect(newProblems(now, [item("spool_failed", 1, "error")])).toEqual([]);
  });
});
