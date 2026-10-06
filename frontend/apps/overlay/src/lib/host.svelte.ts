// How the overlay page runs, and its message channel to the admin studio.
//
//   /o/<slug>            live (OBS)
//   /o/<slug>?demo=1     the saved scene with demo data (thumbnails)
//   /o/_preview          unsaved settings from the studio editor (demo or live data)
//   /o/_edit             layout builder canvas (demo data)
//
// Messages are accepted only from the parent window on the same origin.

import type { LayoutDefinition } from "./layoutdef";
import type { SceneInfo } from "./types";

export type Mode = "live" | "demo" | "preview" | "edit";

export function overlayMode(slug: string | null, params: URLSearchParams): Mode {
  if (slug === "_preview") return "preview";
  if (slug === "_edit") return "edit";
  return params.get("demo") === "1" ? "demo" : "live";
}

/** What the studio sends: the scene as edited, possibly unsaved. */
export interface PreviewConfig {
  scene: SceneInfo;
  /** Slot count of the chosen layout. */
  slots: number;
  /** Names for the demo players (slot name overrides). */
  names?: (string | null)[];
  /** Own layout being edited (builder) or chosen (editor); built-in layouts: null. */
  definition?: LayoutDefinition | null;
  /** Live data of a saved scene instead of demo data (editor "Live" switch). */
  liveSlug?: string | null;
}

export type ToOverlay =
  | { type: "preview-config"; config: PreviewConfig }
  | { type: "edit-select"; ids: string[] };

export type FromOverlay = { type: "ready"; mode: Mode } | { type: "error"; message: string };

class Host {
  config = $state<PreviewConfig | null>(null);
  selected = $state<string[]>([]);
  #listening = false;

  /** Is this message really from our studio (parent window, same origin)? */
  accepts(
    event: Pick<MessageEvent, "origin" | "source">,
    origin: string = globalThis.location?.origin ?? "",
    parent: unknown = globalThis.window?.parent,
    self: unknown = globalThis.window,
  ): boolean {
    // Not from ourselves: a page opened directly (no parent) is its own parent.
    return event.origin === origin && event.source === parent && parent !== self;
  }

  handle(data: unknown): void {
    if (!data || typeof data !== "object") return;
    const msg = data as Partial<ToOverlay>;
    if (msg.type === "preview-config" && msg.config && typeof msg.config === "object") {
      this.config = msg.config;
    } else if (msg.type === "edit-select" && Array.isArray(msg.ids)) {
      this.selected = msg.ids.filter((id): id is string => typeof id === "string");
    }
  }

  listen(mode: Mode): void {
    if (this.#listening || window.parent === window) return;
    this.#listening = true;
    addEventListener("message", (event) => {
      if (this.accepts(event)) this.handle(event.data);
    });
    this.post({ type: "ready", mode });
  }

  post(msg: FromOverlay): void {
    if (window.parent !== window) window.parent.postMessage(msg, location.origin);
  }
}

export const host = new Host();
