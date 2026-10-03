// Live connection to one scene: derived state, 60 Hz frames and score history.

import type { Frame, History, Message, SceneState } from "./types";

export const HISTORY_INTERVAL_MS = 1000;

export function sceneSlug(loc: Location = location): string | null {
  const fromPath = /^\/o\/([^/]+)/.exec(loc.pathname)?.[1];
  return fromPath ? decodeURIComponent(fromPath) : new URLSearchParams(loc.search).get("scene");
}

class SceneConnection {
  state = $state<SceneState | null>(null);
  frames = $state<Record<number, Frame>>({});
  history = $state<History>({});
  connected = $state(false);
  missing = $state(false);

  #slug = "";
  #socket: WebSocket | null = null;
  #retry = 1000;
  #roundStart = performance.now();
  #round = 0;

  start(slug: string): void {
    this.#slug = slug;
    this.#open();
  }

  #open(): void {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const socket = new WebSocket(`${proto}://${location.host}/ws/scene/${encodeURIComponent(this.#slug)}`);
    this.#socket = socket;
    let ping: ReturnType<typeof setInterval> | undefined;
    socket.onopen = () => {
      this.connected = true;
      this.missing = false;
      this.#retry = 1000;
      ping = setInterval(() => socket.send(JSON.stringify({ type: "ping" })), 25000);
    };
    socket.onmessage = (e) => this.#handle(JSON.parse(e.data as string) as Message);
    socket.onclose = (e) => {
      clearInterval(ping);
      this.connected = false;
      if (e.code === 4404) this.missing = true;
      // Keep retrying: OBS keeps the source loaded while the host restarts.
      setTimeout(() => this.#open(), this.#retry);
      this.#retry = Math.min(this.#retry * 2, 10000);
    };
  }

  #handle(msg: Message): void {
    switch (msg.type) {
      case "init": {
        this.state = msg.data.state;
        this.frames = Object.fromEntries(
          Object.entries(msg.data.frames).map(([k, v]) => [Number(k), v]),
        );
        this.history = msg.data.history;
        this.#round = msg.data.state.round;
        // Continue the server's time axis.
        const last = Math.max(0, ...Object.values(msg.data.history).flat().map((p) => p[0]));
        this.#roundStart = performance.now() - last;
        break;
      }
      case "state":
        if (msg.data.round !== this.#round) {
          this.#round = msg.data.round;
          this.history = {};
          this.frames = {};
          this.#roundStart = performance.now();
        }
        this.state = msg.data;
        break;
      case "frame":
        this.frames[msg.slot] = msg.data;
        this.#sample(msg.slot, msg.data.score);
        break;
      case "scene_removed":
        this.state = null;
        this.missing = true;
        break;
    }
  }

  #sample(slot: number, score: number | null): void {
    if (score === null) return;
    const t = Math.round(performance.now() - this.#roundStart);
    const key = String(slot);
    const series = this.history[key] ?? (this.history[key] = []);
    const last = series[series.length - 1];
    if (!last || t - last[0] >= HISTORY_INTERVAL_MS) series.push([t, score]);
    else if (last[1] !== score) series[series.length - 1] = [last[0], score];
  }
}

export const scene = new SceneConnection();
