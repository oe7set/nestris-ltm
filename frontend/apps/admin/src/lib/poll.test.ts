import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const errors: unknown[] = [];
vi.mock("./toast.svelte", () => ({ toasts: { error: (e: unknown) => errors.push(e) } }));

const { ErrorOnce, poll } = await import("./poll");

describe("poll", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("repeats without overlapping and stops", async () => {
    let calls = 0;
    let release: () => void = () => {};
    const stop = poll(
      () =>
        new Promise<void>((resolve) => {
          calls += 1;
          release = resolve;
        }),
      100,
    );
    await vi.advanceTimersByTimeAsync(100);
    expect(calls).toBe(1);
    await vi.advanceTimersByTimeAsync(500); // still running: no second call
    expect(calls).toBe(1);
    release();
    await vi.advanceTimersByTimeAsync(100);
    expect(calls).toBe(2);
    stop();
    release();
    await vi.advanceTimersByTimeAsync(1000);
    expect(calls).toBe(2);
  });

  it("keeps going after a failure", async () => {
    let calls = 0;
    const stop = poll(() => {
      calls += 1;
      throw new Error("down");
    }, 50);
    await vi.advanceTimersByTimeAsync(160);
    expect(calls).toBe(3);
    stop();
  });
});

describe("ErrorOnce", () => {
  it("reports one outage once", () => {
    errors.length = 0;
    const once = new ErrorOnce();
    once.report("a");
    once.report("b");
    expect(errors).toEqual(["a"]);
    once.ok();
    once.report("c");
    expect(errors).toEqual(["a", "c"]);
  });
});
