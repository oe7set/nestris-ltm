// Multi-select state of a paged list: keeps the selected rows across pages
// (the confirmation dialogs list them), cleared when the filters change.

export type PageState = "none" | "some" | "all";

export class Selection<T extends { id: number }> {
  /** Selected rows by id; replaced on every change so the UI updates. */
  items = $state<Map<number, T>>(new Map());

  readonly max: number;

  constructor(max = 500) {
    this.max = max;
  }

  get size(): number {
    return this.items.size;
  }

  get ids(): number[] {
    return [...this.items.keys()];
  }

  get rows(): T[] {
    return [...this.items.values()];
  }

  has(id: number): boolean {
    return this.items.has(id);
  }

  /** Adds or removes ``row``; false if the limit kept it out. */
  toggle(row: T): boolean {
    const next = new Map(this.items);
    if (next.has(row.id)) {
      next.delete(row.id);
    } else {
      if (next.size >= this.max) return false;
      next.set(row.id, row);
    }
    this.items = next;
    return true;
  }

  /** Selects (``on``) or deselects all ``rows``, up to the limit. */
  setMany(rows: T[], on: boolean): void {
    const next = new Map(this.items);
    for (const row of rows) {
      if (!on) next.delete(row.id);
      else if (next.size < this.max || next.has(row.id)) next.set(row.id, row);
    }
    this.items = next;
  }

  /** How many of the page's ``rows`` are selected. */
  pageState(rows: T[]): PageState {
    const selected = rows.filter((r) => this.items.has(r.id)).length;
    if (selected === 0) return "none";
    return selected === rows.length ? "all" : "some";
  }

  /** Drops ids that are gone (e.g. deleted). */
  forget(ids: number[]): void {
    const next = new Map(this.items);
    for (const id of ids) next.delete(id);
    this.items = next;
  }

  clear(): void {
    if (this.items.size) this.items = new Map();
  }
}
