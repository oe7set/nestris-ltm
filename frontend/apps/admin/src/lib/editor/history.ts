// Undo/redo for the layout builder: snapshots of the whole document (small:
// at most 300 elements). Successive edits with the same ``key`` within a
// short time (typing a number, nudging with the arrow keys) merge into one step.

export interface HistoryOptions {
  limit?: number;
  /** Edits with the same key closer together than this merge (ms). */
  mergeMs?: number;
  now?: () => number;
}

export class History<T> {
  #past: T[] = [];
  #future: T[] = [];
  #lastKey: string | null = null;
  #lastAt = 0;
  readonly #limit: number;
  readonly #mergeMs: number;
  readonly #now: () => number;

  constructor(options: HistoryOptions = {}) {
    this.#limit = options.limit ?? 200;
    this.#mergeMs = options.mergeMs ?? 800;
    this.#now = options.now ?? (() => Date.now());
  }

  /** Remember ``before`` (the state before an edit). */
  record(before: T, key: string | null = null): void {
    const now = this.#now();
    const merge = key !== null && key === this.#lastKey && now - this.#lastAt <= this.#mergeMs;
    this.#lastKey = key;
    this.#lastAt = now;
    this.#future = [];
    if (merge) return; // the step already holds the state before the first edit
    this.#past.push(before);
    if (this.#past.length > this.#limit) this.#past.shift();
  }

  /** The state to go back to (``current`` goes on the redo stack), or null. */
  undo(current: T): T | null {
    const previous = this.#past.pop();
    if (previous === undefined) return null;
    this.#future.push(current);
    this.#lastKey = null;
    return previous;
  }

  redo(current: T): T | null {
    const next = this.#future.pop();
    if (next === undefined) return null;
    this.#past.push(current);
    this.#lastKey = null;
    return next;
  }

  /** Stop merging into the last step (e.g. after a pointer gesture ended). */
  seal(): void {
    this.#lastKey = null;
  }

  clear(): void {
    this.#past = [];
    this.#future = [];
    this.#lastKey = null;
  }

  get canUndo(): boolean {
    return this.#past.length > 0;
  }

  get canRedo(): boolean {
    return this.#future.length > 0;
  }

  get size(): number {
    return this.#past.length;
  }
}
