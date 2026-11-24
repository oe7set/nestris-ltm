// The editing state of one layout on the 1920x1080 stage: the definition,
// the selection and undo/redo. Shared by the scene editor and the layout
// editor; the stage, layers and properties panels all work on one instance.
// The definition is immutable (every edit is a new object), which keeps
// undo/redo simple and the preview iframe messages plain data.

import { boardCell, boardSize } from "@nestris-ltm/nes";
import { confirmAsync } from "../confirm.svelte";
import { t } from "../i18n.svelte";
import type { ElementType, LayoutDefinition, LayoutElement } from "../studio";
import { toasts } from "../toast.svelte";
import {
  addElements,
  cloneElements,
  emptyDefinition,
  localProblems,
  MAX_ELEMENTS,
  newElement,
  placeable,
  removeElements,
  restack,
  setPairs,
  setSlots,
  unpairedSlots,
  updateElement,
} from "./elements";
import { align as alignRects, bounds, clamp, clampMove, distribute, type AlignMode, type Rect } from "./geometry";
import { History } from "./history";
import { mirrorSlot } from "./mirror";

// Copy/paste works across layouts while the admin page stays open.
let clipboard: LayoutElement[] = [];

/** dataTransfer type of an element dragged from the palette onto the stage. */
export const DRAG_TYPE = "application/x-nltm-element";

export const SLOT_COLORS = ["#f8b800", "#3cbcfc", "#58d854", "#f83800", "#b46cff", "#ff7eb6", "#00e0c0", "#e0e0e0"];

export function rectOf(e: LayoutElement): Rect {
  return { x: e.x, y: e.y, w: e.w, h: e.h };
}

export function slotColor(e: LayoutElement): string {
  if (e.slot !== undefined && e.slot !== null) return SLOT_COLORS[e.slot % SLOT_COLORS.length]!;
  return "#ffffff";
}

export class LayoutEditor {
  def = $state.raw<LayoutDefinition>(emptyDefinition());
  selected = $state<string[]>([]);
  /** Elements the server rejected on the last save. */
  errorIds = $state<string[]>([]);
  /** Slot new elements are added to. */
  addSlot = $state(0);
  /** False: a built-in layout is shown, nothing can be changed. */
  editable = $state(true);
  #history = new History<LayoutDefinition>();
  #rev = $state(0);

