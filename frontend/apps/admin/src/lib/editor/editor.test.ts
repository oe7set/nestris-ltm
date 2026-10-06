import { describe, expect, it } from "vitest";
import type { LayoutDefinition } from "../studio";
import {
  addElements,
  cloneElements,
  emptyDefinition,
  inMarquee,
  localProblems,
  newElement,
  placeable,
  restack,
  setPairs,
  setSlots,
  uniqueId,
} from "./elements";
import { align, clamp, distribute, MARGIN_W, MIN_SIZE, resize, snapMove, snapToGrid } from "./geometry";
import { History } from "./history";
import { mirrorElement, mirrorSlot } from "./mirror";

const free = { targets: [], threshold: 0, free: true };

describe("geometry", () => {
  it("snaps a move to the grid when nothing is near", () => {
    const r = snapMove({ x: 100, y: 100, w: 50, h: 50 }, 13, 2, { targets: [], threshold: 0 });
    expect(r).toEqual({ dx: 12, dy: 4, guides: [] });
  });

  it("snaps edges and centres to other elements and shows a guide", () => {
    const target = { x: 500, y: 0, w: 100, h: 100 };
    // right edge 150 + dx 345 = 495 -> snaps to the target's left edge 500
    const r = snapMove({ x: 100, y: 300, w: 50, h: 50 }, 345, 0, { targets: [target], threshold: 8 });
    expect(r.dx).toBe(350);
    expect(r.guides).toContainEqual({ axis: "x", at: 500 });
  });

  it("snaps to the stage centre", () => {
    const r = snapMove({ x: 0, y: 0, w: 100, h: 100 }, 906, 0, { targets: [], threshold: 8 });
    expect(r.dx).toBe(910); // centre 50 + 910 = 960
  });

  it("moves freely with Alt", () => {
    expect(snapMove({ x: 0, y: 0, w: 10, h: 10 }, 13.4, 2.6, free)).toEqual({ dx: 13, dy: 3, guides: [] });
  });

  it("resizes from any handle and keeps the minimum size", () => {
    const r = { x: 100, y: 100, w: 200, h: 100 };
    expect(resize(r, "se", 40, 20, free).rect).toEqual({ x: 100, y: 100, w: 240, h: 120 });
    expect(resize(r, "nw", 40, 20, free).rect).toEqual({ x: 140, y: 120, w: 160, h: 80 });
    expect(resize(r, "w", 500, 0, free).rect.w).toBe(MIN_SIZE);
    expect(resize(r, "n", 0, 500, free).rect.h).toBe(MIN_SIZE);
    // Edge handles leave the other axis alone.
    expect(resize(r, "e", 40, 999, free).rect).toEqual({ x: 100, y: 100, w: 240, h: 100 });
  });

  it("keeps the aspect ratio on corner handles with Shift", () => {
    const r = resize({ x: 0, y: 0, w: 200, h: 100 }, "se", 100, 0, free, true).rect;
    expect(r.w / r.h).toBe(2);
  });

  it("clamps to what the server accepts", () => {
    expect(clamp({ x: -5000, y: 0, w: 2, h: 50 })).toEqual({ x: -MARGIN_W, y: 0, w: MIN_SIZE, h: 50 });
    expect(snapToGrid(13)).toBe(16);
  });

  it("aligns and distributes", () => {
    const rs = [
      { x: 0, y: 0, w: 10, h: 10 },
      { x: 50, y: 20, w: 20, h: 10 },
      { x: 200, y: 40, w: 10, h: 10 },
    ];
    expect(align(rs, "left").map((r) => r.x)).toEqual([0, 0, 0]);
    expect(align(rs, "bottom").map((r) => r.y)).toEqual([40, 40, 40]);
    // One element aligns to the stage.
    expect(align([{ x: 5, y: 5, w: 100, h: 10 }], "hcenter")[0]!.x).toBe(910);
    const d = distribute(rs, "x");
    // total 210, used 40 -> gap 85: 0, 95, 200
    expect(d.map((r) => r.x)).toEqual([0, 95, 200]);
  });
});

