import { describe, expect, it } from "vitest";
import { buildUrl, errorDetail } from "./api";

describe("buildUrl", () => {
  it("skips empty values", () => {
    expect(buildUrl("/api/games", { q: "", a: null, b: undefined, limit: 50, flag: false })).toBe(
      "/api/games?limit=50&flag=false",
    );
    expect(buildUrl("/api/x")).toBe("/api/x");
  });
});

describe("errorDetail", () => {
  it("handles string and validation details", () => {
    expect(errorDetail({ detail: "nope" }, "x")).toBe("nope");
    expect(
      errorDetail({ detail: [{ loc: ["body", "nickname"], msg: "too short" }] }, "x"),
    ).toBe("nickname: too short");
    expect(errorDetail("plain", "fallback")).toBe("fallback");
  });
});
