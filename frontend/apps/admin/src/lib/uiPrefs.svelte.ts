// Small layout choices of the admin UI, kept per browser (localStorage).
// Losing them (private window, blocked storage) only resets the layout.

const KEY = "nltm.ui";

/** Scene studio, resizing: keep the aspect ratio by element type, always or never. */
export type RatioMode = "auto" | "keep" | "free";
const RATIO_MODES: readonly RatioMode[] = ["auto", "keep", "free"];

interface Stored {
  tournamentHelp: boolean;
  tournamentFocus: boolean;
  studioFocus: boolean;
  alertSound: boolean;
  studioRatio: RatioMode;
  studioSnap: boolean;
}

export class UiPrefs {
  /** Turnier: the explanation above the bracket is open. */
  tournamentHelp = $state(false);
  /** Turnier: focus mode (bracket only, admin sidebar hidden). */
  tournamentFocus = $state(false);
  /** Scene studio: the editor gets the whole window (admin sidebar hidden). */
  studioFocus = $state(false);
  /** A short beep when a new problem appears (bell). */
  alertSound = $state(false);
  /** Scene studio: aspect ratio while resizing (Shift inverts it). */
  studioRatio = $state<RatioMode>("auto");
  /** Scene studio: snap to elements, stage and guide lines (Alt: never). */
  studioSnap = $state(true);

  constructor() {
    try {
      const raw = globalThis.localStorage?.getItem(KEY);
      if (!raw) return;
      const s = JSON.parse(raw) as Partial<Stored>;
      this.tournamentHelp = s.tournamentHelp === true;
      this.tournamentFocus = s.tournamentFocus === true;
      this.studioFocus = s.studioFocus === true;
      this.alertSound = s.alertSound === true;
      this.studioRatio = RATIO_MODES.includes(s.studioRatio as RatioMode) ? (s.studioRatio as RatioMode) : "auto";
      this.studioSnap = s.studioSnap !== false;
    } catch {
      // nothing stored or unreadable: defaults
    }
  }

  save(): void {
    try {
      const data: Stored = {
        tournamentHelp: this.tournamentHelp,
        tournamentFocus: this.tournamentFocus,
        studioFocus: this.studioFocus,
        alertSound: this.alertSound,
        studioRatio: this.studioRatio,
        studioSnap: this.studioSnap,
      };
      globalThis.localStorage?.setItem(KEY, JSON.stringify(data));
    } catch {
      // storage blocked: the choice lasts for this visit only
    }
  }

  toggle(key: "tournamentHelp" | "tournamentFocus" | "studioFocus" | "alertSound" | "studioSnap"): void {
    this[key] = !this[key];
    this.save();
  }

  setRatio(mode: RatioMode): void {
    this.studioRatio = mode;
    this.save();
  }
}

export const uiPrefs = new UiPrefs();
