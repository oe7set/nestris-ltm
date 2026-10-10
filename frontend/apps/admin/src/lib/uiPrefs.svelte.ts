// Small layout choices of the admin UI, kept per browser (localStorage).
// Losing them (private window, blocked storage) only resets the layout.

const KEY = "nltm.ui";

interface Stored {
  tournamentHelp: boolean;
  tournamentFocus: boolean;
  alertSound: boolean;
}

export class UiPrefs {
  /** Turnier: the explanation above the bracket is open. */
  tournamentHelp = $state(false);
  /** Turnier: focus mode (bracket only, admin sidebar hidden). */
  tournamentFocus = $state(false);
  /** A short beep when a new problem appears (bell). */
  alertSound = $state(false);

  constructor() {
    try {
      const raw = globalThis.localStorage?.getItem(KEY);
      if (!raw) return;
      const s = JSON.parse(raw) as Partial<Stored>;
      this.tournamentHelp = s.tournamentHelp === true;
      this.tournamentFocus = s.tournamentFocus === true;
      this.alertSound = s.alertSound === true;
    } catch {
      // nothing stored or unreadable: defaults
    }
  }

  save(): void {
    try {
      const data: Stored = {
        tournamentHelp: this.tournamentHelp,
        tournamentFocus: this.tournamentFocus,
        alertSound: this.alertSound,
      };
      globalThis.localStorage?.setItem(KEY, JSON.stringify(data));
    } catch {
      // storage blocked: the choice lasts for this visit only
    }
  }

  toggle(key: keyof Stored): void {
    this[key] = !this[key];
    this.save();
  }
}

export const uiPrefs = new UiPrefs();
