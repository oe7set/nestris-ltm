// Remote station configuration (services/station_config.py, nestris-core
// docs/STATION.md "Remote configuration"): the fields the admin form offers
// and helpers for the nested value tables.

export interface CaptureDevice {
  path: string;
  formats: { format: string; sizes: string[] }[];
}

export interface ConfigReport {
  station: string | null;
  version: string | null;
  rev: number | null;
  state: "none" | "applied" | "pending" | "restarting" | "rejected" | string;
  error: string | null;
  values: Values;
  effective: Values;
  locked: string[];
  allowed: string[];
  devices: { capture: CaptureDevice[]; serial: string[] } | null;
  ts: string | null;
}

export interface ConfigStation {
  id: string;
  name: string | null;
  known: boolean;
  online: boolean;
  managed: boolean;
  overrides: Values | null;
  updated_by: string | null;
  updated_at: string | null;
  desired: Values | null;
  desired_rev: number | null;
  report: ConfigReport | null;
  in_sync: boolean;
}

export interface ConfigOverview {
  template: Values | null;
  allowed: string[];
  stations: ConfigStation[];
}

export type Values = { [key: string]: unknown };

export type FieldKind = "int" | "float" | "bool" | "text" | "select";

export interface Field {
  key: string;
  kind: FieldKind;
  options?: string[];
  min?: number;
  max?: number;
  step?: number;
}

export interface Group {
  id: string;
  fields: Field[];
}

/** The form; labels and help texts are `sconf.f.<key>` / `sconf.h.<key>`. */
export const GROUPS: Group[] = [
  {
    id: "capture",
    fields: [
      { key: "capture.device", kind: "text" },
      { key: "capture.input_format", kind: "text" },
      { key: "capture.width", kind: "int", min: 0, max: 4096 },
      { key: "capture.height", kind: "int", min: 0, max: 4096 },
      { key: "capture.fps", kind: "float", min: 0, max: 240, step: 0.01 },
      { key: "capture.scale_width", kind: "int", min: 64, max: 4096 },
      { key: "capture.scale_height", kind: "int", min: 64, max: 4096 },
      { key: "capture.lowres", kind: "select", options: ["0", "1", "2", "3"] },
      { key: "capture.stall_timeout_s", kind: "float", min: 1, max: 120, step: 0.5 },
    ],
  },
  {
    id: "recognition",
    fields: [
      { key: "engine.region", kind: "select", options: ["PAL", "NTSC"] },
      { key: "engine.calibration.acquire_downscale_width", kind: "int", min: 0, max: 4096 },
    ],
  },
  {
    id: "session",
    fields: [
      { key: "session.min_game_frames", kind: "int", min: 1, max: 100000 },
      { key: "session.end_confirm_frames", kind: "int", min: 1, max: 10000 },
      { key: "session.signal_lost_end_s", kind: "float", min: 1, max: 3600, step: 1 },
    ],
  },
  {
    id: "live",
    fields: [
      { key: "mqtt.live_max_hz", kind: "float", min: 1, max: 120, step: 1 },
      { key: "mqtt.live_playfield", kind: "bool" },
      { key: "mqtt.status_interval_s", kind: "float", min: 1, max: 300, step: 1 },
    ],
  },
  {
    id: "recording",
    fields: [
      { key: "recording.enabled", kind: "bool" },
      { key: "recording.keep_days", kind: "int", min: 0, max: 3650 },
      { key: "recording.max_gb", kind: "float", min: 0, max: 10000, step: 0.5 },
    ],
  },
  {
    id: "station",
    fields: [
      { key: "station.name", kind: "text" },
      { key: "rfid.enabled", kind: "bool" },
      { key: "rfid.port", kind: "text" },
      { key: "log.level", kind: "select", options: ["error", "warn", "info", "debug"] },
    ],
  },
];

export const FORM_KEYS = new Set(GROUPS.flatMap((g) => g.fields.map((f) => f.key)));

export function getPath(values: Values | null | undefined, key: string): unknown {
  let node: unknown = values;
  for (const part of key.split(".")) {
    if (node === null || typeof node !== "object" || !(part in (node as Values))) return undefined;
    node = (node as Values)[part];
  }
  return node;
}

/** A copy of `values` with `key` set (`undefined` removes it, empty tables go too). */
export function setPath(values: Values, key: string, value: unknown): Values {
  const parts = key.split(".");
  const out: Values = structuredClone(values);
  const walk = (node: Values, i: number): void => {
    const part = parts[i]!;
    if (i === parts.length - 1) {
      if (value === undefined) delete node[part];
      else node[part] = value;
      return;
    }
    const child = node[part];
    const next: Values = child && typeof child === "object" ? (child as Values) : {};
    node[part] = next;
    walk(next, i + 1);
    if (Object.keys(next).length === 0) delete node[part];
  };
  walk(out, 0);
  return out;
}

/** Dotted paths of every leaf. */
export function leafPaths(values: Values | null | undefined, prefix = ""): string[] {
  if (!values) return [];
  return Object.entries(values).flatMap(([k, v]) => {
    const here = prefix ? `${prefix}.${k}` : k;
    return v && typeof v === "object" && !Array.isArray(v) && Object.keys(v as Values).length
      ? leafPaths(v as Values, here)
      : [here];
  });
}

/** Parse a form input into the field's type; `undefined` = no value. */
export function parseInput(field: Field, raw: string): unknown {
  const text = raw.trim();
  if (text === "") return undefined;
  switch (field.kind) {
    case "int": {
      const n = Number(text);
      return Number.isInteger(n) ? n : undefined;
    }
    case "float": {
      const n = Number(text.replace(",", "."));
      return Number.isFinite(n) ? n : undefined;
    }
    case "bool":
      return text === "true" ? true : text === "false" ? false : undefined;
    case "select":
      return field.key === "capture.lowres" ? Number(text) : text;
    default:
      return text;
  }
}

export function display(value: unknown): string {
  if (value === undefined || value === null) return "";
  return typeof value === "object" ? JSON.stringify(value) : String(value);
}

/** Where a station's value comes from. */
export type Source = "override" | "template" | "local" | "locked";

export function sourceOf(
  key: string,
  overrides: Values | null | undefined,
  template: Values | null | undefined,
  locked: string[] | undefined,
): Source {
  if (locked?.includes(key)) return "locked";
  if (getPath(overrides, key) !== undefined) return "override";
  if (getPath(template, key) !== undefined) return "template";
  return "local";
}
