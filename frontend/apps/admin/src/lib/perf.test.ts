import { describe, expect, it } from "vitest";
import {
  captureLevel,
  dropLevel,
  engineLevel,
  fpsLevel,
  linkLevel,
  overallLevel,
  sparkline,
  worst,
  type LinkStats,
  type StationPerf,
} from "./perf";

const perf = (p: Partial<StationPerf>): StationPerf => ({
  capture_fps: 50,
  fps: 50,
  target_fps: 50,
  drop_rate: 0,
  missing: 0,
  dropped_total: 0,
  missing_total: 0,
  engine_ms_p50: 5,
  engine_ms_p95: 8,
  frame_age_ms_p95: 10,
  live_hz: 30,
  size: "720x576",
  cpu_pct: 50,
  load1: 1,
  ...p,
});

const link = (l: Partial<LinkStats>): LinkStats => ({
  rx_hz: 30,
  received: 100,
  lost: 0,
  loss_rate: 0,
  restarts: 0,
  sequenced: true,
  frame_age_ms: 7,
  transport_ms: 3,
  clock_skew: false,
  ...l,
});

describe("perf levels", () => {
  it("rates fps against the target", () => {
    expect(fpsLevel(perf({}))).toBe("ok");
    expect(fpsLevel(perf({ fps: 45 }))).toBe("warn");
    expect(fpsLevel(perf({ fps: 30 }))).toBe("bad");
    expect(fpsLevel(perf({ target_fps: null, capture_fps: 25, fps: 25 }))).toBe("ok");
    expect(fpsLevel(null)).toBe("none");
  });

  it("flags capture gaps and drops", () => {
    expect(captureLevel(perf({ missing: 2 }))).toBe("warn");
    expect(captureLevel(perf({ capture_fps: 30 }))).toBe("bad");
    expect(dropLevel(perf({ drop_rate: 0.02 }))).toBe("warn");
    expect(dropLevel(perf({ drop_rate: 0.2 }))).toBe("bad");
  });

  it("rates the engine against the frame budget", () => {
    // 50 fps = 20 ms per frame.
    expect(engineLevel(perf({ engine_ms_p95: 13 }))).toBe("ok");
    expect(engineLevel(perf({ engine_ms_p95: 17 }))).toBe("warn");
    expect(engineLevel(perf({ engine_ms_p95: 25 }))).toBe("bad");
  });

  it("ignores links of stations without sequence numbers", () => {
    expect(linkLevel(link({ sequenced: false, loss_rate: 0.5 }))).toBe("none");
    expect(linkLevel(link({ loss_rate: 0.1 }))).toBe("bad");
  });

  it("combines to the worst level", () => {
    expect(worst("none", "ok")).toBe("ok");
    expect(worst("ok", "bad", "warn")).toBe("bad");
    expect(overallLevel(perf({}), link({}))).toBe("ok");
    expect(overallLevel(perf({ drop_rate: 0.03 }), link({}))).toBe("warn");
    expect(overallLevel(null, null)).toBe("none");
  });
});

describe("sparkline", () => {
  it("scales values into the box and skips gaps", () => {
    expect(sparkline([0, 50], 100, 10)).toBe("0.0,10.0 100.0,0.0");
    expect(sparkline([25, null, 50], 100, 10, 50)).toBe("0.0,5.0 100.0,0.0");
    expect(sparkline([1], 100, 10)).toBe("");
  });
});
