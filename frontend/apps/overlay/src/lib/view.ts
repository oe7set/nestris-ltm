// Merge the derived slot state with the latest 60 Hz frame of that slot.

import type { Frame, SlotState } from "./types";

export interface SlotView extends SlotState {
  frame: Frame | null;
  next_piece: string | null;
  paused: boolean;
}

export function slotView(slot: SlotState, frame: Frame | undefined): SlotView {
  const f = frame ?? null;
  const live = slot.status === "playing" && f !== null;
  return {
    ...slot,
    // While playing, the frame is newer than the (10 Hz) state.
    score: live && f.score !== null ? f.score : slot.score,
    lines: live && f.lines !== null ? f.lines : slot.lines,
    level: live && f.level !== null ? f.level : slot.level,
    tetris_rate: f?.tetris_rate ?? slot.tetris_rate,
    burn: f?.burn ?? slot.burn,
    drought: f?.drought ?? slot.drought,
    max_drought: f?.max_drought ?? slot.max_drought,
    frame: f,
    next_piece: slot.status === "playing" ? (f?.next_piece ?? null) : null,
    paused: f?.game_state === "paused",
  };
}

/** Lines gained between two frames; 4 means a tetris. */
export function clearedLines(prev: number | null | undefined, next: number | null | undefined): number {
  if (prev === null || prev === undefined || next === null || next === undefined) return 0;
  const d = next - prev;
  return d > 0 && d <= 4 ? d : 0;
}
