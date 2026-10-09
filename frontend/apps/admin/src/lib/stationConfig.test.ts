import { describe, expect, it } from "vitest";
import { GROUPS, getPath, leafPaths, parseInput, setPath, sourceOf, type Field } from "./stationConfig";

const field = (key: string): Field => GROUPS.flatMap((g) => g.fields).find((f) => f.key === key)!;

describe("value tables", () => {
  it("sets and removes nested keys without touching the input", () => {
    const base = { capture: { fps: 50 } };
    const set = setPath(base, "capture.scale_width", 480);
    expect(set).toEqual({ capture: { fps: 50, scale_width: 480 } });
    expect(base).toEqual({ capture: { fps: 50 } });
    expect(setPath(set, "capture.fps", undefined)).toEqual({ capture: { scale_width: 480 } });
    // Removing the last key drops the empty table.
    expect(setPath({ log: { level: "info" } }, "log.level", undefined)).toEqual({});
    expect(setPath({}, "engine.calibration.acquire_downscale_width", 320)).toEqual({
      engine: { calibration: { acquire_downscale_width: 320 } },
    });
  });

  it("reads paths and lists leaves", () => {
    const v = { capture: { fps: 50, lowres: 0 }, mqtt: { live_playfield: false } };
    expect(getPath(v, "capture.lowres")).toBe(0);
    expect(getPath(v, "mqtt.live_playfield")).toBe(false);
    expect(getPath(v, "capture.nope")).toBeUndefined();
    expect(leafPaths(v)).toEqual(["capture.fps", "capture.lowres", "mqtt.live_playfield"]);
  });
});

describe("form inputs", () => {
  it("parses by field kind", () => {
    expect(parseInput(field("capture.fps"), "50,5")).toBe(50.5);
    expect(parseInput(field("capture.scale_width"), "480")).toBe(480);
    expect(parseInput(field("capture.scale_width"), "48.5")).toBeUndefined();
    expect(parseInput(field("capture.lowres"), "1")).toBe(1);
    expect(parseInput(field("mqtt.live_playfield"), "false")).toBe(false);
    expect(parseInput(field("engine.region"), "PAL")).toBe("PAL");
    expect(parseInput(field("station.name"), "  ")).toBeUndefined();
  });

  it("names the source of a value", () => {
    const template = { capture: { fps: 50 } };
    const overrides = { capture: { lowres: 1 } };
    expect(sourceOf("capture.lowres", overrides, template, [])).toBe("override");
    expect(sourceOf("capture.fps", overrides, template, [])).toBe("template");
    expect(sourceOf("capture.device", overrides, template, [])).toBe("local");
    expect(sourceOf("capture.fps", overrides, template, ["capture.fps"])).toBe("locked");
  });
});
