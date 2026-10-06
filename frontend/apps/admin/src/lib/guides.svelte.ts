// Guide lines of the scene studio (scene editor and layout builder): drawn
// over the preview only, never part of a scene or layout, so OBS never shows
// them. Kept per browser (localStorage) and shared by both editors.

import type { Guide } from "./editor/geometry";

export const MAX_GUIDES = 40;
const KEY = "nltm.studio-guides";

interface Stored {
  visible: boolean;
  center: boolean;
  thirds: boolean;
  safe: boolean;
  custom: Guide[];
}

function valid(g: unknown): g is Guide {
  if (!g || typeof g !== "object") return false;
  const { axis, at } = g as Guide;
  return (axis === "x" || axis === "y") && Number.isFinite(at) && at >= 0 && at <= (axis === "x" ? 1920 : 1080);
}

class Guides {
  visible = $state(false);
  center = $state(true);
  thirds = $state(false);
  safe = $state(false);
  custom = $state.raw<Guide[]>([]);

  constructor() {
    try {
      const raw = globalThis.localStorage?.getItem(KEY);
      if (!raw) return;
      const s = JSON.parse(raw) as Partial<Stored>;
      this.visible = s.visible === true;
      this.center = s.center !== false;
      this.thirds = s.thirds === true;
      this.safe = s.safe === true;
      this.custom = Array.isArray(s.custom) ? s.custom.filter(valid).slice(0, MAX_GUIDES) : [];
    } catch {
      // no stored guides: defaults
    }
  }

  save(): void {
    try {
      const data: Stored = {
        visible: this.visible,
        center: this.center,
        thirds: this.thirds,
        safe: this.safe,
        custom: this.custom,
      };
      globalThis.localStorage?.setItem(KEY, JSON.stringify(data));
    } catch {
      // storage blocked: guides last for this visit only
    }
  }

  toggle(key: "visible" | "center" | "thirds" | "safe"): void {
    this[key] = !this[key];
    this.save();
  }

  setCustom(list: Guide[]): void {
    this.custom = list.filter(valid).slice(0, MAX_GUIDES);
    this.save();
  }

  /** Lines elements snap to in the layout builder (only while shown). */
  snapLines(): Guide[] {
    if (!this.visible) return [];
    const out: Guide[] = [...this.custom];
    if (this.thirds) out.push({ axis: "x", at: 640 }, { axis: "x", at: 1280 }, { axis: "y", at: 360 }, { axis: "y", at: 720 });
    if (this.safe) {
      out.push({ axis: "x", at: 96 }, { axis: "x", at: 1824 }, { axis: "y", at: 54 }, { axis: "y", at: 1026 });
      out.push({ axis: "x", at: 192 }, { axis: "x", at: 1728 }, { axis: "y", at: 108 }, { axis: "y", at: 972 });
    }
    return out;
  }
}

export const guides = new Guides();
