// What needs attention (GET /api/attention): the bell in the menu, the
// dashboard card and a toast (optionally a sound) when a problem appears.
// Polled while signed in; paused while the tab is hidden.

import { api } from "./api";
import { format, tDynamic } from "./i18n.svelte";
import { toasts } from "./toast.svelte";
import { uiPrefs } from "./uiPrefs.svelte";

export interface AttentionItem {
  code: string;
  severity: "error" | "warn" | "info";
  count: number;
  link: string;
  names: string[];
}

const POLL_MS = 10_000;
// Worth an unprompted toast when they appear or grow.
const ANNOUNCE = new Set(["mqtt_down", "spool_failed", "stations_offline", "suspicious_games", "station_config_error"]);

export function attentionText(item: AttentionItem): string {
  return format(tDynamic(`attention.${item.code}`, item.code), {
    n: item.count,
    names: item.names.join(", "),
  });
}

/** Items that are new or grew since ``before`` (by code and count). */
export function newProblems(before: AttentionItem[] | null, now: AttentionItem[]): AttentionItem[] {
  if (before === null) return []; // first load: nothing is "new"
  const old = new Map(before.map((i) => [i.code, i.count]));
  return now.filter((i) => ANNOUNCE.has(i.code) && i.count > (old.get(i.code) ?? 0));
}

function beep(): void {
  try {
    const ctx = new AudioContext();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.frequency.value = 880;
    gain.gain.setValueAtTime(0.15, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.35);
    osc.connect(gain).connect(ctx.destination);
    osc.start();
    osc.stop(ctx.currentTime + 0.35);
    osc.onended = () => void ctx.close();
  } catch {
    // no audio (autoplay policy, no device): the toast is enough
  }
}

class Attention {
  items = $state<AttentionItem[]>([]);
  loaded = $state(false);
  #last: AttentionItem[] | null = null;
  #timer: ReturnType<typeof setInterval> | null = null;

  /** The number on the bell: problems, not hints. */
  get count(): number {
    return this.items.filter((i) => i.severity !== "info").length;
  }

  get worst(): AttentionItem["severity"] | null {
    if (this.items.some((i) => i.severity === "error")) return "error";
    if (this.items.some((i) => i.severity === "warn")) return "warn";
    return this.items.length ? "info" : null;
  }

  async refresh(): Promise<void> {
    try {
      const { items } = await api<{ items: AttentionItem[] }>("/api/attention");
      for (const item of newProblems(this.#last, items)) {
        toasts.push(item.severity === "error" ? "error" : "ok", attentionText(item), 9000);
        if (uiPrefs.alertSound) beep();
      }
      this.#last = items;
      this.items = items;
      this.loaded = true;
    } catch {
      // server or database down: the DB banner / problem screen says so
    }
  }

  start(): () => void {
    void this.refresh();
    this.#timer = setInterval(() => {
      if (document.visibilityState === "visible") void this.refresh();
    }, POLL_MS);
    const onVisible = () => {
      if (document.visibilityState === "visible") void this.refresh();
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      if (this.#timer) clearInterval(this.#timer);
      this.#timer = null;
      document.removeEventListener("visibilitychange", onVisible);
    };
  }
}

export const attention = new Attention();
