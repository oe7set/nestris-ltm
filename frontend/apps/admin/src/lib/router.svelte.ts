// Minimal hash router: "#/players/12?tab=games" -> { name, params, query }.
// Hash routing keeps the server simple: every admin URL is "/".

import { matchPath, type Match } from "./routes";

export type { Match } from "./routes";

class Router {
  current = $state<Match>(matchPath(location.hash));

  constructor() {
    window.addEventListener("hashchange", () => {
      this.current = matchPath(location.hash);
    });
  }

  go(path: string): void {
    location.hash = path.startsWith("#") ? path : `#${path}`;
  }

  /** Replace the query string of the current route (filters, paging). */
  setQuery(values: Record<string, string | number | boolean | null | undefined>): void {
    const raw = location.hash.replace(/^#/, "") || "/";
    const path = raw.split("?", 1)[0] ?? "/";
    const params = new URLSearchParams();
    for (const [key, value] of Object.entries(values)) {
      if (value !== undefined && value !== null && value !== "" && value !== false) {
        params.set(key, String(value));
      }
    }
    const qs = params.toString();
    history.replaceState(null, "", `#${path}${qs ? `?${qs}` : ""}`);
    this.current = matchPath(location.hash);
  }
}

export const router = new Router();
