// Scene colours (settings.theme) as CSS variables of the stage, and the
// blocks of built-in layouts a scene switched off (settings.show).

import { SHOW_KEYS, type SceneSettings, type ThemeKey } from "./types";

const HEX = /^#[0-9a-fA-F]{6}$/;

const VARS: Record<ThemeKey, string[]> = {
  accent: ["--accent"],
  frame: ["--frame"],
  inner: ["--nes-inner"],
  panel: ["--panel"],
  text: ["--text"],
  good: ["--good", "--side-a"],
  bad: ["--bad", "--side-b"],
};

/** Inline style for the stage; only well-formed #rrggbb values pass. */
export function stageStyle(theme: SceneSettings["theme"] | undefined): string {
  if (!theme) return "";
  const parts: string[] = [];
  for (const [key, value] of Object.entries(theme)) {
    const vars = VARS[key as ThemeKey];
    if (!vars || typeof value !== "string" || !HEX.test(value)) continue;
    for (const v of vars) parts.push(`${v}: ${value}`);
  }
  return parts.join("; ");
}

/** Space separated names of switched-off blocks (``data-hide`` of the stage). */
export function hiddenBlocks(show: SceneSettings["show"] | undefined): string {
  if (!show) return "";
  return SHOW_KEYS.filter((k) => show[k] === false).join(" ");
}