  readonly ordered = $derived(
    this.def.elements
      .map((e, i) => ({ e, i }))
      .sort((a, b) => (a.e.z ?? 0) - (b.e.z ?? 0) || a.i - b.i)
      .map(({ e }) => e),
  );
  readonly sel = $derived(this.def.elements.filter((e) => this.selected.includes(e.id)));
  readonly one = $derived(this.sel.length === 1 ? this.sel[0]! : null);
  readonly problems = $derived(localProblems(this.def));
  readonly slotNumbers = $derived(Array.from({ length: this.def.slots }, (_, i) => i));
  readonly canUndo = $derived(this.#rev >= 0 && this.#history.canUndo);
  readonly canRedo = $derived(this.#rev >= 0 && this.#history.canRedo);

  /** Start over with a definition (load, save, reset): no undo across it. */
  load(definition: LayoutDefinition): void {
    this.def = definition;
    this.#history.clear();
    this.#rev++;
    this.prune();
    this.addSlot = Math.min(this.addSlot, Math.max(0, definition.slots - 1));
  }

  // ---- history

  /** Every edit goes through here: one undo step each (``key`` merges steps). */
  apply(next: LayoutDefinition, key: string | null = null): void {
    if (next === this.def || !this.editable) return;
    this.#history.record(this.def, key);
    this.def = next;
    this.#rev++;
  }

  /** A pointer gesture changed ``def`` live; record where it started. */
  commitGesture(start: LayoutDefinition): void {
    if (this.def === start) return;
    this.#history.record(start);
    this.#history.seal();
    this.#rev++;
  }

  undo(): void {
    const previous = this.#history.undo(this.def);
    if (!previous) return;
    this.def = previous;
    this.#rev++;
    this.prune();
  }

  redo(): void {
    const next = this.#history.redo(this.def);
    if (!next) return;
    this.def = next;
    this.#rev++;
    this.prune();
  }

  prune(): void {
    const ids = new Set(this.def.elements.map((e) => e.id));
    this.selected = this.selected.filter((s) => ids.has(s));
  }

  // ---- selection

  select(id: string, additive = false): void {
    if (!additive) this.selected = [id];
    else this.selected = this.selected.includes(id) ? this.selected.filter((s) => s !== id) : [...this.selected, id];
  }

  selectAll(): void {
    this.selected = this.def.elements.filter((e) => !e.locked).map((e) => e.id);
  }

  // ---- elements

  add(type: ElementType, cx?: number, cy?: number): void {
    if (!this.editable || !placeable(this.def, type)) return;
    if (this.def.elements.length >= MAX_ELEMENTS) {
      toasts.push("error", t("builder.limit", { n: MAX_ELEMENTS }));
      return;
    }
    const el = newElement(this.def, type, cx, cy, this.addSlot);
    this.apply(addElements(this.def, [el]));
    this.selected = [el.id];
  }

  removeSelected(): void {
    const ids = this.sel.filter((e) => !e.locked).map((e) => e.id);
    if (!ids.length) return;
    this.apply(removeElements(this.def, ids));
    this.prune();
  }

  paste(elements: LayoutElement[] = clipboard): void {
    if (!elements.length || !this.editable) return;
    const room = MAX_ELEMENTS - this.def.elements.length;
    if (room <= 0) {
      toasts.push("error", t("builder.limit", { n: MAX_ELEMENTS }));
      return;
    }
    const copies = cloneElements(this.def, elements.slice(0, room));
    this.apply(addElements(this.def, copies));
    this.selected = copies.map((e) => e.id);
  }

  duplicateSelected(): void {
    this.paste(this.sel);
  }

  copy(): void {
    clipboard = structuredClone($state.snapshot(this.sel) as LayoutElement[]);
  }

  cut(): void {
    this.copy();
    this.removeSelected();
  }

  patch(id: string, change: Partial<LayoutElement>, key: string | null = null): void {
    this.apply(updateElement(this.def, id, change), key);
  }

  /** A typed position/size; ``keepRatio``: the other side follows a new w/h. */
  setGeom(e: LayoutElement, field: "x" | "y" | "w" | "h", raw: string, keepRatio = false): void {
    const v = Number(raw);
    if (!Number.isFinite(v)) return;
    const r: Rect = { ...rectOf(e), [field]: Math.round(v) };
    if (keepRatio && e.w > 0 && e.h > 0) {
      if (field === "w") r.h = Math.round((r.w * e.h) / e.w);
      if (field === "h") r.w = Math.round((r.h * e.w) / e.h);
    }
    this.patch(e.id, clamp(r), `geom:${e.id}:${field}`);
  }

  /** Shrink selected playfields to the size their playfield really takes (centred). */
  fitToContent(): void {
    const boards = new Set(this.sel.filter((e) => !e.locked && e.type === "board").map((e) => e.id));
    if (!boards.size) return;
    const elements = this.def.elements.map((e) => {
      if (!boards.has(e.id)) return e;
      const s = boardSize(boardCell(e.w, e.h));
      return { ...e, ...clamp({ x: e.x + Math.round((e.w - s.w) / 2), y: e.y + Math.round((e.h - s.h) / 2), w: s.w, h: s.h }) };
    });
    this.apply({ ...this.def, elements });
  }

  setProp(e: LayoutElement, prop: string, value: unknown): void {
    const props: Record<string, unknown> = { ...(e.props ?? {}) };
    if (value === undefined || value === null || value === "") delete props[prop];
    else props[prop] = value;
    this.patch(e.id, { props }, `prop:${e.id}:${prop}`);
  }

  /**
   * Change several props of elements at once (one undo step): the given
   * ids, else every unlocked selected element. undefined/null/"" removes a prop.
   */
  setProps(change: Record<string, unknown> | ((e: LayoutElement) => Record<string, unknown>), ids?: string[]): void {
    const pick = new Set(ids ?? this.sel.filter((e) => !e.locked).map((e) => e.id));
    if (!pick.size) return;
    let keys: string[] = [];
    const elements = this.def.elements.map((e) => {
      if (!pick.has(e.id)) return e;
      const props: Record<string, unknown> = { ...(e.props ?? {}) };
      const own = typeof change === "function" ? change(e) : change;
      keys = Object.keys(own);
      for (const [k, v] of Object.entries(own)) {
        if (v === undefined || v === null || v === "") delete props[k];
        else props[k] = v;
      }
      return { ...e, props };
    });
    this.apply({ ...this.def, elements }, `props:${[...pick].join(",")}:${keys.join(",")}`);
  }

  restack(id: string, to: "up" | "down" | "top" | "bottom"): void {
    this.apply(restack(this.def, id, to));
  }

  nudge(dx: number, dy: number): void {
    const movable = this.sel.filter((e) => !e.locked);
    const box = bounds(movable.map(rectOf));
    if (!box) return;
    const d = clampMove(box, dx, dy);
    const ids = new Set(movable.map((e) => e.id));
    this.apply(
      { ...this.def, elements: this.def.elements.map((e) => (ids.has(e.id) ? { ...e, x: e.x + d.dx, y: e.y + d.dy } : e)) },
      "nudge",
    );
  }

  #moveAll(moved: Rect[], movable: LayoutElement[]): void {
    const byId = new Map(movable.map((e, i) => [e.id, moved[i]!]));
    this.apply({ ...this.def, elements: this.def.elements.map((e) => (byId.has(e.id) ? { ...e, ...byId.get(e.id)! } : e)) });
  }

  alignSelected(mode: AlignMode): void {
    const movable = this.sel.filter((e) => !e.locked);
    this.#moveAll(alignRects(movable.map(rectOf), mode), movable);
  }

  distributeSelected(axis: "x" | "y"): void {
    const movable = this.sel.filter((e) => !e.locked);
    this.#moveAll(distribute(movable.map(rectOf), axis), movable);
  }

  /** Centre the selection on the stage (one axis or both). */
  centreSelected(axis: "x" | "y" | "both"): void {
    const movable = this.sel.filter((e) => !e.locked);
    const box = bounds(movable.map(rectOf));
    if (!box) return;
    const dx = axis === "y" ? 0 : Math.round((1920 - box.w) / 2 - box.x);
    const dy = axis === "x" ? 0 : Math.round((1080 - box.h) / 2 - box.y);
    this.#moveAll(movable.map((e) => ({ ...rectOf(e), x: e.x + dx, y: e.y + dy })), movable);
  }

  // ---- slots and pairs

  async changeSlots(raw: string | number): Promise<void> {
    const result = setSlots(this.def, Number(raw));
    if (result.removed > 0 && !(await confirmAsync({ title: t("builder.remove_confirm", { n: result.removed }), danger: true }))) {
      this.def = { ...this.def }; // re-render the select with the old value
      return;
    }
    this.apply(result.def);
    this.prune();
    this.addSlot = Math.min(this.addSlot, result.def.slots - 1);
  }

  async changePairs(pairs: [number, number][]): Promise<void> {
    const result = setPairs(this.def, pairs);
    if (result.removed > 0 && !(await confirmAsync({ title: t("builder.remove_confirm", { n: result.removed }), danger: true }))) {
      this.def = { ...this.def };
      return;
    }
    this.apply(result.def);
    this.prune();
  }

  addPair(): void {
    const free = unpairedSlots(this.def);
    if (free.length >= 2) void this.changePairs([...this.def.pairs, [free[0]!, free[1]!]]);
  }

  setPairSlot(index: number, side: 0 | 1, slot: number): void {
    const pairs = this.def.pairs.map((p) => [...p] as [number, number]);
    const pair = pairs[index]!;
    // Taking a slot from another pair swaps it over, so pairs stay disjoint.
    const other = pairs.findIndex((p, i) => i !== index && p.includes(slot));
    if (other >= 0) {
      const o = pairs[other]!;
      o[o.indexOf(slot)] = pair[side];
    } else if (pair[1 - side] === slot) {
      pair[1 - side] = pair[side];
    }
    pair[side] = slot;
    void this.changePairs(pairs);
  }

  async mirror(from: number, to: number): Promise<void> {
    const target = this.def.elements.filter((e) => e.slot === to).length;
    if (target > 0 && !(await confirmAsync({ title: t("builder.mirror_confirm", { n: target, to: to + 1 }), danger: true }))) return;
    this.apply(mirrorSlot(this.def, from, to).def);
    this.prune();
  }

  // ---- keyboard (shared shortcuts; the page adds save)

  /** Handle an editor shortcut; true when it was one. */
  handleKey(event: KeyboardEvent): boolean {
    const target = event.target as HTMLElement | null;
    if (target && (["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName) || target.isContentEditable)) return false;
    if (document.querySelector("dialog[open]")) return false;
    const ctrl = event.ctrlKey || event.metaKey;
    const key = event.key.toLowerCase();
    if (ctrl && key === "z" && !event.shiftKey) this.undo();
    else if (ctrl && (key === "y" || (key === "z" && event.shiftKey))) this.redo();
    else if (!this.editable) return false;
    else if (ctrl && key === "c") this.copy();
    else if (ctrl && key === "x") this.cut();
    else if (ctrl && key === "v") this.paste();
    else if (ctrl && key === "d") this.duplicateSelected();
    else if (ctrl && key === "a") this.selectAll();
    else if (key === "delete" || key === "backspace") this.removeSelected();
    else if (key === "escape") this.selected = [];
    else if (key.startsWith("arrow") && this.sel.length) {
      const step = event.shiftKey ? 8 : 1;
      this.nudge(key === "arrowleft" ? -step : key === "arrowright" ? step : 0, key === "arrowup" ? -step : key === "arrowdown" ? step : 0);
    } else return false;
    event.preventDefault();
    return true;
  }
}
