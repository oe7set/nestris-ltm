// Previous / next game on the game page, in the order of the games list the
// operator came from (its filters and page). Kept per browser tab.

const KEY = "nltm.games.nav";

export interface GameNav {
  ids: number[];
  /** The list's address, for the way back. */
  back: string;
}

export function saveGameNav(nav: GameNav): void {
  try {
    sessionStorage.setItem(KEY, JSON.stringify(nav));
  } catch {
    // storage blocked: no previous/next
  }
}

export function neighbours(id: number): { prev: number | null; next: number | null; back: string | null } {
  try {
    const nav = JSON.parse(sessionStorage.getItem(KEY) ?? "null") as GameNav | null;
    const index = nav?.ids.indexOf(id) ?? -1;
    if (!nav || index < 0) return { prev: null, next: null, back: null };
    return {
      prev: nav.ids[index - 1] ?? null,
      next: nav.ids[index + 1] ?? null,
      back: nav.back,
    };
  } catch {
    return { prev: null, next: null, back: null };
  }
}
