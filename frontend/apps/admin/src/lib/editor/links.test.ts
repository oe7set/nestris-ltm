import { describe, expect, it } from "vitest";
import type { LayoutDefinition, LayoutElement } from "../studio";
import { LayoutEditor } from "./layoutEditor.svelte";
import { applyLinks, applyPreset, LINK_PRESETS, linkedId, linkOrigins, linkRect, removeLink, setLink } from "./links";

const preset = (id: string) => LINK_PRESETS.find((p) => p.id === id)!;

function quad(): LayoutDefinition {
  return {
    schema: 1,
    slots: 4,
    pairs: [
      [0, 1],
      [2, 3],
    ],
    elements: [
      { id: "board-s0", type: "board", slot: 0, x: 700, y: 8, w: 240, h: 460 },
      { id: "score-s0", type: "stat", slot: 0, x: 500, y: 8, w: 192, h: 72, props: { field: "score", align: "left" } },
      { id: "vs", type: "versus", pair: 0, x: 900, y: 200, w: 120, h: 100 },
      { id: "title", type: "title", x: 600, y: 1000, w: 720, h: 56 },
    ],
  };
}

const bySlot = (d: LayoutDefinition, slot: number): LayoutElement[] => d.elements.filter((e) => e.slot === slot);

describe("links", () => {
  it("mirrors at the stage centre, then moves", () => {
    const r = { x: 100, y: 50, w: 200, h: 100 };
    expect(linkRect(r, { from: 0, to: 1, flip_x: true })).toEqual({ x: 1620, y: 50, w: 200, h: 100 });
    expect(linkRect(r, { from: 0, to: 1, dy: 540 })).toEqual({ x: 100, y: 590, w: 200, h: 100 });
    expect(linkRect(r, { from: 0, to: 1, flip_y: true })).toEqual({ x: 100, y: 930, w: 200, h: 100 });
  });

  it("gives copies stable ids", () => {
    expect(linkedId("score-s0", { from: 0, to: 3 })).toBe("score-s3");
    expect(linkedId("vs", { from: 0, to: 1, pair: true })).toBe("vs-m1");
    expect(linkedId("x".repeat(32), { from: 0, to: 2 }).length).toBeLessThanOrEqual(32);
  });

  it("4 quarters mirrored: three quarters follow slot 1, pairs follow too", () => {
    const d = applyPreset(quad(), preset("quad_mirror"));
    expect(bySlot(d, 1).find((e) => e.type === "board")).toMatchObject({ id: "board-s1", x: 1920 - 700 - 240, y: 8 });
    expect(bySlot(d, 2).find((e) => e.type === "board")).toMatchObject({ x: 700, y: 548 });
    expect(bySlot(d, 3).find((e) => e.type === "stat")).toMatchObject({ x: 1920 - 500 - 192, y: 548, props: { align: "right" } });
    expect(d.elements.find((e) => e.pair === 1)).toMatchObject({ id: "vs-m1", type: "versus", y: 740 });
    expect(d.elements.find((e) => e.id === "title")).toMatchObject({ x: 600, y: 1000 }); // general: untouched
  });

  it("4 quarters alike keeps the arrangement", () => {
    const d = applyPreset(quad(), preset("quad_same"));
    expect(bySlot(d, 3).find((e) => e.type === "stat")).toMatchObject({ x: 1460, y: 548, props: { align: "left" } });
  });

  it("copies follow every change of the master and are mapped back to it", () => {
    let d = applyPreset(quad(), preset("quad_mirror"));
    d = applyLinks({ ...d, elements: d.elements.map((e) => (e.id === "board-s0" ? { ...e, x: 720 } : e)) });
    expect(d.elements.find((e) => e.id === "board-s2")!.x).toBe(720);
    expect(d.elements.find((e) => e.id === "board-s1")!.x).toBe(1920 - 720 - 240);
    expect(linkOrigins(d).get("board-s3")).toBe("board-s0");
    expect(linkOrigins(d).has("board-s0")).toBe(false);
  });

  it("does not change an unlinked definition", () => {
    const d = quad();
    expect(applyLinks(d)).toBe(d);
  });

  it("allows no chains and one master per target", () => {
    let d = setLink(quad(), { from: 0, to: 1, flip_x: true });
    d = setLink(d, { from: 1, to: 2 }); // slot 1 becomes a master: its own link goes
    expect(d.links).toEqual([{ from: 1, to: 2 }]);
    d = setLink(d, { from: 0, to: 2, dy: 540 });
    expect(d.links).toEqual([{ from: 0, to: 2, dy: 540 }]);
  });

  it("unlinking keeps the copies as ordinary elements", () => {
    const d = removeLink(applyPreset(quad(), preset("mirror_lr")), 0);
    expect(d.links).toBeUndefined();
    expect(bySlot(d, 1)).toHaveLength(2);
    expect(linkOrigins(d).size).toBe(0);
  });

  it("drops links of slots that no longer exist", () => {
    const d = applyLinks({ ...applyPreset(quad(), preset("quad_mirror")), slots: 2, pairs: [[0, 1]] });
    expect(d.links).toEqual([{ from: 0, to: 1, flip_x: true }]);
  });
});

describe("LayoutEditor with links", () => {
  it("moves the copies with the master in one undo step; a copy selects its master", () => {
    const ed = new LayoutEditor();
    ed.load(applyPreset(quad(), preset("quad_mirror")));
    ed.select("board-s3");
    expect(ed.selected).toEqual(["board-s0"]);
    ed.nudge(8, 0);
    expect(ed.def.elements.find((e) => e.id === "board-s2")!.x).toBe(708);
    ed.undo();
    expect(ed.def.elements.find((e) => e.id === "board-s2")!.x).toBe(700);
    ed.selectAll();
    expect(ed.selected.every((id) => !ed.origins.has(id))).toBe(true);
  });
});
