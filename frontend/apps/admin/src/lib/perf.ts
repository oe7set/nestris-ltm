// Station performance: the `perf` block of the station status (station
// 0.3.0+, nestris-core docs/STATION.md) and how `live` reaches this host
// (`link`, live/linkstats.py). Thresholds turn the numbers into a traffic light.

export interface StationPerf {
  capture_fps: number | null;
  fps: number | null;
  target_fps: number | null;
  drop_rate: number | null;
  missing: number | null;
  dropped_total: number | null;
  missing_total: number | null;
  engine_ms_p50: number | null;
  engine_ms_p95: number | null;
  frame_age_ms_p95: number | null;
  live_hz: number | null;
  size: string | null;
  cpu_pct: number | null;
  load1: number | null;
}

export interface LinkStats {
  rx_hz: number;
  received: number;
  lost: number;
  loss_rate: number;
  restarts: number;
  sequenced: boolean;
  frame_age_ms: number | null;
  transport_ms: number | null;
  clock_skew: boolean;
}

export interface PerfPoint {
  t: string;
  fps: number | null;
  capture_fps: number | null;
  target_fps: number | null;
  drop_rate: number | null;
  missing: number | null;
  engine_ms_p95: number | null;
  cpu_pct: number | null;
  rx_hz: number;
  lost: number;
}

export type Level = "ok" | "warn" | "bad" | "none";

const ORDER: Level[] = ["none", "ok", "warn", "bad"];

/** The worse of two levels (`none` = no data, never wins). */
export function worst(...levels: Level[]): Level {
  return levels.reduce((a, b) => (ORDER.indexOf(b) > ORDER.indexOf(a) ? b : a), "none");
}

/** Processed fps against the target (or what the capture delivers). */
export function fpsLevel(p: StationPerf | null | undefined): Level {
  if (!p || p.fps == null) return "none";
  const target = p.target_fps ?? p.capture_fps;
  if (!target) return "none";
  const ratio = p.fps / target;
  return ratio >= 0.95 ? "ok" : ratio >= 0.8 ? "warn" : "bad";
}

/** The capture itself: delivers the target rate, no frames missing. */
export function captureLevel(p: StationPerf | null | undefined): Level {
  if (!p || p.capture_fps == null) return "none";
  const ratioLevel: Level =
    p.target_fps && p.capture_fps < p.target_fps * 0.95
      ? p.capture_fps < p.target_fps * 0.8
        ? "bad"
        : "warn"
      : "ok";
  return worst(ratioLevel, (p.missing ?? 0) > 0 ? "warn" : "ok");
}

export function dropLevel(p: StationPerf | null | undefined): Level {
  if (!p || p.drop_rate == null) return "none";
  return p.drop_rate < 0.01 ? "ok" : p.drop_rate < 0.05 ? "warn" : "bad";
}

/** Engine p95 against the time one frame may take at the target rate. */
export function engineLevel(p: StationPerf | null | undefined): Level {
  if (!p || p.engine_ms_p95 == null) return "none";
  const rate = p.target_fps ?? p.capture_fps;
  if (!rate) return "none";
  const budget = 1000 / rate;
  return p.engine_ms_p95 < budget * 0.7 ? "ok" : p.engine_ms_p95 < budget ? "warn" : "bad";
}

export function cpuLevel(p: StationPerf | null | undefined): Level {
  if (!p || p.cpu_pct == null) return "none";
  return p.cpu_pct < 80 ? "ok" : p.cpu_pct < 95 ? "warn" : "bad";
}

export function linkLevel(l: LinkStats | null | undefined): Level {
  if (!l || !l.sequenced) return "none";
  return l.loss_rate < 0.01 ? "ok" : l.loss_rate < 0.05 ? "warn" : "bad";
}

export function overallLevel(p: StationPerf | null | undefined, l: LinkStats | null | undefined): Level {
  return worst(fpsLevel(p), captureLevel(p), dropLevel(p), engineLevel(p), cpuLevel(p), linkLevel(l));
}

export function fmt(v: number | null | undefined, digits = 1, unit = ""): string {
  return v == null ? "–" : `${v.toFixed(digits)}${unit}`;
}

export function pct(v: number | null | undefined, digits = 1): string {
  return v == null ? "–" : `${(v * 100).toFixed(digits)} %`;
}

/** SVG polyline points for a sparkline of `values` in a w×h box. */
export function sparkline(values: (number | null)[], w: number, h: number, max?: number): string {
  const nums = values.filter((v): v is number => v != null);
  if (nums.length < 2) return "";
  const top = Math.max(max ?? 0, ...nums) || 1;
  const step = w / (values.length - 1);
  return values
    .map((v, i) => (v == null ? null : `${(i * step).toFixed(1)},${(h - (v / top) * h).toFixed(1)}`))
    .filter((p) => p != null)
    .join(" ");
}
