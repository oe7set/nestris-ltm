// Short-lived notifications in the corner, optionally with one action
// ("Rückgängig"). Errors stay longer and are announced as alerts.

import { ApiError } from "./api";

export interface ToastAction {
  label: string;
  run: () => void | Promise<void>;
}

export interface Toast {
  id: number;
  kind: "ok" | "error";
  text: string;
  action?: ToastAction;
}

class Toasts {
  items = $state<Toast[]>([]);
  #next = 1;

  push(kind: Toast["kind"], text: string, ms = kind === "error" ? 7000 : 2500, action?: ToastAction): number {
    const id = this.#next++;
    this.items = [...this.items, { id, kind, text, action }];
    setTimeout(() => this.dismiss(id), ms);
    return id;
  }

  ok(text: string): void {
    this.push("ok", text);
  }

  /** A success message with an action (e.g. undo), shown long enough to use it. */
  withAction(text: string, action: ToastAction, ms = 8000): void {
    this.push("ok", text, ms, action);
  }

  error(err: unknown): void {
    this.push("error", errorText(err));
  }

  dismiss(id: number): void {
    this.items = this.items.filter((t) => t.id !== id);
  }
}

export function errorText(err: unknown): string {
  return err instanceof ApiError || err instanceof Error ? err.message : String(err);
}

export const toasts = new Toasts();
