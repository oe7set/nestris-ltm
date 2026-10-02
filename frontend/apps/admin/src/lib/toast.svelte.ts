// Short-lived notifications in the corner.

import { ApiError } from "./api";

export interface Toast {
  id: number;
  kind: "ok" | "error";
  text: string;
}

class Toasts {
  items = $state<Toast[]>([]);
  #next = 1;

  push(kind: Toast["kind"], text: string, ms = kind === "error" ? 7000 : 2500): void {
    const id = this.#next++;
    this.items = [...this.items, { id, kind, text }];
    setTimeout(() => this.dismiss(id), ms);
  }

  ok(text: string): void {
    this.push("ok", text);
  }

  error(err: unknown): void {
    const text = err instanceof ApiError || err instanceof Error ? err.message : String(err);
    this.push("error", text);
  }

  dismiss(id: number): void {
    this.items = this.items.filter((t) => t.id !== id);
  }
}

export const toasts = new Toasts();
