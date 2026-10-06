import { describe, expect, it } from "vitest";
import { demoData, demoPlayfield, demoScore, rng } from "./demo";
import { boardCell, fitFont, heartPixel } from "./fit";
import { host, overlayMode } from "./host.svelte";
import { customId, paintOrder, type LayoutDefinition } from "./layoutdef";
import { hiddenBlocks, stageStyle } from "./theme";
import type { SceneInfo } from "./types";

const scene: SceneInfo = {
  slug: "demo",
  name: "Demo",
  layout: "2x1v1_cam",
  mode: "none",
  auto_round: false,
  settings: { style: "nes", lang: "de" },
  pairs: [
    [0, 1],
    [2, 3],
  ],
};

describe("demo data", () => {
  it("is deterministic and fills every slot", () => {
    const a = demoData({ scene, slots: 4 }, 42_000);
    const b = demoData({ scene, slots: 4 }, 42_000);
    expect(a).toEqual(b);
    expect(a.state.slots).toHaveLength(4);
    expect(Object.keys(a.frames)).toHaveLength(4);
    for (const s of a.state.slots) {
      expect(s.status).toBe("playing");
      expect(s.lives).toEqual({ current: s.slot % 2 ? 1 : 2, max: 2 });
      expect(s.vs_partner).toBeDefined();
    }
    expect(a.state.groups?.map((g) => g.slots)).toEqual([[0, 1], [2, 3]]);
    expect(a.state.matches).toHaveLength(2);
  });

  it("scores grow within a loop, playfields are 20 rows of 10 cells", () => {
    expect(demoScore(0, 10_000)).toBeLessThan(demoScore(0, 20_000));
    const rows = demoPlayfield(1, 5000);
    expect(rows).toHaveLength(20);
    expect(rows.every((r) => /^[0-3]{10}$/.test(r))).toBe(true);
    expect(rows[0]).toBe("0000000000"); // the top stays free
    expect(rng(7)()).toBe(rng(7)());
  });

  it("uses given names and a single group without pairs", () => {
    const d = demoData({ scene: { ...scene, pairs: [] }, slots: 3, names: ["Anna", null, "Bert"] }, 1000);
    expect(d.state.slots.map((s) => s.name)).toEqual(["Anna", "Tom", "Bert"]);
    expect(d.state.groups).toEqual([{ group: 0, slots: [0, 1, 2], round: 1, complete: false }]);
    expect(d.state.slots.every((s) => s.lives === undefined)).toBe(true);
  });
});

describe("host", () => {
  it("knows the modes", () => {
    const p = (q: string) => new URLSearchParams(q);
    expect(overlayMode("buehne", p(""))).toBe("live");
    expect(overlayMode("buehne", p("demo=1"))).toBe("demo");
    expect(overlayMode("_preview", p(""))).toBe("preview");
    expect(overlayMode("_edit", p("demo=1"))).toBe("edit");
  });

  it("accepts messages only from its parent on the same origin", () => {
    const parent = {};
    const self = {};
    const ok = { origin: "http://host:7990", source: parent } as unknown as MessageEvent;
    expect(host.accepts(ok, "http://host:7990", parent)).toBe(true);
    expect(host.accepts({ ...ok, origin: "http://evil" } as MessageEvent, "http://host:7990", parent)).toBe(false);
    expect(host.accepts({ ...ok, source: self } as unknown as MessageEvent, "http://host:7990", parent)).toBe(false);
  });

  it("ignores malformed messages", () => {
    host.handle(null);
    host.handle({ type: "edit-select", ids: ["a", 3, "b"] });
    expect(host.selected).toEqual(["a", "b"]);
    host.handle({ type: "preview-config" });
    expect(host.config).toBeNull();
  });
});

describe("theme and sizes", () => {
  it("passes only #rrggbb colours", () => {
    expect(stageStyle({ accent: "#ff0000", good: "#00ff00", bad: "red; background: url(x)" })).toBe(
      "--accent: #ff0000; --good: #00ff00; --side-a: #00ff00",
    );
    expect(hiddenBlocks({ header: false, pace: true, next: false })).toBe("header next");
  });

  it("fits fonts, boards and hearts into their box", () => {
    expect(fitFont(6, 200, 100, 0.5, true) % 8).toBe(0);
    expect(fitFont(20, 100, 100, 0.5, true)).toBe(8); // long text, small box: the minimum
    expect(fitFont(3, 300, 100, 0.5, false)).toBe(50);
    const cell = boardCell(360, 760);
    expect(cell * 10.5 + 8).toBeLessThanOrEqual(360);
    expect(cell * 20.5 + 8).toBeLessThanOrEqual(760);
    expect(heartPixel(2, 200, 40)).toBe(4);
  });
});

describe("layout definitions", () => {
  it("paints by z, keeps hidden ones for the builder", () => {
    const def: LayoutDefinition = {
      schema: 1,
      slots: 1,
      pairs: [],
      elements: [
        { id: "a", type: "frame", x: 0, y: 0, w: 10, h: 10, z: 2 },
        { id: "b", type: "frame", x: 0, y: 0, w: 10, h: 10, hidden: true },
        { id: "c", type: "frame", x: 0, y: 0, w: 10, h: 10 },
      ],
    };
    expect(paintOrder(def).map((e) => e.id)).toEqual(["c", "a"]);
    expect(paintOrder(def, true).map((e) => e.id)).toEqual(["b", "c", "a"]);
    expect(customId("custom:abc")).toBe("abc");
    expect(customId("1v1")).toBeNull();
  });
});
