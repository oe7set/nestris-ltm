// Minimal hash router: "#/players/12?tab=games" -> { name, params, query }.
// Hash routing keeps the server simple: every admin URL is "/".

import { matchPath, redirectFor, type Match } from "./routes";

/** Follow an old address (e.g. #/scenes) without a history entry. */
function resolve(): Match {
  const target = redirectFor(location.hash);
  if (target) history.replaceState(null, "", target);
  return matchPath(location.hash);
}

export type { Match } from "./routes";

class Router {
  current = $state<Match>(resolve());
  // A page with unsaved changes may veto leaving it (e.g. the scene editor).
  // The answer may come later (an in-app question): the address is put back
  // at once and followed when the guard says yes.
  #guard: ((to: Match) => boolean | Promise<boolean>) | null = null;
  #passing = false;

  constructor() {
    window.addEventListener("hashchange", (event) => {
      const next = resolve();
      const answer = this.#guard && !this.#passing ? this.#guard(next) : true;
      if (answer !== true) {
        const target = location.hash;
        // Stay for now: restore the old address without a new hashchange event.
        history.replaceState(null, "", new URL(event.oldURL).hash || "#/");
        if (answer === false) return;
        void answer.then((ok) => {
          if (!ok) return;
          this.#passing = true;
          history.replaceState(null, "", target);
          this.current = resolve();
          this.#passing = false;
        });
        return;
      }
      this.current = next;
    });
  }

  /** Ask before leaving the current page; returns the function that removes the guard. */
  setGuard(guard: (to: Match) => boolean | Promise<boolean>): () => void {
    this.#guard = guard;
    return () => {
      if (this.#guard === guard) this.#guard = null;
    };
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
