// Number formatting and texts for the overlays.

import { look } from "./look.svelte";

export type Lang = "de" | "en";

/** Thousands grouped by a space, or by commas in the NES style ("181,290"). */
export function fmt(n: number | null | undefined): string {
  if (n === null || n === undefined) return "–";
  const text = Math.round(n).toLocaleString("en-US");
  return look.nes ? text : text.replace(/,/g, " ");
}

export function signed(n: number): string {
  return (n > 0 ? "+" : n < 0 ? "−" : "±") + fmt(Math.abs(n));
}

export function pct(n: number | null | undefined): string {
  if (n === null || n === undefined) return "–";
  return `${Math.round(n * 100)}%`;
}

export function tetrises(n: number): string {
  return n.toFixed(1);
}

const TEXT = {
  de: {
    score: "PUNKTE",
    start_level: "START",
    pieces: "STEINE",
    gap: "ABSTAND",
    lines: "LINES",
    level: "LEVEL",
    next: "NÄCHSTER",
    trt: "TETRIS-RATE",
    burn: "BURN",
    drought: "DROUGHT",
    pace: "PACE",
    lead: "VORSPRUNG",
    diff: "DIFFERENZ",
    behind: "RÜCKSTAND",
    tetris: "TETRIS",
    needs: "braucht",
    to_win: "zum Sieg",
    to_advance: "zum Weiterkommen",
    waiting: "WARTET",
    finished: "FERTIG",
    paused: "PAUSE",
    advanced: "WEITER",
    eliminated: "RAUS",
    winner: "SIEGER",
    round: "RUNDE",
    quali: "QUALI",
    no_scene: "Szene nicht gefunden",
    offline: "keine Verbindung",
    rank: "PLATZ",
    even: "GLEICHSTAND",
    mode_top2_advance: "TOP 2 KOMMEN WEITER",
    mode_worst_out: "SCHLECHTESTER SCHEIDET AUS",
    mode_winner_only: "NUR DER SIEGER KOMMT WEITER",
    mode_none: "",
  },
  en: {
    score: "SCORE",
    start_level: "START",
    pieces: "PIECES",
    gap: "GAP",
    lines: "LINES",
    level: "LEVEL",
    next: "NEXT",
    trt: "TETRIS RATE",
    burn: "BURN",
    drought: "DROUGHT",
    pace: "PACE",
    lead: "LEAD",
    diff: "DIFFERENCE",
    behind: "BEHIND",
    tetris: "TETRIS",
    needs: "needs",
    to_win: "to win",
    to_advance: "to advance",
    waiting: "WAITING",
    finished: "FINISHED",
    paused: "PAUSE",
    advanced: "ADVANCES",
    eliminated: "OUT",
    winner: "WINNER",
    round: "ROUND",
    quali: "QUALIFYING",
    no_scene: "Scene not found",
    offline: "no connection",
    rank: "RANK",
    even: "EVEN",
    mode_top2_advance: "TOP 2 ADVANCE",
    mode_worst_out: "LAST PLACE IS OUT",
    mode_winner_only: "WINNER TAKES ALL",
    mode_none: "",
  },
} as const;

export type TextKey = keyof (typeof TEXT)["de"];

export function text(lang: Lang | undefined, key: TextKey): string {
  return TEXT[lang === "en" ? "en" : "de"][key];
}

/** "RUNDE 3", or "QUALI" for a qualifying scene (no rounds). */
export function roundLabel(lang: Lang | undefined, qualifying: boolean | undefined, round: number | string): string {
  return qualifying ? text(lang, "quali") : `${text(lang, "round")} ${round}`;
}

// The NES style uses the game's own short HUD words (as NestrisChamps does).
const NES_HUD: Partial<Record<TextKey, string>> = {
  score: "SCORE",
  start_level: "START",
  pieces: "PIECES",
  gap: "GAP",
  lines: "LINES",
  level: "LV",
  next: "NEXT",
  trt: "TRT",
  burn: "BURN",
  drought: "DRT",
  pace: "PACE",
  diff: "DIFF",
};

/** A stat label: NES HUD word in the NES style, the localized text otherwise. */
export function hud(lang: Lang | undefined, key: TextKey): string {
  return (look.nes && NES_HUD[key]) || text(lang, key);
}
