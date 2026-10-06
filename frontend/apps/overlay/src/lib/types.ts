// Shapes of the /ws/scene/<slug> protocol (see services/scenes.py).

export interface Gap {
  points: number; // positive = behind
  tetrises: number;
  tetrises_needed: number;
}

export type SlotStatus = "empty" | "waiting" | "playing" | "finished";
export type Outcome = "advanced" | "eliminated" | "winner" | null;

export interface SlotState {
  slot: number;
  group?: number; // round group (head-to-head pair)
  round?: number; // round of that group
  station_id: string | null;
  label: string | null;
  name: string | null;
  status: SlotStatus;
  online: boolean;
  score: number | null;
  lines: number | null;
  level: number | null;
  start_level: number | null;
  tetris_rate: number | null;
  burn: number | null;
  drought: number | null;
  max_drought: number | null;
  pieces: number | null;
  pace: number | null;
  rank: number | null;
  outcome: Outcome;
  to_leader?: Gap;
  vs_partner?: Gap;
  to_advance?: Gap & { score: number };
  // Hearts of the bracket match bound to this slot's pair (if any).
  lives?: { current: number | null; max: number };
  match_result?: "won" | "lost" | null;
}

export interface PairMatch {
  pair: number;
  match_id: string;
  round_name: string;
  max_lives: number;
  bound_by: "manual" | "auto";
  winner_id: number | null;
}

export interface SceneInfo {
  slug: string;
  name: string;
  layout: string;
  mode: "none" | "top2_advance" | "worst_out" | "winner_only";
  auto_round: boolean;
  /** Qualifying: no rounds, every slot shows the current game. */
  qualifying?: boolean;
  settings: SceneSettings;
  pairs: [number, number][];
  // Own layouts: "<uuid>:<version>"; the definition is fetched when it changes.
  layout_rev?: string | null;
}

export interface SceneSettings {
  lang?: "de" | "en";
  background?: "transparent" | "dark";
  camera_frames?: boolean;
  title?: string;
  style?: "modern" | "nes";
  theme?: Partial<Record<ThemeKey, string>>;
  show?: Partial<Record<ShowKey, boolean>>;
}

// Mirrors core/scene_settings.py.
export const THEME_KEYS = ["accent", "frame", "inner", "panel", "text", "good", "bad"] as const;
export type ThemeKey = (typeof THEME_KEYS)[number];
export const SHOW_KEYS = ["header", "diff_graph", "versus", "pace", "burn", "hearts", "next"] as const;
export type ShowKey = (typeof SHOW_KEYS)[number];

export interface RoundGroup {
  group: number;
  slots: number[];
  round: number;
  complete: boolean;
}

export interface SceneState {
  groups?: RoundGroup[];
  matches?: PairMatch[];
  scene: SceneInfo;
  round: number;
  complete: boolean;
  leader: number | null;
  slots: SlotState[];
}

export interface Frame {
  game_id: string | null;
  game_state: string;
  score: number | null;
  lines: number | null;
  level: number | null;
  next_piece: string | null;
  tetris_rate: number | null;
  burn: number;
  drought: number;
  max_drought: number;
  pieces: number;
  playfield: string[] | null;
}

export type History = Record<string, [number, number][]>;

export type Message =
  | { type: "init"; data: { state: SceneState; frames: Record<string, Frame>; history: History } }
  | { type: "state"; data: SceneState }
  | { type: "frame"; slot: number; data: Frame }
  | { type: "scene_removed" }
  | { type: "pong" };
