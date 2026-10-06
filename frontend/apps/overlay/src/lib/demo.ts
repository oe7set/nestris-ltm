// Demo data for previews: a believable, animated tournament scene without any
// station. Deterministic for a given time, so thumbnails and tests are stable.

import type { Frame, History, PairMatch, SceneInfo, SceneState, SlotState } from "./types";

export const DEMO_NAMES = ["Erv", "Tom", "Lea", "Max", "Kim", "Ben", "Ida", "Ole"];
const PIECES = ["T", "J", "Z", "O", "S", "L", "I"];
const LOOP_MS = 180_000; // the demo game restarts every 3 minutes

export interface DemoInput {
  scene: SceneInfo;
  slots: number;
  /** Optional names per slot (e.g. the scene's name overrides). */
  names?: (string | null | undefined)[];
}

export interface DemoData {
  state: SceneState;
  frames: Record<number, Frame>;
  history: History;
}

/** Small deterministic PRNG (mulberry32). */
export function rng(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** Score of a demo slot at a time in the loop (monotonic within the loop). */
export function demoScore(slot: number, ms: number): number {
  const t = (ms % LOOP_MS) / 1000;
  const speed = 900 + slot * 137; // points per second, different per slot
  return Math.round(t * speed + Math.floor(t / 7) * 1200 * (slot % 2 ? 9 : 10)); // a tetris now and then
}

/** A plausible stack: random column heights with one open well, 20 rows of "0123". */
export function demoPlayfield(slot: number, ms: number): string[] {
  const step = Math.floor(ms / 2000);
  const r = rng(slot * 7919 + step);
  const well = 9 - (slot % 3);
  const heights = Array.from({ length: 10 }, (_, x) => (x === well ? 0 : 3 + Math.floor(r() * 7)));
  const rows: string[] = [];
  for (let y = 0; y < 20; y++) {
    let row = "";
    for (let x = 0; x < 10; x++) {
      const filled = 20 - y <= heights[x]!;
      row += filled ? String(1 + Math.floor(r() * 3)) : "0";
    }
    rows.push(row);
  }
  return rows;
}

function slotState(
  scene: SceneInfo,
  slot: number,
  ms: number,
  group: number,
  name: string,
  scores: number[],
  partner: number | null,
): SlotState {
  const score = scores[slot] ?? 0;
  const lines = Math.floor(score / 1600);
  const level = 18 + Math.floor(lines / 10);
  const gap = partner === null ? undefined : (scores[partner] ?? 0) - score; // > 0: behind
  return {
    slot,
    group,
    round: 1 + Math.floor(ms / LOOP_MS) % 3,
    station_id: `demo-${slot + 1}`,
    label: null,
    name,
    status: "playing",
    online: true,
    score,
    lines,
    level,
    start_level: 18,
    tetris_rate: 0.45 + (slot % 4) * 0.08,
    burn: (slot * 3) % 12,
    drought: (Math.floor(ms / 1000) + slot * 5) % 17,
    max_drought: 16,
    pieces: Math.floor(score / 300),
    pace: Math.round(score * 2.4 + 400_000 + slot * 21_000),
    rank: null,
    outcome: null,
    vs_partner:
      gap === undefined
        ? undefined
        : { points: gap, tetrises: Math.abs(gap) / (1200 * (level + 1)), tetrises_needed: Math.max(0, Math.ceil(gap / (1200 * (level + 1)))) },
    lives: partner === null ? undefined : { current: slot % 2 ? 1 : 2, max: 2 },
    match_result: null,
  };
}

/** The whole demo scene at time ``ms`` (since the preview started). */
export function demoData(input: DemoInput, ms: number): DemoData {
  const { scene } = input;
  const count = Math.max(1, Math.min(8, input.slots));
  const pairs = scene.pairs.filter(([a, b]) => a < count && b < count);
  const partnerOf = (slot: number): number | null => {
    for (const [a, b] of pairs) {
      if (slot === a) return b;
      if (slot === b) return a;
    }
    return null;
  };
  const groupOf = (slot: number): number => {
    const index = pairs.findIndex(([a, b]) => a === slot || b === slot);
    return index < 0 ? 0 : index;
  };
  const scores = Array.from({ length: count }, (_, s) => demoScore(s, ms));
  const slots = Array.from({ length: count }, (_, s) =>
    slotState(scene, s, ms, groupOf(s), input.names?.[s] || DEMO_NAMES[s % DEMO_NAMES.length]!, scores, partnerOf(s)),
  );
  // Ranks within each group, like the scene engine.
  const groups = pairs.length ? pairs.map((p) => [...p]) : [Array.from({ length: count }, (_, s) => s)];
  for (const members of groups) {
    members
      .slice()
      .sort((a, b) => scores[b]! - scores[a]! || a - b)
      .forEach((s, i) => (slots[s]!.rank = i + 1));
  }
  const matches: PairMatch[] = pairs.map((_, i) => ({
    pair: i,
    match_id: `demo_${i + 1}`,
    round_name: scene.settings.lang === "en" ? "Semifinals" : "Halbfinale",
    max_lives: 2,
    bound_by: "auto",
    winner_id: null,
  }));
  const frames: Record<number, Frame> = {};
  const history: History = {};
  const loopMs = ms % LOOP_MS;
  for (let s = 0; s < count; s++) {
    const st = slots[s]!;
    frames[s] = {
      game_id: `demo-${s}`,
      game_state: "in_game",
      score: st.score,
      lines: st.lines,
      level: st.level,
      next_piece: PIECES[(Math.floor(ms / 1500) + s) % PIECES.length]!,
      tetris_rate: st.tetris_rate,
      burn: st.burn ?? 0,
      drought: st.drought ?? 0,
      max_drought: st.max_drought ?? 0,
      pieces: st.pieces ?? 0,
      playfield: demoPlayfield(s, ms),
    };
    const series: [number, number][] = [];
    for (let t = 0; t <= loopMs; t += 1000) series.push([t, demoScore(s, t)]);
    history[String(s)] = series;
  }
  return {
    state: {
      scene,
      round: slots[0]?.round ?? 1,
      groups: groups.map((members, g) => ({ group: g, slots: members, round: slots[members[0]!]!.round ?? 1, complete: false })),
      complete: false,
      leader: slots.find((x) => x.rank === 1)?.slot ?? null,
      matches,
      slots,
    },
    frames,
    history,
  };
}
