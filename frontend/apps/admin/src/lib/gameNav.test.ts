import { afterEach, describe, expect, it, vi } from "vitest";
import { neighbours, saveGameNav } from "./gameNav";

function memoryStorage() {
  const data = new Map<string, string>();
  return { getItem: (k: string) => data.get(k) ?? null, setItem: (k: string, v: string) => void data.set(k, v) };
}

describe("game navigation", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("finds the neighbours in the saved list", () => {
    vi.stubGlobal("sessionStorage", memoryStorage());
    saveGameNav({ ids: [9, 7, 5], back: "#/games?q=x" });
    expect(neighbours(7)).toEqual({ prev: 9, next: 5, back: "#/games?q=x" });
    expect(neighbours(9).prev).toBeNull();
    expect(neighbours(42)).toEqual({ prev: null, next: null, back: null });
  });

  it("works without storage", () => {
    vi.stubGlobal("sessionStorage", {
      getItem: () => {
        throw new Error("blocked");
      },
      setItem: () => {
        throw new Error("blocked");
      },
    });
    saveGameNav({ ids: [1], back: "#/games" });
    expect(neighbours(1).back).toBeNull();
  });
});
