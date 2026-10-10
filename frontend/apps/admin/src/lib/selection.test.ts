import { describe, expect, it } from "vitest";
import { Selection } from "./selection.svelte";

const rows = (...ids: number[]) => ids.map((id) => ({ id, name: `r${id}` }));

describe("Selection", () => {
  it("toggles rows and reports the page state", () => {
    const sel = new Selection<{ id: number; name: string }>();
    const page = rows(1, 2, 3);
    expect(sel.pageState(page)).toBe("none");
    sel.toggle(page[0]!);
    expect(sel.has(1)).toBe(true);
    expect(sel.pageState(page)).toBe("some");
    sel.setMany(page, true);
    expect(sel.pageState(page)).toBe("all");
    expect(sel.size).toBe(3);
    sel.toggle(page[0]!);
    expect(sel.ids).toEqual([2, 3]);
  });

  it("keeps rows of other pages", () => {
    const sel = new Selection<{ id: number; name: string }>();
    sel.setMany(rows(1, 2), true);
    sel.setMany(rows(3, 4), true);
    sel.setMany(rows(3, 4), false);
    expect(sel.ids).toEqual([1, 2]);
    expect(sel.rows.map((r) => r.name)).toEqual(["r1", "r2"]);
  });

  it("respects the limit", () => {
    const sel = new Selection<{ id: number; name: string }>(2);
    sel.setMany(rows(1, 2, 3), true);
    expect(sel.size).toBe(2);
    expect(sel.toggle(rows(9)[0]!)).toBe(false);
    expect(sel.toggle(rows(1)[0]!)).toBe(true); // removing always works
  });

  it("forgets and clears", () => {
    const sel = new Selection<{ id: number; name: string }>();
    sel.setMany(rows(1, 2, 3), true);
    sel.forget([2]);
    expect(sel.ids).toEqual([1, 3]);
    sel.clear();
    expect(sel.size).toBe(0);
  });
});
