// Replay clock over decoded NGF frames: play/pause, speed, seek, loop.

import type { NgfFrame } from "./ngf";

export class Timeline {
  readonly frames: NgfFrame[];
  readonly start: number;
  readonly duration: number; // ms
  speed = 1;
  loop = false;
  #position = 0; // ms since the first frame
  #playing = false;
  #lastTick: number | null = null;

  constructor(frames: NgfFrame[]) {
    this.frames = frames;
    this.start = frames[0]?.ctimeMs ?? 0;
    this.duration = frames.length ? frames[frames.length - 1]!.ctimeMs - this.start : 0;
  }

  get position(): number {
    return this.#position;
  }

  get playing(): boolean {
    return this.#playing;
  }

  get ended(): boolean {
    return this.#position >= this.duration;
  }

  play(now: number): void {
    if (this.ended) this.#position = 0;
    this.#playing = true;
    this.#lastTick = now;
  }

  pause(): void {
    this.#playing = false;
    this.#lastTick = null;
  }

  seek(ms: number): void {
    this.#position = Math.min(Math.max(ms, 0), this.duration);
  }

  /** Advance the clock to ``now`` (performance.now()); returns the frame index. */
  tick(now: number): number {
    if (this.#playing && this.#lastTick !== null) {
      this.#position += (now - this.#lastTick) * this.speed;
      if (this.#position >= this.duration) {
        if (this.loop && this.duration > 0) this.#position %= this.duration;
        else {
          this.#position = this.duration;
          this.pause();
        }
      }
    }
    if (this.#playing) this.#lastTick = now;
    return this.index();
  }

  /** Index of the last frame at or before the current position (binary search). */
  index(): number {
    const target = this.start + this.#position;
    let lo = 0;
    let hi = this.frames.length - 1;
    if (hi < 0) return -1;
    while (lo < hi) {
      const mid = (lo + hi + 1) >> 1;
      if (this.frames[mid]!.ctimeMs <= target) lo = mid;
      else hi = mid - 1;
    }
    return lo;
  }

  /** Jump by ``n`` frames (frame stepping while paused). */
  step(n: number): void {
    const i = Math.min(Math.max(this.index() + n, 0), this.frames.length - 1);
    this.#position = this.frames[i]!.ctimeMs - this.start;
  }
}
