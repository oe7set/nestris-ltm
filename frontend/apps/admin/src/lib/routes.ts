// Route table and hash parsing (pure, unit-tested in routes.test.ts).

export interface RouteDef {
  name: string;
  pattern: string; // e.g. "/players/:id"
}

export interface Match {
  name: string;
  params: Record<string, string>;
  query: URLSearchParams;
}

export const routes: RouteDef[] = [
  { name: "dashboard", pattern: "/" },
  { name: "players", pattern: "/players" },
  { name: "player", pattern: "/players/:id" },
  { name: "games", pattern: "/games" },
  { name: "game-new", pattern: "/games/new" },
  { name: "game", pattern: "/games/:id" },
  { name: "events", pattern: "/events" },
  { name: "tournament", pattern: "/tournament" },
  { name: "matches", pattern: "/matches" },
  { name: "scenes", pattern: "/scenes" },
  { name: "studio", pattern: "/studio" },
  { name: "studio-scene", pattern: "/studio/scene/:id" },
  { name: "studio-layout", pattern: "/studio/layout/:id" },
  { name: "stations", pattern: "/stations" },
  { name: "audit", pattern: "/audit" },
  { name: "settings", pattern: "/settings" },
  { name: "updates", pattern: "/updates" },
  { name: "devices", pattern: "/devices" },
  { name: "pages", pattern: "/pages" },
];

export function matchPath(hash: string, defs: RouteDef[] = routes): Match {
  const raw = hash.replace(/^#/, "") || "/";
  const [pathPart, queryPart = ""] = raw.split("?", 2);
  const path = (pathPart ?? "/").replace(/\/+$/, "") || "/";
  const query = new URLSearchParams(queryPart);
  const segments = path.split("/").filter(Boolean);
  for (const def of defs) {
    const pattern = def.pattern.split("/").filter(Boolean);
    if (pattern.length !== segments.length) continue;
    const params: Record<string, string> = {};
    const ok = pattern.every((part, i) => {
      const seg = decodeURIComponent(segments[i] ?? "");
      if (part.startsWith(":")) {
        params[part.slice(1)] = seg;
        return true;
      }
      return part === seg;
    });
    if (ok) return { name: def.name, params, query };
  }
  return { name: "not-found", params: {}, query };
}
