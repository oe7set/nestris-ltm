import { describe, expect, it } from "vitest";
import { matchPath } from "./routes";

describe("matchPath", () => {
  it("matches static and parameter routes", () => {
    expect(matchPath("").name).toBe("dashboard");
    expect(matchPath("#/").name).toBe("dashboard");
    expect(matchPath("#/players").name).toBe("players");
    const m = matchPath("#/players/42");
    expect(m.name).toBe("player");
    expect(m.params.id).toBe("42");
  });

  it("prefers the static route over a parameter", () => {
    expect(matchPath("#/games/new").name).toBe("game-new");
    expect(matchPath("#/games/7").name).toBe("game");
  });

  it("parses the query string and ignores trailing slashes", () => {
    const m = matchPath("#/games/?flagged=true&q=Erv");
    expect(m.name).toBe("games");
    expect(m.query.get("flagged")).toBe("true");
    expect(m.query.get("q")).toBe("Erv");
  });

  it("reports unknown paths", () => {
    expect(matchPath("#/nope/1/2").name).toBe("not-found");
  });
});
