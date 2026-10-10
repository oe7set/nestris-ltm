// The active tab of a page lives in its ?tab= query (shareable, survives reload).

import { router } from "./router.svelte";

/** The tab named in the query if it is one of ``tabs``, else the first. */
export function tabFromQuery<T extends string>(tabs: readonly T[], query: URLSearchParams = router.current.query): T {
  const wanted = query.get("tab");
  return tabs.includes(wanted as T) ? (wanted as T) : tabs[0]!;
}

/** Store ``tab`` in the query; the first (default) tab leaves it out. */
export function tabToQuery<T extends string>(tabs: readonly T[], tab: T): void {
  router.setQuery({ tab: tab === tabs[0] ? null : tab });
}
