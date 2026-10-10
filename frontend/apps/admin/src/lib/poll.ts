// Polling for pages that refresh themselves: the next round starts when the
// previous one finished (no overlapping requests), nothing runs while the
// browser tab is hidden, and showing the tab again refreshes at once.

import { toasts } from "./toast.svelte";

/** Run ``fn`` every ``ms`` (or a delay computed each time); returns stop(). */
export function poll(fn: () => unknown, ms: number | (() => number)): () => void {
  let timer: ReturnType<typeof setTimeout> | undefined;
  let stopped = false;
  let running = false;

  const delay = () => (typeof ms === "function" ? ms() : ms);

  async function tick(): Promise<void> {
    if (stopped || running) return;
    if (typeof document !== "undefined" && document.visibilityState === "hidden") {
      schedule();
      return;
    }
    running = true;
    try {
      await fn();
    } catch {
      // the page reports its own errors
    } finally {
      running = false;
      schedule();
    }
  }

  function schedule(): void {
    clearTimeout(timer);
    if (!stopped) timer = setTimeout(() => void tick(), delay());
  }

  const onVisible = (): void => {
    if (document.visibilityState === "visible") void tick();
  };
  if (typeof document !== "undefined") document.addEventListener("visibilitychange", onVisible);
  schedule();

  return () => {
    stopped = true;
    clearTimeout(timer);
    if (typeof document !== "undefined") document.removeEventListener("visibilitychange", onVisible);
  };
}

/**
 * Error reporting for polled requests: the first failure shows a toast, the
 * same outage does not repeat it every few seconds; a success re-arms it.
 */
export class ErrorOnce {
  #shown = false;

  report(err: unknown): void {
    if (this.#shown) return;
    this.#shown = true;
    toasts.error(err);
  }

  ok(): void {
    this.#shown = false;
  }
}
