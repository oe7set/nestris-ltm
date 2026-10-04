// Live connection to one scene: derived state, 60 Hz frames and score history.

import type { Frame, History, Message, RoundGroup, SceneState } from "./types";

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
  // Per round group (every head-to-head pair plays its own rounds).
  #roundStart: Record<number, number> = {};
  #rounds: Record<number, number> = {};

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
        for (const g of groupsOf(msg.data.state)) {
          this.#rounds[g.group] = g.round;
          // Continue the server's time axis.
          const last = Math.max(0, ...g.slots.flatMap((s) => (msg.data.history[String(s)] ?? []).map((p) => p[0])));
          this.#roundStart[g.group] = performance.now() - last;
        }
        break;
      }
      case "state":
        for (const g of groupsOf(msg.data)) {
          if (this.#rounds[g.group] !== undefined && this.#rounds[g.group] !== g.round) {
            // A new round of this group: only its slots start over.
            for (const s of g.slots) {
              delete this.history[String(s)];
              delete this.frames[s];
            }
            this.#roundStart[g.group] = performance.now();
          }
          this.#rounds[g.group] = g.round;
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
    const group = this.state?.slots[slot]?.group ?? 0;
    const start = this.#roundStart[group] ?? (this.#roundStart[group] = performance.now());
    const t = Math.round(performance.now() - start);
    const key = String(slot);
    const series = this.history[key] ?? (this.history[key] = []);
    const last = series[series.length - 1];
    if (!last || t - last[0] >= HISTORY_INTERVAL_MS) series.push([t, score]);
    else if (last[1] !== score) series[series.length - 1] = [last[0], score];
  }
}

/** Round groups of a state (older servers: one group with every slot). */
export function groupsOf(state: SceneState): RoundGroup[] {
  return state.groups ?? [{ group: 0, slots: state.slots.map((s) => s.slot), round: state.round, complete: state.complete }];
}

export const scene = new SceneConnection();
