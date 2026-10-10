import { afterEach, describe, expect, it, vi } from "vitest";
import { UiPrefs } from "./uiPrefs.svelte";

function memoryStorage(initial: Record<string, string> = {}) {
  const data = new Map(Object.entries(initial));
  return {
    getItem: (k: string) => data.get(k) ?? null,
    setItem: (k: string, v: string) => void data.set(k, v),
    data,
  };
}

describe("UiPrefs", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("defaults without storage and survives a blocked one", () => {
    vi.stubGlobal("localStorage", {
      getItem: () => {
        throw new Error("blocked");
      },
      setItem: () => {
        throw new Error("blocked");
      },
    });
    const prefs = new UiPrefs();
    expect(prefs.tournamentHelp).toBe(false);
    expect(prefs.tournamentFocus).toBe(false);
    prefs.toggle("tournamentFocus"); // must not throw
    expect(prefs.tournamentFocus).toBe(true);
  });

  it("stores and reloads the choices", () => {
    const storage = memoryStorage();
    vi.stubGlobal("localStorage", storage);
    const prefs = new UiPrefs();
    prefs.toggle("tournamentHelp");
    expect(new UiPrefs().tournamentHelp).toBe(true);
    expect(new UiPrefs().tournamentFocus).toBe(false);
  });

  it("ignores garbage", () => {
    vi.stubGlobal("localStorage", memoryStorage({ "nltm.ui": "{not json" }));
    expect(new UiPrefs().tournamentHelp).toBe(false);
    vi.stubGlobal("localStorage", memoryStorage({ "nltm.ui": '{"tournamentHelp":"yes"}' }));
    expect(new UiPrefs().tournamentHelp).toBe(false);
  });
});
