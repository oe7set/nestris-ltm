// Own overlay layouts from the layout builder: mirrors core/overlay_layout.py
// (the server validates; these types only describe what it sends).

export const CANVAS_W = 1920;
export const CANVAS_H = 1080;

export type Align = "left" | "center" | "right";
export type StatField =
  | "score" | "lines" | "level" | "start_level" | "trt" | "drought" | "burn" | "pace" | "gap" | "pieces";

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

export const CUSTOM_PREFIX = "custom:";

export function customId(layout: string): string | null {
  return layout.startsWith(CUSTOM_PREFIX) ? layout.slice(CUSTOM_PREFIX.length) : null;
}

/** Elements in paint order (z, then definition order); hidden ones only when asked. */
export function paintOrder(def: LayoutDefinition, withHidden = false): LayoutElement[] {
  return def.elements
    .map((e, i) => ({ e, i }))
    .filter(({ e }) => withHidden || !e.hidden)
    .sort((a, b) => (a.e.z ?? 0) - (b.e.z ?? 0) || a.i - b.i)
    .map(({ e }) => e);
}
