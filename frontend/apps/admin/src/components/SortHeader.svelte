<script lang="ts">
  // A table header that sorts its list: click to sort, click again to turn.
  import type { SortState } from "../lib/listSort";

  let {
    key,
    label,
    sort,
    onsort,
    num = false,
    cls = "",
  }: {
    key: string;
    label: string;
    sort: SortState;
    onsort: (key: string) => void;
    num?: boolean;
    cls?: string;
  } = $props();

  const active = $derived(sort.key === key);
</script>

<th
  class={cls}
  class:num
  aria-sort={active ? (sort.dir === "asc" ? "ascending" : "descending") : "none"}
>
  <button type="button" class="sort" class:active onclick={() => onsort(key)}>
    {label}<span class="arrow" aria-hidden="true">{active ? (sort.dir === "asc" ? "▲" : "▼") : "↕"}</span>
  </button>
</th>

<style>
  .sort {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 0;
    min-height: 0;
    border: 0;
    background: none;
    color: inherit;
    font: inherit;
    text-transform: inherit;
    letter-spacing: inherit;
    cursor: pointer;
  }
  .sort:hover,
  .sort.active {
    color: var(--text);
  }
  .arrow {
    font-size: 0.75em;
    opacity: 0.35;
  }
  .active .arrow {
    opacity: 1;
    color: var(--accent);
  }
</style>
