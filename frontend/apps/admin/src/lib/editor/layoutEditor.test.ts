import { describe, expect, it } from "vitest";
import type { LayoutDefinition } from "../studio";
import { LayoutEditor } from "./layoutEditor.svelte";

function def(): LayoutDefinition {
  return {
    schema: 1,
    slots: 2,
    pairs: [[0, 1]],
    elements: [
      { id: "board-a", type: "board", slot: 0, x: 100, y: 100, w: 336, h: 696 },
      { id: "board-b", type: "board", slot: 1, x: 1400, y: 100, w: 336, h: 696, locked: true },
    ],
  };
}

describe("LayoutEditor", () => {
  it("records every edit for undo and redo, and load starts over", () => {
    const ed = new LayoutEditor();
    ed.load(def());
    expect(ed.canUndo).toBe(false);
    ed.selected = ["board-a"];
    ed.nudge(8, 0);
    ed.patch("board-a", { hidden: true });
    expect(ed.def.elements[0]).toMatchObject({ x: 108, hidden: true });
    ed.undo();
    expect(ed.def.elements[0]!.hidden).toBeUndefined();
    ed.undo();
    expect(ed.def.elements[0]!.x).toBe(100);
    expect(ed.canUndo).toBe(false);
    ed.redo();
    expect(ed.def.elements[0]!.x).toBe(108);
    ed.load(def());
    expect(ed.canUndo || ed.canRedo).toBe(false);
  });

  it("changes nothing while a fixed layout is shown", () => {
    const ed = new LayoutEditor();
    ed.load(def());
    ed.editable = false;
    ed.selected = ["board-a"];
    ed.nudge(8, 0);
    ed.removeSelected();
    expect(ed.def.elements).toHaveLength(2);
    expect(ed.def.elements[0]!.x).toBe(100);
  });

  it("keeps locked elements in place and centres the selection on the stage", () => {
    const ed = new LayoutEditor();
    ed.load(def());
    ed.selected = ["board-b"];
    ed.removeSelected();
    expect(ed.def.elements).toHaveLength(2); // locked: not deleted
    ed.selected = ["board-a"];
    ed.centreSelected("both");
    expect(ed.def.elements[0]).toMatchObject({ x: (1920 - 336) / 2, y: (1080 - 696) / 2 });
  });

  it("adds new elements to the chosen slot and selects them", () => {
    const ed = new LayoutEditor();
    ed.load(def());
    ed.addSlot = 1;
    ed.add("next");
    const added = ed.def.elements.at(-1)!;
    expect(added).toMatchObject({ type: "next", slot: 1 });
    expect(ed.selected).toEqual([added.id]);
  });
});
