// Live station state over the /ws/live WebSocket, with automatic reconnect.

export interface LiveFrame {
  game_id: string | null;
  game_state: string;
  score: number | null;
  lines: number | null;
  level: number | null;
  next_piece: string | null;
  tetris_rate: number | null;
  ts: string;
}

export interface StationSnapshot {
  id: string;
  name: string | null;
  online: boolean;
  stale: boolean;
  status: Record<string, unknown> | null;
  card: { uid: string; name: string | null } | null;
  card_present: boolean;
  player_nickname: string | null;
  live: LiveFrame | null;
  messages: number;
  last_message_at: string | null;
}

export interface GameEvent {
  station: string;
  kind: string;
  data: Record<string, unknown>;
  at: Date;
}

type Message =
  | { type: "snapshot"; stations: StationSnapshot[] }
  | { type: "station"; station: string; data: StationSnapshot }
  | { type: "station_removed"; station: string }
  | { type: "live"; station: string; data: LiveFrame }
  | { type: "game_event"; station: string; kind: string; data: Record<string, unknown> }
  | { type: "pong" };

class LiveConnection {
  stations = $state<Record<string, StationSnapshot>>({});
  events = $state<GameEvent[]>([]);
  connected = $state(false);

  #socket: WebSocket | null = null;
  #retry = 1000;
  #users = 0;
  #timer: ReturnType<typeof setTimeout> | null = null;
  #ping: ReturnType<typeof setInterval> | null = null;

  /** Reference-counted: the socket stays open while any page uses it. */
  acquire(): () => void {
    this.#users += 1;
    if (this.#users === 1) this.#open();
    return () => {
      this.#users -= 1;
      if (this.#users === 0) this.#close();
    };
  }

  #open(): void {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const socket = new WebSocket(`${proto}://${location.host}/ws/live`);
    this.#socket = socket;
    socket.onopen = () => {
      this.connected = true;
      this.#retry = 1000;
      this.#ping = setInterval(() => socket.send(JSON.stringify({ type: "ping" })), 25000);
    };
    socket.onmessage = (event) => this.#handle(JSON.parse(event.data as string) as Message);
    socket.onclose = () => {
      this.connected = false;
      if (this.#ping) clearInterval(this.#ping);
      if (this.#socket === socket && this.#users > 0) {
        this.#timer = setTimeout(() => this.#open(), this.#retry);
        this.#retry = Math.min(this.#retry * 2, 15000);
      }
    };
  }

  #close(): void {
    if (this.#timer) clearTimeout(this.#timer);
    if (this.#ping) clearInterval(this.#ping);
    const socket = this.#socket;
    this.#socket = null;
    socket?.close();
  }

  #handle(msg: Message): void {
    switch (msg.type) {
      case "snapshot":
        this.stations = Object.fromEntries(msg.stations.map((s) => [s.id, s]));
        break;
      case "station":
        this.stations[msg.station] = msg.data;
        break;
      case "station_removed":
        delete this.stations[msg.station];
        break;
      case "live": {
        const station = this.stations[msg.station];
        if (station) {
          station.live = msg.data;
          station.online = true;
        }
        break;
      }
      case "game_event":
        this.events = [
          { station: msg.station, kind: msg.kind, data: msg.data, at: new Date() },
          ...this.events,
        ].slice(0, 50);
        break;
    }
  }
}

export const live = new LiveConnection();
