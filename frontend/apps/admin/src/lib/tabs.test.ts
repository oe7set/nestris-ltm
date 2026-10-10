import { describe, expect, it, vi } from "vitest";

vi.mock("./router.svelte", () => ({
  router: { current: { query: new URLSearchParams() }, setQuery: vi.fn() },
}));

const { tabFromQuery } = await import("./tabs");

describe("tabFromQuery", () => {
  const TABS = ["general", "display", "access"] as const;

  it("takes a known tab and falls back to the first", () => {
    expect(tabFromQuery(TABS, new URLSearchParams("tab=display"))).toBe("display");
    expect(tabFromQuery(TABS, new URLSearchParams("tab=bogus"))).toBe("general");
    expect(tabFromQuery(TABS, new URLSearchParams())).toBe("general");
  });
});
