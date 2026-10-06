// Scene studio: shared types and helpers (gallery, scene editor, builder).

import { ApiError, buildUrl } from "./api";

export type Style = "nes" | "modern";
export const THEME_KEYS = ["accent", "frame", "inner", "panel", "text", "good", "bad"] as const;
export type ThemeKey = (typeof THEME_KEYS)[number];
export const SHOW_KEYS = ["header", "diff_graph", "versus", "pace", "burn", "hearts", "next"] as const;
export type ShowKey = (typeof SHOW_KEYS)[number];
export const MODES = ["none", "top2_advance", "worst_out", "winner_only"] as const;

/** Defaults of the NES theme (nes.css), shown in the colour pickers. */
export const THEME_DEFAULTS: Record<ThemeKey, string> = {
  accent: "#f8b800",
  frame: "#fcfcfc",
  inner: "#3cbcfc",
  panel: "#000000",
  text: "#fcfcfc",
  good: "#58d854",
  bad: "#f83800",
};

export interface SceneSettings {
  style: Style;
  lang: "de" | "en";
  background: "transparent" | "dark";
  camera_frames: boolean;
  title?: string | null;
  theme: Partial<Record<ThemeKey, string>>;
  show: Record<ShowKey, boolean>;
  replay?: unknown;
}

export interface SlotRow {
  slot: number;
  station_id: string | null;
  label_override: string | null;
  name_override: string | null;
}

export interface SceneRow {
  id: number;
  slug: string;
  name: string;
  layout: string;
  mode: string;
  auto_round: boolean;
  settings: SceneSettings;
  slots: SlotRow[];
  round: number | null;
  rounds?: number[];
  clients: number;
  updated_at: string;
}

/** An entry of GET /api/scenes/layouts (built-in or own). */
export interface LayoutInfo {
  id: string;
  slots: number;
  title_de: string;
  title_en: string;
  description_de: string;
  description_en: string;
  pairs: [number, number][];
  supports_modes: boolean;
  custom: boolean;
}

export interface CustomLayout {
  id: string;
  key: string;
  name: string;
  description: string;
  version: number;
  slots: number | null;
  pairs: [number, number][];
  valid: boolean;
  updated_at: string | null;
  used_by?: string[];
  definition?: LayoutDefinition;
}

export type ElementType =
  | "board" | "next" | "stat" | "name" | "hearts" | "nametag" | "camera"
  | "versus" | "diff_graph" | "title" | "round" | "text" | "frame";

export interface LayoutElement {
  id: string;
  type: ElementType;
  slot?: number | null;
  pair?: number | null;
  x: number;
  y: number;
  w: number;
  h: number;
  z?: number;
  hidden?: boolean;
  locked?: boolean;
  props?: Record<string, unknown>;
}

export interface LayoutDefinition {
  schema: 1;
  canvas?: { w: number; h: number };
  slots: number;
  pairs: [number, number][];
  elements: LayoutElement[];
}

/** What the overlay preview iframe needs (overlay lib/host.svelte.ts). */
export interface PreviewConfig {
  scene: {
    slug: string;
    name: string;
    layout: string;
    mode: string;
    auto_round: boolean;
    settings: Partial<SceneSettings>;
    pairs: [number, number][];
  };
  slots: number;
  names?: (string | null)[];
  definition?: LayoutDefinition | null;
  liveSlug?: string | null;
}

export function defaultSettings(): SceneSettings {
  return {
    style: "nes",
    lang: "de",
    background: "transparent",
    camera_frames: false,
    title: null,
    theme: {},
    show: { header: true, diff_graph: true, versus: true, pace: true, burn: true, hearts: true, next: true },
  };
}

/** Settings as the server stores them (no empty title, no replay). */
export function cleanSettings(s: SceneSettings): Omit<SceneSettings, "replay"> {
  const { replay: _replay, ...rest } = s;
  const title = (rest.title ?? "").trim();
  const theme: Partial<Record<ThemeKey, string>> = {};
  for (const k of THEME_KEYS) {
    const v = rest.theme[k];
    if (v && /^#[0-9a-fA-F]{6}$/.test(v)) theme[k] = v;
  }
  return { ...rest, title: title || null, theme };
}

export function previewOf(
  scene: { slug: string; name: string; layout: string; mode: string; auto_round: boolean; settings: SceneSettings },
  layout: { slots: number; pairs: [number, number][] } | undefined,
  extra: Partial<PreviewConfig> = {},
): PreviewConfig {
  return {
    scene: {
      slug: scene.slug || "preview",
      name: scene.name || "Preview",
      layout: scene.layout,
      mode: scene.mode,
      auto_round: scene.auto_round,
      settings: cleanSettings(scene.settings),
      pairs: layout?.pairs ?? [],
    },
    slots: layout?.slots ?? 2,
    ...extra,
  };
}

/** Slug from a name: lowercase, digits, dashes. */
export function slugify(name: string): string {
  return (
    name
      .toLowerCase()
      .replace(/ä/g, "ae")
      .replace(/ö/g, "oe")
      .replace(/ü/g, "ue")
      .replace(/ß/g, "ss")
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "")
      .slice(0, 64) || "szene"
  );
}

/** Download an export from the server as a file (cookie session). */
export async function downloadExport(query: Record<string, string>): Promise<void> {
  const response = await fetch(buildUrl("/api/studio/export", query), { credentials: "same-origin" });
  if (!response.ok) throw new ApiError(response.status, `export failed (${response.status})`);
  const blob = await response.blob();
  const disposition = response.headers.get("content-disposition") ?? "";
  const name = /filename="([^"]+)"/.exec(disposition)?.[1] ?? "nestrisltm.nltm-scenes.json";
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export const MAX_IMPORT_BYTES = 1024 * 1024;

/** Read an import file (size checked before reading, JSON parsed). */
export async function readImportFile(file: File): Promise<unknown> {
  if (file.size > MAX_IMPORT_BYTES) throw new Error("file larger than 1 MB");
  const text = await file.text();
  try {
    return JSON.parse(text) as unknown;
  } catch {
    throw new Error("not a JSON file");
  }
}
