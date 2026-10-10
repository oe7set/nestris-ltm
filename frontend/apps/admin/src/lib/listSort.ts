// Sorting of the admin lists (games, players): which way a column sorts.

export type SortDir = "asc" | "desc";

export interface SortState {
  key: string;
  dir: SortDir;
}

/** Text columns (names) start A-Z, numbers and times high / new first. */
export function defaultDir(key: string, textKeys: readonly string[]): SortDir {
  return textKeys.includes(key) ? "asc" : "desc";
}

/** Clicking a column: the same column turns the direction, another starts in its default. */
export function nextSort(current: SortState, key: string, textKeys: readonly string[]): SortState {
  if (current.key === key) return { key, dir: current.dir === "asc" ? "desc" : "asc" };
  return { key, dir: defaultDir(key, textKeys) };
}

/** The sort from the URL (unknown keys fall back to the default). */
export function readSort(
  query: URLSearchParams,
  keys: readonly string[],
  fallback: string,
  textKeys: readonly string[],
): SortState {
  const raw = query.get("sort") ?? fallback;
  const key = keys.includes(raw) ? raw : fallback;
  const dir = query.get("dir");
  return { key, dir: dir === "asc" || dir === "desc" ? dir : defaultDir(key, textKeys) };
}

/** URL values: only what differs from the default, so plain links stay short. */
export function sortParams(
  state: SortState,
  fallback: string,
  textKeys: readonly string[],
): { sort: string | null; dir: SortDir | null } {
  return {
    sort: state.key === fallback ? null : state.key,
    dir: state.dir === defaultDir(state.key, textKeys) ? null : state.dir,
  };
}
