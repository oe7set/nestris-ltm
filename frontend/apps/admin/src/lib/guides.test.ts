import { describe, expect, it } from "vitest";
import { guides, MAX_GUIDES } from "./guides.svelte";

describe("guides", () => {
  it("snap only while shown, with thirds/safe lines on request", () => {
    guides.visible = false;
    guides.setCustom([{ axis: "x", at: 100 }]);
    expect(guides.snapLines()).toEqual([]);
    guides.visible = true;
    guides.thirds = false;
    guides.safe = false;
    expect(guides.snapLines()).toEqual([{ axis: "x", at: 100 }]);
    guides.thirds = true;
    expect(guides.snapLines()).toContainEqual({ axis: "y", at: 720 });
  });

  it("drops invalid lines and keeps at most the limit", () => {
    guides.setCustom([
      { axis: "x", at: -5 },
      { axis: "y", at: 2000 },
      { axis: "z" as "x", at: 5 },
      ...Array.from({ length: 60 }, (_, i) => ({ axis: "y" as const, at: i })),
    ]);
    expect(guides.custom).toHaveLength(MAX_GUIDES);
    expect(guides.custom.every((g) => g.axis === "y")).toBe(true);
  });
});
