<script lang="ts" module>
  import { confirmAsync } from "../lib/confirm.svelte";
  import type { LayoutElement as ClipElement } from "../lib/studio";
  // Copy/paste works across layouts while the admin page stays open.
  let clipboard: ClipElement[] = [];
</script>

<script lang="ts">
  // Layout builder: place elements freely on the 1920x1080 stage. The overlay
  // app renders the stage (iframe /o/_edit with demo data, exactly as in OBS);
  // this page draws the selection, handles and guides on top of it. The
  // document is immutable (every edit is a new definition), which keeps
  // undo/redo simple and the iframe messages plain data.
  import { onMount } from "svelte";
  import GuideOverlay from "../components/GuideOverlay.svelte";
  import GuideTools from "../components/GuideTools.svelte";
  import Thumb from "../components/Thumb.svelte";
  import { api, ApiError } from "../lib/api";
  import {
    addElements,
    CATALOGUE,
    cloneElements,
    emptyDefinition,
    inMarquee,
    localProblems,
    MAX_ELEMENTS,
    MAX_SLOTS,
    newElement,
    OPTIONAL_PAIR_TYPES,
    PAIR_TYPES,
    placeable,
    removeElements,
    restack,
    setPairs,
    setSlots,
    SLOT_TYPES,
    STAT_FIELDS,
    unpairedSlots,
    updateElement,
  } from "../lib/editor/elements";
  import {
    align as alignRects,
    bounds,
    CANVAS_H,
    CANVAS_W,
    clamp,
    clampMove,
    distribute,
    fromPoints,
    HANDLES,
    resize,
    snapMove,
    type AlignMode,
    type Guide,
    type Handle,
    type Rect,
  } from "../lib/editor/geometry";
  import { History } from "../lib/editor/history";
  import { fillHeight } from "../lib/fillHeight";
  import { guides as guideLines } from "../lib/guides.svelte";
  import { mirrorSlot } from "../lib/editor/mirror";
  import { i18n, t, tDynamic } from "../lib/i18n.svelte";
  import { router } from "../lib/router.svelte";
  import {
    defaultSettings,
    downloadExport,
    type CustomLayout,
    type ElementType,
    type LayoutDefinition,
    type LayoutElement,
    type PreviewConfig,
    type Style,
  } from "../lib/studio";
  import { toasts } from "../lib/toast.svelte";

  let { id }: { id: string } = $props();

  interface Template {
    id: string;
    name_de: string;
    name_en: string;
    description_de: string;
    description_en: string;
    definition: LayoutDefinition;
  }
  interface ServerError {
    element: number | null;
    field: string;
    message: string;
  }
  interface Draft {
    name: string;
    description: string;
    def: LayoutDefinition;
    version: number | null;
    at: string;
  }

  const SLOT_COLORS = ["#f8b800", "#3cbcfc", "#58d854", "#f83800", "#b46cff", "#ff7eb6", "#00e0c0", "#e0e0e0"];
  const ALIGN_MODES: { mode: AlignMode; icon: string }[] = [
    { mode: "left", icon: "⇤" },
    { mode: "hcenter", icon: "↔" },
    { mode: "right", icon: "⇥" },
    { mode: "top", icon: "⤒" },
    { mode: "vcenter", icon: "↕" },
    { mode: "bottom", icon: "⤓" },
  ];
  const DRAG_TYPE = "application/x-nltm-element";

  // ---- document
  let layoutId = $state<string | null>(null);
  let version = $state<number | null>(null);
  let name = $state("");
  let description = $state("");
  let def = $state.raw<LayoutDefinition>(emptyDefinition());
  let saved = $state("");
  let usedBy = $state<string[]>([]);
  let loaded = $state(false);
  let notFound = $state(false);
  let starting = $state(false);
  let saving = $state(false);
  let templates = $state.raw<Template[]>([]);
  let draft = $state.raw<Draft | null>(null);
  let serverErrors = $state<ServerError[]>([]);
  let errorIds = $state<string[]>([]);

  // ---- view
  let selected = $state<string[]>([]);
  let guides = $state<Guide[]>([]);
  let marquee = $state<Rect | null>(null);
  let zoom = $state<"fit" | number>("fit");
  let showGrid = $state(true);
  let style = $state<Style>("nes");
  let background = $state<"dark" | "checker" | "transparent">("dark");
  let wrapW = $state(1200);
  let layer = $state<HTMLDivElement | null>(null);
  let addSlot = $state(0);
  let mirrorFrom = $state(0);
  let mirrorTo = $state(1);

  const history = new History<LayoutDefinition>();
  let histRev = $state(0);

  const scale = $derived(zoom === "fit" ? Math.max(0.2, (wrapW - 4) / CANVAS_W) : zoom);
  const snapshot = (): string => JSON.stringify({ name, description, def });
  const dirty = $derived(loaded && !starting && snapshot() !== saved);
  const ordered = $derived(
    def.elements
      .map((e, i) => ({ e, i }))
      .sort((a, b) => (a.e.z ?? 0) - (b.e.z ?? 0) || a.i - b.i)
      .map(({ e }) => e),
  );
  const sel = $derived(def.elements.filter((e) => selected.includes(e.id)));
  const one = $derived(sel.length === 1 ? sel[0]! : null);
  const problems = $derived(localProblems(def));
  const canUndo = $derived(histRev >= 0 && history.canUndo);
  const canRedo = $derived(histRev >= 0 && history.canRedo);
  const slotNumbers = $derived(Array.from({ length: def.slots }, (_, i) => i));
  const draftKey = $derived(`nltm.layout-draft.${id}`);

  const preview = $derived<PreviewConfig>(configFor(def, name || "Layout", style));

  function configFor(definition: LayoutDefinition, title: string, s: Style = "nes"): PreviewConfig {
    return {
      scene: {
        slug: "preview",
        name: title,
        layout: "custom:edit",
        mode: "none",
        auto_round: false,
        settings: { ...defaultSettings(), style: s },
        pairs: definition.pairs,
      },
      slots: definition.slots,
      definition,
    };
  }

  // ---- edits (all through apply: one undo step each)

  function apply(next: LayoutDefinition, key: string | null = null): void {
    if (next === def) return;
    history.record(def, key);
    def = next;
    histRev++;
  }

  function prune(): void {
    const ids = new Set(def.elements.map((e) => e.id));
    selected = selected.filter((s) => ids.has(s));
  }

  function undo(): void {
    const previous = history.undo(def);
    if (!previous) return;
    def = previous;
    histRev++;
    prune();
  }

  function redo(): void {
    const next = history.redo(def);
    if (!next) return;
    def = next;
    histRev++;
    prune();
  }

  function rectOf(e: LayoutElement): Rect {
    return { x: e.x, y: e.y, w: e.w, h: e.h };
  }

  function typeLabel(type: ElementType): string {
    return tDynamic(`builder.type_${type}`, type);
  }

  function boxLabel(e: LayoutElement): string {
    let label = typeLabel(e.type);
    if (e.type === "stat") label = tDynamic(`builder.field_${String(e.props?.field ?? "score")}`, label);
    if (e.slot !== undefined && e.slot !== null) label += ` · S${e.slot + 1}`;
    if (e.pair !== undefined && e.pair !== null) label += ` · P${e.pair + 1}`;
    return label;
  }

  function colorOf(e: LayoutElement): string {
    if (e.slot !== undefined && e.slot !== null) return SLOT_COLORS[e.slot % SLOT_COLORS.length]!;
    return "#ffffff";
  }

  function add(type: ElementType, cx?: number, cy?: number): void {
    if (!placeable(def, type)) return;
    if (def.elements.length >= MAX_ELEMENTS) {
      toasts.push("error", t("builder.limit", { n: MAX_ELEMENTS }));
      return;
    }
    const el = newElement(def, type, cx, cy, addSlot);
    apply(addElements(def, [el]));
    selected = [el.id];
  }

  function removeSelected(): void {
    const ids = sel.filter((e) => !e.locked).map((e) => e.id);
    if (!ids.length) return;
    apply(removeElements(def, ids));
    prune();
  }

  function duplicateSelected(): void {
    if (!sel.length) return;
    paste(sel);
  }

  function paste(elements: LayoutElement[]): void {
    if (!elements.length) return;
    const room = MAX_ELEMENTS - def.elements.length;
    if (room <= 0) {
      toasts.push("error", t("builder.limit", { n: MAX_ELEMENTS }));
      return;
    }
    const copies = cloneElements(def, elements.slice(0, room));
    apply(addElements(def, copies));
    selected = copies.map((e) => e.id);
  }

  function patch(eid: string, change: Partial<LayoutElement>, key: string | null = null): void {
    apply(updateElement(def, eid, change), key);
  }

  function setGeom(e: LayoutElement, field: "x" | "y" | "w" | "h", raw: string): void {
    const v = Number(raw);
    if (!Number.isFinite(v)) return;
    patch(e.id, clamp({ ...rectOf(e), [field]: v }), `geom:${e.id}:${field}`);
  }

  function setProp(e: LayoutElement, prop: string, value: unknown): void {
    const props: Record<string, unknown> = { ...(e.props ?? {}) };
    if (value === undefined || value === null || value === "") delete props[prop];
    else props[prop] = value;
    patch(e.id, { props }, `prop:${e.id}:${prop}`);
  }

  function nudge(dx: number, dy: number): void {
    const movable = sel.filter((e) => !e.locked);
    const box = bounds(movable.map(rectOf));
    if (!box) return;
    const d = clampMove(box, dx, dy);
    const ids = new Set(movable.map((e) => e.id));
    apply(
      { ...def, elements: def.elements.map((e) => (ids.has(e.id) ? { ...e, x: e.x + d.dx, y: e.y + d.dy } : e)) },
      "nudge",
    );
  }

  function alignSelected(mode: AlignMode): void {
    const movable = sel.filter((e) => !e.locked);
    const moved = alignRects(movable.map(rectOf), mode);
    const byId = new Map(movable.map((e, i) => [e.id, moved[i]!]));
    apply({ ...def, elements: def.elements.map((e) => (byId.has(e.id) ? { ...e, ...byId.get(e.id)! } : e)) });
  }

  function distributeSelected(axis: "x" | "y"): void {
    const movable = sel.filter((e) => !e.locked);
    const moved = distribute(movable.map(rectOf), axis);
    const byId = new Map(movable.map((e, i) => [e.id, moved[i]!]));
    apply({ ...def, elements: def.elements.map((e) => (byId.has(e.id) ? { ...e, ...byId.get(e.id)! } : e)) });
  }

  async function changeSlots(raw: string): Promise<void> {
    const result = setSlots(def, Number(raw));
    if (result.removed > 0 && !(await confirmAsync({ title: t("builder.remove_confirm", { n: result.removed }), danger: true }))) {
      def = { ...def }; // re-render the select with the old value
      return;
    }
    apply(result.def);
    prune();
    addSlot = Math.min(addSlot, result.def.slots - 1);
  }

  async function changePairs(pairs: [number, number][]): Promise<void> {
    const result = setPairs(def, pairs);
    if (result.removed > 0 && !(await confirmAsync({ title: t("builder.remove_confirm", { n: result.removed }), danger: true }))) {
      def = { ...def };
      return;
    }
    apply(result.def);
    prune();
  }

  function addPair(): void {
    const free = unpairedSlots(def);
    if (free.length >= 2) changePairs([...def.pairs, [free[0]!, free[1]!]]);
  }

  function setPairSlot(index: number, side: 0 | 1, slot: number): void {
    const pairs = def.pairs.map((p) => [...p] as [number, number]);
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
    changePairs(pairs);
  }

  async function runMirror(): Promise<void> {
    const target = def.elements.filter((e) => e.slot === mirrorTo).length;
    if (target > 0 && !(await confirmAsync({ title: t("builder.mirror_confirm", { n: target, to: mirrorTo + 1 }), danger: true }))) return;
    apply(mirrorSlot(def, mirrorFrom, mirrorTo).def);
    prune();
  }

  // ---- pointer gestures on the stage

  type Gesture =
    | { kind: "move"; start: LayoutDefinition; px: number; py: number; origin: Map<string, Rect>; box: Rect; moved: boolean; collapseTo: string | null }
    | { kind: "resize"; start: LayoutDefinition; px: number; py: number; id: string; handle: Handle; rect: Rect; moved: boolean }
    | { kind: "marquee"; px: number; py: number; base: string[] };
  let gesture: Gesture | null = null;

  function point(e: { clientX: number; clientY: number }): { x: number; y: number } {
    const r = layer!.getBoundingClientRect();
    return { x: (e.clientX - r.left) / scale, y: (e.clientY - r.top) / scale };
  }

  function others(ids: Set<string>): Rect[] {
    const rects = def.elements.filter((e) => !ids.has(e.id) && !e.hidden).map(rectOf);
    // Shown guide lines snap too (a line = a zero-width rectangle).
    for (const g of guideLines.snapLines()) {
      rects.push(g.axis === "x" ? { x: g.at, y: 0, w: 0, h: CANVAS_H } : { x: 0, y: g.at, w: CANVAS_W, h: 0 });
    }
    return rects;
  }

  function capture(event: PointerEvent): void {
    try {
      layer?.setPointerCapture(event.pointerId);
    } catch {
      // pointer already gone (e.g. released during a re-render): no capture needed
    }
  }

  function onBoxDown(event: PointerEvent, el: LayoutElement): void {
    if (event.button !== 0 || el.locked) return; // locked: click goes through (marquee)
    event.stopPropagation();
    capture(event);
    const p = point(event);
    let collapseTo: string | null = null;
    if (event.shiftKey) {
      if (selected.includes(el.id)) {
        selected = selected.filter((s) => s !== el.id);
        return;
      }
      selected = [...selected, el.id];
    } else if (!selected.includes(el.id)) {
      selected = [el.id];
    } else {
      collapseTo = el.id; // a click without moving selects just this one
    }
    const moving = def.elements.filter((e) => selected.includes(e.id) && !e.locked);
    gesture = {
      kind: "move",
      start: def,
      px: p.x,
      py: p.y,
      origin: new Map(moving.map((e) => [e.id, rectOf(e)])),
      box: bounds(moving.map(rectOf)) ?? rectOf(el),
      moved: false,
      collapseTo,
    };
  }

  function onHandleDown(event: PointerEvent, el: LayoutElement, handle: Handle): void {
    if (event.button !== 0) return;
    event.stopPropagation();
    capture(event);
    const p = point(event);
    gesture = { kind: "resize", start: def, px: p.x, py: p.y, id: el.id, handle, rect: rectOf(el), moved: false };
  }

  function onLayerDown(event: PointerEvent): void {
    if (event.button !== 0) return;
    capture(event);
    layer?.focus();
    const p = point(event);
    if (!event.shiftKey) selected = [];
    gesture = { kind: "marquee", px: p.x, py: p.y, base: [...selected] };
  }

  function onMove(event: PointerEvent): void {
    const g = gesture;
    if (!g) return;
    const p = point(event);
    const opts = { threshold: 6 / scale, grid: showGrid ? 8 : 1, free: event.altKey };
    if (g.kind === "move") {
      const raw = { dx: p.x - g.px, dy: p.y - g.py };
      if (!g.moved && Math.hypot(raw.dx, raw.dy) * scale < 3) return; // a click, not a drag
      g.moved = true;
      const snapped = snapMove(g.box, raw.dx, raw.dy, { ...opts, targets: others(new Set(g.origin.keys())) });
      const d = clampMove(g.box, snapped.dx, snapped.dy);
      guides = snapped.guides;
      def = {
        ...g.start,
        elements: g.start.elements.map((e) => {
          const o = g.origin.get(e.id);
          return o ? { ...e, x: o.x + d.dx, y: o.y + d.dy } : e;
        }),
      };
    } else if (g.kind === "resize") {
      g.moved = true;
      const r = resize(g.rect, g.handle, p.x - g.px, p.y - g.py, { ...opts, targets: others(new Set([g.id])) }, event.shiftKey);
      guides = r.guides;
      def = updateElement(g.start, g.id, r.rect);
    } else {
      marquee = fromPoints(g.px, g.py, p.x, p.y);
      const hit = marquee.w > 2 || marquee.h > 2 ? inMarquee(def, marquee) : [];
      selected = [...new Set([...g.base, ...hit])];
    }
  }

  function onUp(): void {
    const g = gesture;
    gesture = null;
    guides = [];
    marquee = null;
    if (!g) return;
    if ((g.kind === "move" || g.kind === "resize") && g.moved && def !== g.start) {
      history.record(g.start);
      history.seal();
      histRev++;
    } else if (g.kind === "move" && !g.moved && g.collapseTo) {
      selected = [g.collapseTo];
    }
  }

  function onDragOver(event: DragEvent): void {
    if (event.dataTransfer?.types.includes(DRAG_TYPE)) event.preventDefault();
  }

  function onDrop(event: DragEvent): void {
    const type = event.dataTransfer?.getData(DRAG_TYPE) as ElementType | undefined;
    if (!type || !CATALOGUE.some((c) => c.type === type)) return;
    event.preventDefault();
    const p = point(event);
    add(type, p.x, p.y);
  }

  // ---- keyboard

  function onKey(event: KeyboardEvent): void {
    if (!loaded || starting) return;
    const target = event.target as HTMLElement | null;
    if (target && (["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName) || target.isContentEditable)) return;
    if (document.querySelector("dialog[open]")) return;
    const ctrl = event.ctrlKey || event.metaKey;
    const key = event.key.toLowerCase();
    let handled = true;
    if (ctrl && key === "z" && !event.shiftKey) undo();
    else if (ctrl && (key === "y" || (key === "z" && event.shiftKey))) redo();
    else if (ctrl && key === "s") void save(false);
    else if (ctrl && key === "c") clipboard = structuredClone(sel);
    else if (ctrl && key === "x") {
      clipboard = structuredClone(sel);
      removeSelected();
    } else if (ctrl && key === "v") paste(clipboard);
    else if (ctrl && key === "d") duplicateSelected();
    else if (ctrl && key === "a") selected = def.elements.filter((e) => !e.locked).map((e) => e.id);
    else if (key === "delete" || key === "backspace") removeSelected();
    else if (key === "escape") selected = [];
    else if (key.startsWith("arrow") && sel.length) {
      const step = event.shiftKey ? 8 : 1;
      nudge(key === "arrowleft" ? -step : key === "arrowright" ? step : 0, key === "arrowup" ? -step : key === "arrowdown" ? step : 0);
    } else handled = false;
    if (handled) event.preventDefault();
  }

  // ---- load / save

  function adopt(row: CustomLayout): void {
    layoutId = row.id;
    version = row.version;
    name = row.name;
    description = row.description;
    def = row.definition ?? emptyDefinition();
    saved = snapshot();
    history.clear();
    histRev++;
  }

  function begin(definition: LayoutDefinition, title: string): void {
    def = $state.snapshot(definition) as LayoutDefinition;
    name = title;
    description = "";
    saved = JSON.stringify({ name: "", description: "", def: emptyDefinition() });
    starting = false;
    history.clear();
    histRev++;
    selected = [];
    addSlot = 0;
  }

  async function load(): Promise<void> {
    api<Template[]>("/api/studio/templates")
      .then((list) => (templates = list))
      .catch(() => {});
    if (id === "new") {
      starting = true;
      loaded = true;
      readDraft();
      return;
    }
    try {
      const [row, list] = await Promise.all([
        api<CustomLayout>(`/api/overlay-layouts/${encodeURIComponent(id)}`),
        api<CustomLayout[]>("/api/overlay-layouts"),
      ]);
      adopt(row);
      usedBy = list.find((l) => l.id === row.id)?.used_by ?? [];
      loaded = true;
      readDraft();
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) notFound = true;
      else toasts.error(e);
    }
  }

  function readDraft(): void {
    try {
      const raw = localStorage.getItem(draftKey);
      if (!raw) return;
      const d = JSON.parse(raw) as Draft;
      if (!d?.def || !Array.isArray(d.def.elements)) return;
      const same = JSON.stringify({ name: d.name, description: d.description, def: d.def }) === saved;
      if (!same && (d.version ?? null) === version) draft = d;
    } catch {
      // A broken draft is only a lost convenience.
    }
  }

  function restoreDraft(): void {
    if (!draft) return;
    const d = draft;
    if (starting) begin(d.def, d.name);
    else apply(d.def);
    name = d.name;
    description = d.description;
    draft = null;
  }

  function dropDraft(): void {
    draft = null;
    try {
      localStorage.removeItem(draftKey);
    } catch {
      // ignore
    }
  }

  // Keep a draft of unsaved work (a crash or a closed tab loses nothing).
  $effect(() => {
    const key = draftKey;
    if (!dirty) return;
    const data: Draft = { name, description, def, version, at: new Date().toISOString() };
    const timer = setTimeout(() => {
      try {
        localStorage.setItem(key, JSON.stringify(data));
      } catch {
        // storage full or blocked: no draft
      }
    }, 600);
    return () => clearTimeout(timer);
  });

  function markErrors(errors: ServerError[], submitted: LayoutDefinition): void {
    serverErrors = errors;
    errorIds = errors
      .map((err) => (err.element !== null ? submitted.elements[err.element]?.id : undefined))
      .filter((x): x is string => !!x);
  }

  function errorLabel(err: ServerError, submitted: LayoutDefinition): string {
    const el = err.element !== null ? submitted.elements[err.element] : undefined;
    return el ? `${boxLabel(el)} (${el.id})` : t("builder.layout_error");
  }
  let submitted = $state.raw<LayoutDefinition>(emptyDefinition());

  async function save(asCopy: boolean): Promise<void> {
    if (saving) return;
    if (!name.trim()) {
      toasts.push("error", t("builder.name_required"));
      return;
    }
    saving = true;
    submitted = def;
    const body = { name: name.trim(), description: description.trim(), definition: def };
    try {
      let row: CustomLayout;
      if (asCopy || layoutId === null) {
        row = await api<CustomLayout>("/api/overlay-layouts", {
          method: "POST",
          body: asCopy ? { ...body, name: t("builder.copy_name", { name: body.name }).slice(0, 64) } : body,
        });
      } else {
        row = await api<CustomLayout>(`/api/overlay-layouts/${layoutId}`, {
          method: "PUT",
          body: { ...body, expected_version: version },
        });
      }
      serverErrors = [];
      errorIds = [];
      dropDraft();
      toasts.ok(t("builder.saved"));
      if (asCopy || id === "new") {
        saved = snapshot(); // the work lives on in the new layout
        router.go(`/studio/layout/${row.id}`);
      } else {
        adopt(row);
      }
    } catch (e) {
      if (e instanceof ApiError && e.code === "invalid") {
        const detail = (e.body as { detail?: { errors?: ServerError[] } } | null)?.detail;
        markErrors(detail?.errors ?? [], submitted);
        toasts.push("error", t("builder.invalid", { n: serverErrors.length }));
      } else if (e instanceof ApiError && e.code === "stale") {
        toasts.push("error", t("builder.stale"));
      } else {
        toasts.error(e);
      }
    } finally {
      saving = false;
    }
  }

  async function remove(): Promise<void> {
    if (!layoutId) return;
    if (!(await confirmAsync({ title: t("studio.confirm_delete_layout", { name }), danger: true, confirmLabel: t("common.delete") }))) return;
    try {
      await api(`/api/overlay-layouts/${layoutId}`, { method: "DELETE" });
      dropDraft();
      saved = snapshot();
      router.go("/studio?tab=layouts");
    } catch (e) {
      toasts.error(e);
    }
  }

  function exportLayout(): void {
    if (layoutId) downloadExport({ layouts: layoutId }).catch((e) => toasts.error(e));
  }

  onMount(() => {
    void load();
    const beforeUnload = (e: BeforeUnloadEvent): void => {
      if (dirty) e.preventDefault();
    };
    const unguard = router.setGuard(async () => !dirty || (await confirmAsync({ title: t("studio.unsaved_confirm"), danger: true, confirmLabel: t("common.discard") })));
    addEventListener("beforeunload", beforeUnload);
    addEventListener("keydown", onKey);
    return () => {
      removeEventListener("beforeunload", beforeUnload);
      removeEventListener("keydown", onKey);
      unguard();
    };
  });
</script>

{#if notFound}
  <p class="muted">{t("common.not_found")} · <a href="#/studio?tab=layouts">{t("studio.title")}</a></p>
{:else if loaded && starting}
  <div class="head row">
    <a href="#/studio?tab=layouts" class="muted">← {t("studio.title")}</a>
    <h1>{t("builder.title_new")}</h1>
  </div>
  {#if draft}
    <div class="banner row">
      <span>{t("builder.draft_found", { at: new Date(draft.at).toLocaleString(i18n.locale) })}</span>
      <span class="spacer"></span>
      <button class="primary" onclick={restoreDraft}>{t("builder.draft_restore")}</button>
      <button onclick={dropDraft}>{t("builder.draft_discard")}</button>
    </div>
  {/if}
  <h2 class="sub">{t("builder.start")}</h2>
  <div class="starts">
    {#each [1, 2, 4] as n (n)}
      <button class="start" onclick={() => begin(emptyDefinition(n), "")}>
        <div class="blank">{n} × ▢</div>
        <strong>{t("builder.start_blank")}</strong>
        <span class="muted small">{t("builder.start_blank_hint", { n })}</span>
      </button>
    {/each}
    {#each templates as tpl (tpl.id)}
      <button class="start" onclick={() => begin(tpl.definition, i18n.locale === "en" ? tpl.name_en : tpl.name_de)}>
        <Thumb config={configFor(tpl.definition, i18n.locale === "en" ? tpl.name_en : tpl.name_de)} />
        <strong>{i18n.locale === "en" ? tpl.name_en : tpl.name_de}</strong>
        <span class="muted small">{i18n.locale === "en" ? tpl.description_en : tpl.description_de}</span>
      </button>
    {/each}
  </div>
{:else if loaded}
  <div class="head row">
    <a href="#/studio?tab=layouts" class="muted">← {t("studio.title")}</a>
    <h1>{name || t("builder.title_new")}</h1>
    {#if dirty}<span class="badge warn">{t("studio.unsaved")}</span>{/if}
    <span class="spacer"></span>
    {#if layoutId}
      <button onclick={exportLayout}>{t("studio.export")}</button>
      <button class="danger" disabled={usedBy.length > 0} title={usedBy.length ? t("studio.in_use") : ""} onclick={remove}>
        {t("common.delete")}
      </button>
      <button onclick={() => save(true)} disabled={saving}>{t("builder.save_copy")}</button>
    {/if}
    <button class="primary" onclick={() => save(false)} disabled={saving || (!dirty && layoutId !== null)}>{t("builder.save")}</button>
  </div>
  {#if draft}
    <div class="banner row">
      <span>{t("builder.draft_found", { at: new Date(draft.at).toLocaleString(i18n.locale) })}</span>
      <span class="spacer"></span>
      <button class="primary" onclick={restoreDraft}>{t("builder.draft_restore")}</button>
      <button onclick={dropDraft}>{t("builder.draft_discard")}</button>
    </div>
  {/if}
  {#if usedBy.length}
    <p class="hint">{t("builder.used_by", { scenes: usedBy.join(", ") })}</p>
  {/if}

  <div class="builder fill-page">
    <!-- left: layout + palette -->
    <aside class="side" use:fillHeight>
      <section class="panel block">
        <h2>{t("builder.layout")}</h2>
        <label>{t("builder.name")}<input bind:value={name} maxlength="64" /></label>
        <label>{t("builder.description")}<textarea bind:value={description} maxlength="500" rows="2"></textarea></label>
        <label>
          {t("builder.slots")}
          <select value={def.slots} onchange={(e) => changeSlots(e.currentTarget.value)}>
            {#each Array.from({ length: MAX_SLOTS }, (_, i) => i + 1) as n (n)}<option value={n}>{n}</option>{/each}
          </select>
        </label>
        <div class="pairs">
          <span class="label">{t("builder.pairs")}</span>
          {#each def.pairs as pair, i (i)}
            <div class="row pair">
              <span class="muted">P{i + 1}</span>
              <select value={pair[0]} onchange={(e) => setPairSlot(i, 0, Number(e.currentTarget.value))}>
                {#each slotNumbers as s (s)}<option value={s}>S{s + 1}</option>{/each}
              </select>
              <span>vs</span>
              <select value={pair[1]} onchange={(e) => setPairSlot(i, 1, Number(e.currentTarget.value))}>
                {#each slotNumbers as s (s)}<option value={s}>S{s + 1}</option>{/each}
              </select>
              <button class="icon" aria-label={t("builder.delete")} onclick={() => changePairs(def.pairs.filter((_, j) => j !== i))}>✕</button>
            </div>
          {:else}
            <span class="muted small">{t("builder.no_pairs")}</span>
          {/each}
          {#if unpairedSlots(def).length >= 2 && def.pairs.length < 4}
            <button onclick={addPair}>{t("builder.add_pair")}</button>
          {/if}
          <span class="muted small">{t("builder.pairs_hint")}</span>
        </div>
        {#if def.slots >= 2}
          <div class="mirror">
            <span class="label">{t("builder.mirror")}</span>
            <div class="row">
              <select bind:value={mirrorFrom}>{#each slotNumbers as s (s)}<option value={s}>Slot {s + 1}</option>{/each}</select>
              <span>→</span>
              <select bind:value={mirrorTo}>{#each slotNumbers as s (s)}<option value={s}>Slot {s + 1}</option>{/each}</select>
            </div>
            <button disabled={mirrorFrom === mirrorTo} onclick={runMirror}>
              {t("builder.mirror_run", { from: mirrorFrom + 1, to: mirrorTo + 1 })}
            </button>
            <span class="muted small">{t("builder.mirror_hint")}</span>
          </div>
        {/if}
      </section>

      <section class="panel block">
        <h2>{t("builder.palette")}</h2>
        <label class="row inline">
          {t("builder.add_to")}
          <select bind:value={addSlot}>{#each slotNumbers as s (s)}<option value={s}>Slot {s + 1}</option>{/each}</select>
        </label>
        <div class="palette">
          {#each CATALOGUE as c (c.type)}
            {@const ok = placeable(def, c.type)}
            <button
              class="tile"
              disabled={!ok}
              title={ok ? "" : t("builder.needs_pair")}
              draggable={ok}
              ondragstart={(e) => e.dataTransfer?.setData(DRAG_TYPE, c.type)}
              onclick={() => add(c.type)}
            >
              {typeLabel(c.type)}
            </button>
          {/each}
        </div>
        <span class="muted small">{t("builder.palette_hint")}</span>
      </section>
    </aside>

    <!-- centre: the stage -->
    <section class="center">
      <div class="tools row">
        <button class="icon" title={t("builder.undo")} aria-label={t("builder.undo")} disabled={!canUndo} onclick={undo}>↶</button>
        <button class="icon" title={t("builder.redo")} aria-label={t("builder.redo")} disabled={!canRedo} onclick={redo}>↷</button>
        <div class="seg">
          <button aria-pressed={zoom === "fit"} class:on={zoom === "fit"} onclick={() => (zoom = "fit")}>{t("builder.zoom_fit")}</button>
          {#each [0.5, 0.75, 1] as z (z)}
            <button aria-pressed={zoom === z} class:on={zoom === z} onclick={() => (zoom = z)}>{z * 100}%</button>
          {/each}
        </div>
        <label class="row inline"><input type="checkbox" bind:checked={showGrid} /> {t("builder.grid")}</label>
        <div class="seg" title={t("builder.style_preview")}>
          <button aria-pressed={style === "nes"} class:on={style === "nes"} onclick={() => (style = "nes")}>NES</button>
          <button aria-pressed={style === "modern"} class:on={style === "modern"} onclick={() => (style = "modern")}>Modern</button>
        </div>
        <GuideTools />
        <div class="seg">
          <button aria-pressed={background === "checker"} class:on={background === "checker"} onclick={() => (background = "checker")}>{t("studio.bg_checker")}</button>
          <button aria-pressed={background === "dark"} class:on={background === "dark"} onclick={() => (background = "dark")}>{t("scenes.bg_dark")}</button>
        </div>
        {#if sel.length > 1}
          <span class="sep"></span>
          {#each ALIGN_MODES as a (a.mode)}
            <button class="icon" title="{t('builder.align')}: {a.mode}" aria-label={a.mode} onclick={() => alignSelected(a.mode)}>{a.icon}</button>
          {/each}
          {#if sel.length > 2}
            <button class="icon" title={t("builder.distribute_h")} aria-label={t("builder.distribute_h")} onclick={() => distributeSelected("x")}>⋯</button>
            <button class="icon" title={t("builder.distribute_v")} aria-label={t("builder.distribute_v")} onclick={() => distributeSelected("y")}>⋮</button>
          {/if}
        {/if}
      </div>

      <div class="canvas-wrap" bind:clientWidth={wrapW}>
        <div class="canvas" style:width="{CANVAS_W * scale}px" style:height="{CANVAS_H * scale}px">
          <Thumb config={preview} still={false} edit background={background} title={name} />
          <div
            class="layer"
            bind:this={layer}
            role="application"
            tabindex="-1"
            aria-label={t("builder.layout")}
            onpointerdown={onLayerDown}
            onpointermove={onMove}
            onpointerup={onUp}
            onpointercancel={onUp}
            ondragover={onDragOver}
            ondrop={onDrop}
          >
            <div class="inner" style:transform="scale({scale})" style:--s={scale}>
              {#if showGrid}<div class="grid" class:coarse={scale < 0.6}></div>{/if}
              {#each ordered as el (el.id)}
                {@const isSel = selected.includes(el.id)}
                <div
                  class="box"
                  class:sel={isSel}
                  class:locked={el.locked}
                  class:ghost={el.hidden}
                  class:err={errorIds.includes(el.id) || problems.has(el.id)}
                  style:left="{el.x}px"
                  style:top="{el.y}px"
                  style:width="{el.w}px"
                  style:height="{el.h}px"
                  style:--c={colorOf(el)}
                  onpointerdown={(e) => onBoxDown(e, el)}
                  role="presentation"
                >
                  <span class="tag">{boxLabel(el)}</span>
                  {#if isSel && one?.id === el.id && !el.locked}
                    {#each HANDLES as h (h)}
                      <div class="handle {h}" onpointerdown={(e) => onHandleDown(e, el, h)} role="presentation"></div>
                    {/each}
                  {/if}
                </div>
              {/each}
              {#each guides as g, i (i)}
                <div class="guide {g.axis}" style:left={g.axis === "x" ? `${g.at}px` : "0"} style:top={g.axis === "y" ? `${g.at}px` : "0"}></div>
              {/each}
              {#if marquee}
                <div class="marquee" style:left="{marquee.x}px" style:top="{marquee.y}px" style:width="{marquee.w}px" style:height="{marquee.h}px"></div>
              {/if}
            </div>
          </div>
          <GuideOverlay />
        </div>
      </div>

      {#if serverErrors.length || problems.size}
        <div class="panel errors">
          <h2>{t("builder.errors")}</h2>
          <ul>
            {#each serverErrors as err, i (i)}
              {@const eid = err.element !== null ? submitted.elements[err.element]?.id : undefined}
              <li>
                {#if eid}<button class="link" onclick={() => (selected = [eid])}>{errorLabel(err, submitted)}</button>{:else}{errorLabel(err, submitted)}{/if}:
                {err.message}
              </li>
            {/each}
            {#each [...problems] as [eid, what] (eid)}
              <li><button class="link" onclick={() => (selected = [eid])}>{eid}</button>: {tDynamic(`builder.problem_${what}`, what)}</li>
            {/each}
          </ul>
        </div>
      {/if}
      <p class="muted small">{t("builder.keys")}</p>
    </section>

    <!-- right: properties + layers -->
    <aside class="side" use:fillHeight>
      <section class="panel block">
        <h2>{t("builder.properties")}</h2>
        {#if one}
          {@const el = one}
          {@const p = el.props ?? {}}
          <div class="row">
            <strong>{typeLabel(el.type)}</strong>
            <span class="muted small">{el.id}</span>
          </div>
          {#if SLOT_TYPES.has(el.type)}
            <label>{t("builder.slot")}
              <select value={el.slot ?? 0} onchange={(e) => patch(el.id, { slot: Number(e.currentTarget.value) })}>
                {#each slotNumbers as s (s)}<option value={s}>Slot {s + 1}</option>{/each}
              </select>
            </label>
          {/if}
          {#if PAIR_TYPES.has(el.type) || OPTIONAL_PAIR_TYPES.has(el.type)}
            <label>{t("builder.pair")}
              <select
                value={el.pair ?? ""}
                onchange={(e) => patch(el.id, { pair: e.currentTarget.value === "" ? null : Number(e.currentTarget.value) })}
              >
                {#if OPTIONAL_PAIR_TYPES.has(el.type)}<option value="">{t("builder.pair_none")}</option>{/if}
                {#each def.pairs as pair, i (i)}<option value={i}>P{i + 1}: Slot {pair[0] + 1} vs {pair[1] + 1}</option>{/each}
              </select>
            </label>
          {/if}
          <div class="geom">
            {#each ["x", "y", "w", "h"] as const as f (f)}
              <label>{f.toUpperCase()}<input type="number" value={el[f]} onchange={(e) => setGeom(el, f, e.currentTarget.value)} /></label>
            {/each}
          </div>
          <div class="row wrap">
            <label class="row inline"><input type="checkbox" checked={!!el.hidden} onchange={(e) => patch(el.id, { hidden: e.currentTarget.checked })} /> {t("builder.hidden")}</label>
            <label class="row inline"><input type="checkbox" checked={!!el.locked} onchange={(e) => patch(el.id, { locked: e.currentTarget.checked })} /> {t("builder.locked")}</label>
          </div>

          {#if el.type === "stat"}
            <label>{t("builder.field")}
              <select value={p.field ?? "score"} onchange={(e) => setProp(el, "field", e.currentTarget.value)}>
                {#each STAT_FIELDS as f (f)}<option value={f}>{tDynamic(`builder.field_${f}`, f)}</option>{/each}
              </select>
            </label>
            <label>{t("builder.label")}
              <input value={p.label ?? ""} placeholder={t("builder.label_auto")} maxlength="24" oninput={(e) => setProp(el, "label", e.currentTarget.value)} />
            </label>
            <label class="row inline"><input type="checkbox" checked={p.show_label !== false} onchange={(e) => setProp(el, "show_label", e.currentTarget.checked)} /> {t("builder.show_label")}</label>
          {/if}
          {#if el.type === "next"}
            <label class="row inline"><input type="checkbox" checked={p.show_label !== false} onchange={(e) => setProp(el, "show_label", e.currentTarget.checked)} /> {t("builder.show_label")}</label>
          {/if}
          {#if el.type === "title" || el.type === "text"}
            <label>{t("builder.text")}
              <input
                value={p.text ?? ""}
                placeholder={el.type === "title" ? t("builder.title_auto") : ""}
                maxlength={el.type === "title" ? 64 : 200}
                oninput={(e) => setProp(el, "text", e.currentTarget.value)}
              />
            </label>
          {/if}
          {#if el.type === "text"}
            <label>{t("builder.size")}
              <input type="number" min="8" max="160" value={p.size ?? 24} onchange={(e) => setProp(el, "size", Math.min(160, Math.max(8, Number(e.currentTarget.value) || 24)))} />
            </label>
          {/if}
          {#if ["stat", "name", "hearts", "nametag", "title", "round", "text"].includes(el.type)}
            <label>{t("builder.align_text")}
              <select value={p.align ?? (el.type === "nametag" || el.type === "title" || el.type === "round" ? "center" : "left")} onchange={(e) => setProp(el, "align", e.currentTarget.value)}>
                {#each ["left", "center", "right"] as a (a)}<option value={a}>{tDynamic(`builder.align_${a}`, a)}</option>{/each}
              </select>
            </label>
          {/if}
          {#if el.type === "stat" || el.type === "text"}
            <div class="row color">
              <span>{t("builder.color")}</span>
              <input type="color" value={typeof p.color === "string" ? p.color : "#fcfcfc"} oninput={(e) => setProp(el, "color", e.currentTarget.value)} />
              {#if p.color}<button class="link" onclick={() => setProp(el, "color", null)}>{t("builder.color_auto")}</button>{/if}
            </div>
          {/if}
          {#if el.type === "name"}
            <label class="row inline"><input type="checkbox" checked={!!p.show_rank} onchange={(e) => setProp(el, "show_rank", e.currentTarget.checked)} /> {t("builder.show_rank")}</label>
          {/if}
          {#if el.type === "nametag"}
            <label class="row inline"><input type="checkbox" checked={!!p.show_round} onchange={(e) => setProp(el, "show_round", e.currentTarget.checked)} /> {t("builder.show_round")}</label>
          {/if}
          {#if el.type === "camera"}
            <label class="row inline"><input type="checkbox" checked={p.framed !== false} onchange={(e) => setProp(el, "framed", e.currentTarget.checked)} /> {t("builder.framed")}</label>
          {/if}
          {#if el.type === "frame"}
            <label>{t("builder.frame_style")}
              <select value={p.style ?? "nes"} onchange={(e) => setProp(el, "style", e.currentTarget.value)}>
                <option value="nes">{t("builder.frame_nes")}</option>
                <option value="panel">{t("builder.frame_panel")}</option>
              </select>
            </label>
          {/if}

          <div class="row wrap">
            <button onclick={() => apply(restack(def, el.id, "up"))}>{t("builder.forward")}</button>
            <button onclick={() => apply(restack(def, el.id, "down"))}>{t("builder.backward")}</button>
            <button onclick={() => apply(restack(def, el.id, "top"))}>{t("builder.to_front")}</button>
            <button onclick={() => apply(restack(def, el.id, "bottom"))}>{t("builder.to_back")}</button>
          </div>
          <div class="row wrap">
            <button onclick={duplicateSelected}>{t("builder.duplicate")}</button>
            <button class="danger" disabled={el.locked} onclick={removeSelected}>{t("builder.delete")}</button>
          </div>
        {:else if sel.length > 1}
          <p>{t("builder.selected_n", { n: sel.length })}</p>
          <div class="row wrap">
            <button onclick={duplicateSelected}>{t("builder.duplicate")}</button>
            <button class="danger" onclick={removeSelected}>{t("builder.delete")}</button>
          </div>
        {:else}
          <p class="muted small">{t("builder.nothing_selected")}</p>
        {/if}
      </section>

      <section class="panel block">
        <h2>{t("builder.layers")} ({def.elements.length})</h2>
        <ul class="layers">
          {#each [...ordered].reverse() as el (el.id)}
            <li class:on={selected.includes(el.id)} class:err={errorIds.includes(el.id) || problems.has(el.id)}>
              <button
                class="layer-name"
                style:--c={colorOf(el)}
                onclick={(e) => (selected = e.shiftKey ? (selected.includes(el.id) ? selected.filter((s) => s !== el.id) : [...selected, el.id]) : [el.id])}
              >
                <span class="dot"></span>{boxLabel(el)}
              </button>
              <button class="icon" class:off={!el.hidden} title={t("builder.hidden")} aria-label={t("builder.hidden")} onclick={() => patch(el.id, { hidden: !el.hidden })}>
                <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true"><path d="M1 8s2.5-5 7-5 7 5 7 5-2.5 5-7 5-7-5-7-5Z" fill="none" stroke="currentColor" stroke-width="1.4" /><circle cx="8" cy="8" r="2.2" fill="currentColor" />{#if el.hidden}<path d="M2 14 14 2" stroke="currentColor" stroke-width="1.6" />{/if}</svg>
              </button>
              <button class="icon" class:off={!el.locked} title={t("builder.locked")} aria-label={t("builder.locked")} onclick={() => patch(el.id, { locked: !el.locked })}>
                <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true"><rect x="3" y="7" width="10" height="7" rx="1.5" fill="currentColor" /><path d={el.locked ? "M5 7V5a3 3 0 0 1 6 0v2" : "M5 7V5a3 3 0 0 1 5.8-1"} fill="none" stroke="currentColor" stroke-width="1.6" /></svg>
              </button>
            </li>
          {/each}
        </ul>
      </section>
    </aside>
  </div>
{/if}

<style>
  .head {
    gap: 10px;
    margin-bottom: 10px;
    flex-wrap: wrap;
  }
  .head h1 {
    margin: 0;
  }
  .banner {
    gap: 10px;
    padding: 8px 12px;
    margin-bottom: 10px;
    border: 1px solid var(--accent);
    border-radius: 8px;
  }
  .builder {
    display: grid;
    grid-template-columns: 260px minmax(0, 1fr) 290px;
    gap: 12px;
    align-items: start;
  }
  .side {
    display: grid;
    gap: 12px;
    max-height: var(--fill-h, calc(100vh - 140px));
    overflow: auto;
    padding-right: 2px;
  }
  .block {
    display: grid;
    gap: 8px;
  }
  .block h2,
  .errors h2 {
    margin: 0;
    font-size: 15px;
  }
  .block label {
    display: grid;
    gap: 4px;
  }
  .block label.inline,
  .row.inline {
    display: flex;
    gap: 6px;
    align-items: center;
  }
  .label {
    font-size: 13px;
    color: var(--muted);
  }
  .pairs,
  .mirror {
    display: grid;
    gap: 6px;
  }
  .pair {
    gap: 6px;
  }
  .pair select,
  .mirror select {
    flex: 1;
    min-width: 0;
  }
  .wrap {
    flex-wrap: wrap;
    gap: 6px;
  }
  .palette {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 6px;
  }
  .tile {
    text-align: left;
    cursor: grab;
    font-size: 13px;
  }
  .center {
    display: grid;
    gap: 8px;
    min-width: 0;
  }
  .tools {
    gap: 8px;
    flex-wrap: wrap;
    align-items: center;
  }
  .sep {
    width: 1px;
    height: 24px;
    background: var(--line);
  }
  .icon {
    min-width: 34px;
    padding: 4px 8px;
  }
  .icon.off {
    opacity: 0.45;
  }
  .canvas-wrap {
    overflow: auto;
    max-height: calc(100vh - 210px);
    border-radius: 8px;
  }
  .canvas {
    position: relative;
  }
  .canvas :global(.thumb) {
    position: absolute;
    inset: 0;
    border-radius: 0;
    border: 0;
  }
  .layer {
    position: absolute;
    inset: 0;
    outline: none;
    touch-action: none;
    user-select: none;
  }
  .inner {
    position: absolute;
    left: 0;
    top: 0;
    width: 1920px;
    height: 1080px;
    transform-origin: 0 0;
  }
  .grid {
    position: absolute;
    inset: 0;
    pointer-events: none;
    background-image:
      linear-gradient(to right, rgb(255 255 255 / 0.06) 1px, transparent 1px),
      linear-gradient(to bottom, rgb(255 255 255 / 0.06) 1px, transparent 1px);
    background-size: 8px 8px;
  }
  .grid.coarse {
    background-size: 40px 40px;
  }
  .box {
    position: absolute;
    box-sizing: border-box;
    outline: calc(1px / var(--s)) dashed color-mix(in srgb, var(--c) 70%, transparent);
    cursor: move;
  }
  .box:hover {
    outline-style: solid;
    background: color-mix(in srgb, var(--c) 8%, transparent);
  }
  .box.sel {
    outline: calc(2px / var(--s)) solid var(--accent);
    background: color-mix(in srgb, var(--accent) 10%, transparent);
  }
  .box.locked {
    cursor: default;
    outline-style: dotted;
  }
  .box.ghost {
    opacity: 0.6;
  }
  .box.err {
    outline: calc(3px / var(--s)) solid var(--bad, #f83800);
  }
  .tag {
    position: absolute;
    left: 0;
    top: 0;
    transform-origin: 0 0;
    transform: scale(calc(1 / var(--s)));
    font: 600 11px/1.3 system-ui, sans-serif;
    white-space: nowrap;
    padding: 1px 5px;
    color: #000;
    background: var(--c);
    opacity: 0.85;
    pointer-events: none;
  }
  .box:not(.sel):not(:hover):not(.err) .tag {
    display: none;
  }
  .handle {
    --hs: calc(10px / var(--s));
    position: absolute;
    width: var(--hs);
    height: var(--hs);
    background: var(--accent);
    border: calc(1px / var(--s)) solid #000;
    box-sizing: border-box;
  }
  .handle.nw { left: calc(var(--hs) / -2); top: calc(var(--hs) / -2); cursor: nwse-resize; }
  .handle.n { left: calc(50% - var(--hs) / 2); top: calc(var(--hs) / -2); cursor: ns-resize; }
  .handle.ne { right: calc(var(--hs) / -2); top: calc(var(--hs) / -2); cursor: nesw-resize; }
  .handle.e { right: calc(var(--hs) / -2); top: calc(50% - var(--hs) / 2); cursor: ew-resize; }
  .handle.se { right: calc(var(--hs) / -2); bottom: calc(var(--hs) / -2); cursor: nwse-resize; }
  .handle.s { left: calc(50% - var(--hs) / 2); bottom: calc(var(--hs) / -2); cursor: ns-resize; }
  .handle.sw { left: calc(var(--hs) / -2); bottom: calc(var(--hs) / -2); cursor: nesw-resize; }
  .handle.w { left: calc(var(--hs) / -2); top: calc(50% - var(--hs) / 2); cursor: ew-resize; }
  .guide {
    position: absolute;
    background: #ff3df0;
    pointer-events: none;
  }
  .guide.x {
    width: calc(1px / var(--s));
    height: 1080px;
  }
  .guide.y {
    height: calc(1px / var(--s));
    width: 1920px;
  }
  .marquee {
    position: absolute;
    border: calc(1px / var(--s)) solid var(--accent);
    background: color-mix(in srgb, var(--accent) 12%, transparent);
    pointer-events: none;
  }
  .errors ul {
    margin: 6px 0 0;
    padding-left: 18px;
  }
  .link {
    background: none;
    border: 0;
    padding: 0;
    color: var(--accent);
    cursor: pointer;
    text-decoration: underline;
  }
  .geom {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 6px;
  }
  .geom input {
    min-width: 0;
    width: 100%;
  }
  .color {
    gap: 8px;
    align-items: center;
  }
  .color input {
    width: 34px;
    height: 26px;
    padding: 0;
  }
  .layers {
    list-style: none;
    margin: 0;
    padding: 0;
    display: grid;
    gap: 2px;
    max-height: 40vh;
    overflow: hidden auto;
  }
  .layers li {
    display: flex;
    gap: 4px;
    align-items: center;
    border-radius: 6px;
  }
  .layers li.on {
    background: color-mix(in srgb, var(--accent) 18%, transparent);
  }
  .layers li.err .layer-name {
    color: var(--bad, #f83800);
  }
  .layer-name {
    flex: 1;
    min-width: 0;
    text-align: left;
    border: 0;
    background: none;
    padding: 4px 6px;
    font-size: 13px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .dot {
    display: inline-block;
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--c);
    margin-right: 6px;
  }
  .layers .icon {
    min-width: 28px;
    padding: 2px 4px;
    border: 0;
    background: none;
  }
  .sub {
    font-size: 16px;
  }
  .starts {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
    gap: 12px;
  }
  .start {
    display: grid;
    gap: 6px;
    padding: 8px;
    text-align: left;
    align-content: start;
  }
  .blank {
    aspect-ratio: 16 / 9;
    display: grid;
    place-items: center;
    border: 1px dashed var(--line);
    border-radius: 8px;
    font-size: 22px;
    color: var(--muted);
  }
  @media (max-width: 1300px) {
    .builder {
      grid-template-columns: 1fr;
    }
    .side {
      max-height: none;
    }
  }
</style>
