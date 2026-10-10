// In-app confirmation instead of the browser's confirm(): one dialog
// (components/ConfirmHost.svelte, mounted once in App.svelte) and a promise
// that resolves to the answer.
//
//   if (!(await confirmAsync({ title: "Delete?", danger: true }))) return;

export interface ConfirmOptions {
  title: string;
  /** What will happen, in one or two sentences. */
  text?: string;
  /** Label of the confirming button (default: "Bestätigen"). */
  confirmLabel?: string;
  /** Red confirm button for destructive actions. */
  danger?: boolean;
  /** Ask the user to type this text before the button unlocks. */
  typeToConfirm?: string;
}

export interface PendingConfirm extends ConfirmOptions {
  resolve: (ok: boolean) => void;
}

class ConfirmState {
  current = $state<PendingConfirm | null>(null);

  ask(options: ConfirmOptions): Promise<boolean> {
    // A second question while one is open answers the first with "no".
    this.current?.resolve(false);
    return new Promise((resolve) => {
      this.current = { ...options, resolve };
    });
  }

  answer(ok: boolean): void {
    const pending = this.current;
    this.current = null;
    pending?.resolve(ok);
  }
}

export const confirmState = new ConfirmState();

export function confirmAsync(options: ConfirmOptions): Promise<boolean> {
  return confirmState.ask(options);
}
