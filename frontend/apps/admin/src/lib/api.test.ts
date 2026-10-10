import { describe, expect, it } from "vitest";
import { ApiError, buildUrl, dbUnavailableState, errorDetail } from "./api";

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

describe("dbUnavailableState", () => {
  it("reads the state of a 503 database-unavailable answer", () => {
    const body = { detail: "database unavailable (auth_failed)", code: "db_unavailable", state: "auth_failed" };
    const error = new ApiError(503, body.detail, "db_unavailable", body);
    expect(dbUnavailableState(error)).toBe("auth_failed");
  });

  it("ignores other errors", () => {
    expect(dbUnavailableState(new ApiError(503, "mqtt offline", "mqtt_offline"))).toBeNull();
    expect(dbUnavailableState(new Error("x"))).toBeNull();
  });
});
