import { describe, expect, it } from "vitest";
import type { LayoutDefinition } from "../studio";
import { align, arrange, distribute, gapCandidates, matchSize, measure, measureBetween, snapMove, STAGE } from "./geometry";
import { LayoutEditor } from "./layoutEditor.svelte";

const a = { x: 100, y: 100, w: 100, h: 50 };
const b = { x: 400, y: 300, w: 200, h: 100 };
const c = { x: 900, y: 120, w: 50, h: 50 };

describe("arrange geometry", () => {
  it("aligns to a reference box", () => {
    expect(align([a, b], "left", c).map((r) => r.x)).toEqual([900, 900]);
    expect(align([a], "hcenter", STAGE)[0]!.x).toBe(910);
  });

  it("distributes with a fixed gap from the first one on", () => {
    expect(distribute([b, a, c], "x", 10).map((r) => r.x)).toEqual([210, 100, 420]);
    // Without a gap: equal gaps between first and last, as before.
    expect(distribute([a, b, c], "x").map((r) => r.x)).toEqual([100, 450, 900]);
  });

  it("lines up a row (centred on one line), a column and a grid", () => {
    expect(arrange([b, a, c], "row", 8)).toEqual([
      { x: 208, y: 100, w: 200, h: 100 },
      { x: 100, y: 125, w: 100, h: 50 },
      { x: 416, y: 125, w: 50, h: 50 },
    ]);
    const col = arrange([a, b], "column", 0);
    expect(col[1]!.y).toBe(col[0]!.y + col[0]!.h);
    const grid = arrange([a, b, c, { x: 950, y: 400, w: 60, h: 40 }], "grid", 10, 2);
    expect(new Set(grid.map((r) => r.y + r.h / 2)).size).toBe(2); // two rows
  });

  it("matches the size of a reference, keeping each centre", () => {
    expect(matchSize([a], b, "w")[0]).toEqual({ x: 50, y: 100, w: 200, h: 50 });
    expect(matchSize([a], b, "both")[0]).toEqual({ x: 50, y: 75, w: 200, h: 100 });
  });

  it("measures distances to the neighbours or the stage edge", () => {
    const m = measure({ x: 300, y: 100, w: 100, h: 50 }, [a]);
    expect(m).toContainEqual({ axis: "x", from: 200, to: 300, at: 125 }); // to a
    expect(m).toContainEqual({ axis: "x", from: 400, to: 1920, at: 125 }); // to the stage edge
    expect(m).toContainEqual({ axis: "y", from: 0, to: 100, at: 350 });
    expect(measureBetween(a, b)).toEqual([
      { axis: "x", from: 200, to: 400, at: expect.any(Number) },
      { axis: "y", from: 150, to: 300, at: expect.any(Number) },
    ]);
  });

  it("snaps to equal spacing in a row", () => {
    const row = [
      { x: 0, y: 0, w: 100, h: 100 },
      { x: 140, y: 0, w: 100, h: 100 },
    ];
    expect(gapCandidates({ x: 285, y: 0, w: 100, h: 100 }, row, "x")).toContain(280);
    const moved = snapMove({ x: 500, y: 0, w: 100, h: 100 }, -217, 0, { targets: row, threshold: 6, grid: 1 });
    expect(moved.dx).toBe(-220); // 500 - 220 = 280: the same 40 px gap
  });
});

function def(): LayoutDefinition {
  return {
    schema: 1,
    slots: 2,
    pairs: [],
    elements: [
      { id: "frame-1", type: "frame", x: 0, y: 0, w: 1000, h: 600 },
      { id: "s1", type: "stat", slot: 0, x: 100, y: 100, w: 200, h: 80, props: { field: "score", frame: "none", text_size: 24, text_mode: "fixed" } },
      { id: "s2", type: "stat", slot: 1, x: 400, y: 300, w: 100, h: 40, props: { field: "lines", align: "right" } },
      { id: "n1", type: "name", slot: 0, x: 600, y: 100, w: 200, h: 60 },
    ],
  };
}

describe("LayoutEditor arranging", () => {
  it("aligns to the key element (selected first), which stays put", () => {
    const ed = new LayoutEditor();
    ed.load(def());
    ed.selected = ["s2", "s1"];
    ed.alignSelected("left", "key");
    expect(ed.def.elements.find((e) => e.id === "s1")!.x).toBe(400);
    expect(ed.def.elements.find((e) => e.id === "s2")!.x).toBe(400);
  });

  it("centres in the frame around the selection", () => {
    const ed = new LayoutEditor();
    ed.load(def());
    ed.selected = ["s1"];
    expect(ed.frameAround()?.id).toBe("frame-1");
    ed.alignSelected("hcenter", "frame");
    expect(ed.def.elements.find((e) => e.id === "s1")!.x).toBe(400);
  });

  it("selects alike and copies a style without the content", () => {
    const ed = new LayoutEditor();
    ed.load(def());
    ed.selected = ["s1"];
    ed.selectSimilar("slot");
    expect(ed.selected).toEqual(["s1", "n1"]);
    ed.selected = ["s1"];
    ed.copyStyle();
    ed.selected = ["s2", "n1"];
    expect(ed.canPasteStyle).toBe(true);
    ed.pasteStyle();
    const s2 = ed.def.elements.find((e) => e.id === "s2")!;
    expect(s2.props).toEqual({ field: "lines", frame: "none", text_size: 24, text_mode: "fixed" });
    expect(ed.def.elements.find((e) => e.id === "n1")!.props).toBeUndefined(); // other type: untouched
  });
});
