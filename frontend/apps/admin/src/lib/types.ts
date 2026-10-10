// Shapes of the REST API responses (see src/nestris_ltm/api/routes_*.py).

export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
  event: { id: number; name: string } | null;
}

export interface Player {
  id: number;
  nickname: string;
  first_name: string | null;
  last_name: string | null;
  birth_date: string | null;
  email: string | null;
  phone: string | null;
  street: string | null;
  postal_code: string | null;
  city: string | null;
  country: string | null;
  notes: string | null;
  auto_created: boolean;
  deleted_at: string | null;
  created_at: string;
  updated_at: string;
  games_total?: number;
  best_score?: number | null;
  best_score_event?: number | null;
  hide_everywhere?: boolean;
  hide_from_bracket?: boolean;
}

export interface Card {
  uid: string;
  card_name: string | null;
  first_seen_at: string;
  last_seen_at: string;
}

export interface PlayerDetail extends Player {
  cards: Card[];
  games_event: number;
  event: { id: number; name: string } | null;
}

export interface Game {
  id: number;
  external_id: string | null;
  station_id: string | null;
  player_id: number | null;
  player_nickname: string | null;
  card_name: string | null;
  card_uid: string | null;
  status: "live" | "finished" | "abandoned";
  source: "station" | "manual" | "ngf_import" | "self_reported";
  started_at: string;
  ended_at: string | null;
  duration_s: number | null;
  active_seconds: number | null;
  end_reason: string | null;
  start_level: number | null;
  end_level: number | null;
  score: number | null;
  lines: number | null;
  clears_single: number | null;
  clears_double: number | null;
  clears_triple: number | null;
  clears_tetris: number | null;
  tetris_rate: number | null;
  burn: number | null;
  max_drought: number | null;
  pieces: number | null;
  pps: number | null;
  cheated: number;
  cheat_points: number;
  valid: boolean | null;
  is_edited: boolean;
  notes: string | null;
  hidden: boolean;
  flagged: boolean;
  /** Current values of a running game (from the live feed). */
  live?: { score: number | null; lines: number | null; level: number | null } | null;
}

export interface Cheat {
  id: number;
  ts: string;
  count: number;
  points: number;
  score_before: number;
  score_after: number;
}

export interface ValidationIssue {
  code: string;
  severity: string;
  detail: string;
}

export interface GameDetail extends Game {
  validation: { issues: ValidationIssue[]; metrics: Record<string, unknown> } | null;
  cheats: Cheat[];
  frame_count: number;
  recording: { size_bytes: number; received_at: string } | null;
  hidden_in: { event_id: number; event: string; reason: string | null }[];
}

export interface EventInfo {
  id: number;
  name: string;
  slug: string;
  starts_at: string;
  ends_at: string | null;
  is_active: boolean;
  games: number;
  players: number;
  hidden_stations: string[];
}

export interface StationRow {
  id: string;
  name: string | null;
  last_seen_at?: string | null;
  games: number;
  live: import("./live.svelte").StationSnapshot | null | undefined;
}

export interface AuditEntry {
  id: number;
  ts: string;
  actor: string;
  action: string;
  entity: string;
  entity_id: string;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
}

export interface Me {
  authenticated: boolean;
  kind: string | null;
  name: string | null;
  needs_setup: boolean;
  can_setup: boolean;
}

export interface PageInfo {
  id: string;
  group: "admin" | "display" | "overlay" | "diagnostics" | "api" | "tray";
  path: string;
  title_de: string;
  title_en: string;
  description_de: string;
  description_en: string;
  public: boolean;
  status: "available" | "planned";
  phase: number | null;
}

export interface Diagnostics {
  version: string;
  uptime_s: number;
  database: {
    ready: boolean;
    state: string;
    host: string;
    name: string;
    error: string | null;
    attempts: number;
    next_retry_at: string | null;
  };
  mqtt: {
    enabled: boolean;
    broker: string;
    topic_prefix: string;
    connected: boolean;
    messages: number;
    last_error: string | null;
  };
  ingest: {
    events_stored: number;
    events_failed: number;
    last_event_error: string | null;
    spool_pending: number;
    spool_failed: number;
    frames_written: number;
    frames_pending: number;
    frames_dropped: number;
    parse_errors: number;
  };
  websocket_clients: number;
}

export interface LogEntry {
  id: number;
  ts: string;
  level: string;
  logger: string;
  message: string;
}

export interface DbStatus {
  ready: boolean;
  state: string;
  detail: string | null;
  extra: { db_revision?: string | null; app_head?: string | null; migrated_by?: string | null };
  attempts: number;
  next_retry_at: string | null;
  ready_since: string | null;
  connection: { host: string; port: number; user: string; name: string; has_password: boolean };
  app_head: string | null;
  config_file: string;
  env_overrides: string[];
  aside_databases: string[];
  can_reconfigure: boolean;
  can_restore: boolean;
}

export interface DbTestResult {
  ok: boolean;
  state: string;
  detail: string;
  database_exists?: boolean;
}

export interface DbBackup {
  file: string;
  size: number;
  created_at: string;
  kind: "update" | "manual" | "other";
  before_version: string | null;
  revision: string | null;
  compatible: boolean | null;
}
