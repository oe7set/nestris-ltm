// Definitions of own layouts (GET /api/overlay-layouts/<id>, public), cached
// per revision: the scene state only carries "<uuid>:<version>".

import type { LayoutDefinition } from "./layoutdef";

const RETRY_MS = 5000;

class Definitions {
  byId = $state<Record<string, LayoutDefinition>>({});
  failed = $state<Record<string, string>>({});
  #loaded: Record<string, string> = {}; // id -> revision fetched (or in flight)

  /** Make sure the definition of ``id`` at ``rev`` is (being) loaded. */
  ensure(id: string, rev: string | null | undefined): void {
    const key = rev ?? "0";
    if (this.#loaded[id] === key) return;
    this.#loaded[id] = key;
    void this.#fetch(id, key);
  }

  async #fetch(id: string, rev: string): Promise<void> {
    try {
      const response = await fetch(`/api/overlay-layouts/${encodeURIComponent(id)}`, { cache: "no-store" });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = (await response.json()) as { definition: LayoutDefinition };
      if (this.#loaded[id] !== rev) return; // a newer revision is on its way
      this.byId[id] = data.definition;
      delete this.failed[id];
    } catch (err) {
      this.failed[id] = err instanceof Error ? err.message : String(err);
      setTimeout(() => {
        if (this.#loaded[id] === rev) {
          delete this.#loaded[id];
          this.ensure(id, rev);
        }
      }, RETRY_MS);
    }
  }
}

export const definitions = new Definitions();
