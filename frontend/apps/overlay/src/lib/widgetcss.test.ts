// Own-layout widgets must never pick up the frames of the built-in layouts:
// a global rule that paints a frame (border / box-shadow) on a class the
// widget also uses gave double frames in OBS (next, versus, ranking).

import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const read = (rel: string): string => readFileSync(new URL(rel, import.meta.url), "utf8");

/** Static class names in Widget.svelte's markup (dynamic parts dropped). */
function widgetClasses(): Set<string> {
  const markup = read("../components/Widget.svelte").split("<style>")[0]!;
  const out = new Set<string>();
  for (const m of markup.matchAll(/class="([^"]*)"/g)) {
    for (const token of m[1]!.replace(/\{[^}]*\}/g, " ").split(/\s+/)) if (token) out.add(token.replace(/-$/, ""));
  }
  return out;
}

/** Selector items of rules that paint a frame, ":is(a, b)" expanded. */
function framingSelectors(css: string): string[] {
  const out: string[] = [];
  const flat = css.replace(/\/\*[\s\S]*?\*\//g, "");
  for (const m of flat.matchAll(/([^{}]+)\{([^{}]*)\}/g)) {
    const [selector, body] = [m[1]!.trim(), m[2]!];
    if (!/(^|[;\s])(border(-width)?|box-shadow)\s*:/.test(body) || selector.startsWith("@")) continue;
    for (const part of selector.split(/,(?![^(]*\))/)) {
      const is = part.match(/^(.*?):is\(([^)]*)\)(.*)$/);
      if (!is) out.push(part.trim());
      else for (const inner of is[2]!.split(",")) out.push(`${is[1]}${inner.trim()}${is[3]}`.trim());
    }
  }
  return out;
}

describe("widget frames", () => {
  const classes = widgetClasses();

  it.each(["../nes.css", "../overlay.css"])("%s frames no widget class from outside", (file) => {
    const clashes: string[] = [];
    for (const sel of framingSelectors(read(file))) {
      // Rules written for widgets go through the widget root ".w".
      if (/\.w(\s|>|$|\.)/.test(sel)) continue;
      const compounds = sel.replace(/^\.stage(\.[a-z-]+)*\s+/, "").split(/\s+/);
      // Context selectors ("header .title", ".side .box") need an ancestor no widget has.
      if (compounds.length !== 1) continue;
      for (const c of compounds[0]!.matchAll(/\.([a-z][a-z0-9-]*)/g)) if (classes.has(c[1]!)) clashes.push(`${sel} → .${c[1]}`);
    }
    expect(clashes).toEqual([]);
  });

  it("does not put the element type on the widget root as a plain class", () => {
    expect(read("../components/Widget.svelte")).not.toMatch(/class="w \{el\.type\}/);
  });
});
