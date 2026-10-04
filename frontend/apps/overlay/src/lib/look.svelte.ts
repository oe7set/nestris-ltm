// Visual style of the overlay ("modern" or "nes"), set by App.svelte from the
// scene settings (or ?style=nes). Reactive, so formatting follows a switch.

export const look = $state({ nes: false });