describe("history", () => {
  it("undoes and redoes, and a new edit clears redo", () => {
    const h = new History<number>();
    h.record(1);
    h.record(2);
    expect(h.undo(3)).toBe(2);
    expect(h.undo(2)).toBe(1);
    expect(h.undo(1)).toBeNull();
    expect(h.redo(1)).toBe(2);
    h.record(2);
    expect(h.canRedo).toBe(false);
  });

  it("merges quick edits with the same key", () => {
    let now = 0;
    const h = new History<string>({ now: () => now, mergeMs: 500 });
    h.record("a", "x");
    now = 100;
    h.record("ab", "x");
    now = 2000;
    h.record("abc", "x");
    expect(h.size).toBe(2);
    expect(h.undo("abcd")).toBe("abc");
    expect(h.undo("abc")).toBe("a");
  });

  it("keeps at most the limit", () => {
    const h = new History<number>({ limit: 3 });
    for (let i = 0; i < 10; i++) h.record(i);
    expect(h.size).toBe(3);
    expect(h.undo(10)).toBe(9);
  });
});

function sample(): LayoutDefinition {
  const def = emptyDefinition(2);
  const board = newElement(def, "board", 400, 500, 0);
  const d1 = addElements(def, [board]);
  const score = { ...newElement(d1, "stat", 200, 100, 0), id: "score-s0", props: { field: "score", align: "left" } };
  const d2 = addElements(d1, [score]);
  return addElements(d2, [newElement(d2, "versus")]);
}

describe("elements", () => {
  it("creates valid elements with unique ids on top", () => {
    const def = sample();
    expect(def.elements.map((e) => e.id)).toEqual(["board-1", "score-s0", "versus-1"]);
    expect(def.elements[2]!.pair).toBe(0);
    expect(def.elements[2]!.z).toBeGreaterThan(def.elements[0]!.z!);
    expect(uniqueId(def, "board-1")).toBe("board-2");
    expect(localProblems(def).size).toBe(0);
    expect(placeable(emptyDefinition(3), "versus")).toBe(false);
  });

  it("drops what belongs to removed slots and pairs", () => {
    const { def, removed } = setSlots(sample(), 1);
    expect(def.pairs).toEqual([]);
    expect(def.elements.map((e) => e.id)).toEqual(["board-1", "score-s0"]);
    expect(removed).toBe(1);
    const back = setSlots(setSlots(sample(), 2).def, 1);
    expect(back.def.slots).toBe(1);
  });

  it("keeps pair elements with their pair when pairs are reordered", () => {
    const base = setSlots(sample(), 4).def;
    const two = setPairs(base, [[0, 1], [2, 3]]).def;
    const reordered = setPairs(two, [[2, 3], [1, 0]]);
    expect(reordered.removed).toBe(0);
    expect(reordered.def.elements.find((e) => e.type === "versus")!.pair).toBe(1);
  });

  it("clones with fresh ids and fits slots of the target layout", () => {
    const def = sample();
    const copies = cloneElements(emptyDefinition(1), def.elements);
    expect(copies.map((e) => e.type)).toEqual(["board", "stat"]); // no pair to put versus in
    expect(copies.every((e) => (e.slot ?? 0) < 1)).toBe(true);
    const again = cloneElements(def, [def.elements[0]!]);
    expect(again[0]!.id).toBe("board-2");
    expect(again[0]!.x).toBe(def.elements[0]!.x + 16);
  });

  it("restacks and selects by marquee", () => {
    const def = sample();
    const top = restack(def, "board-1", "top");
    const z = (d: LayoutDefinition, id: string): number => d.elements.find((e) => e.id === id)!.z!;
    expect(z(top, "board-1")).toBeGreaterThan(z(top, "versus-1"));
    expect(inMarquee(def, { x: 0, y: 0, w: 300, h: 120 })).toEqual(["score-s0"]);
  });
});

describe("mirror", () => {
  it("mirrors position and alignment", () => {
    const m = mirrorElement({ id: "a", type: "stat", slot: 0, x: 100, y: 50, w: 200, h: 80, props: { align: "left" } });
    expect([m.x, m.y, m.props?.align]).toEqual([1620, 50, "right"]);
  });

  it("builds the other side of a 1 vs 1", () => {
    const { def, replaced } = mirrorSlot(sample(), 0, 1);
    expect(replaced).toBe(0);
    const right = def.elements.filter((e) => e.slot === 1);
    expect(right.map((e) => e.id).sort()).toEqual(["board-2", "score-s1"]);
    // Again: the old right side is replaced, not doubled.
    const again = mirrorSlot(def, 0, 1);
    expect(again.replaced).toBe(2);
    expect(again.def.elements.filter((e) => e.slot === 1)).toHaveLength(2);
  });
});
