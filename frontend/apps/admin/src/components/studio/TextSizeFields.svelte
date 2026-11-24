<script lang="ts">
  // Text size of one or more elements: stable (reserved characters, the
  // default), fixed px or fit to the current text. Several elements are
  // changed together (one undo step), e.g. every score of a 4-player scene.
  import type { LayoutEditor } from "../../lib/editor/layoutEditor.svelte";
  import { defaultChars, stableTextPx } from "../../lib/editor/textsize";
  import { t } from "../../lib/i18n.svelte";
  import type { LayoutElement } from "../../lib/studio";

  interface Props {
    editor: LayoutEditor;
    elements: LayoutElement[];
    /** NES style: sizes on the 8 px grid. */
    nes: boolean;
  }
  let { editor, elements, nes }: Props = $props();

  const first = $derived(elements[0]!);
  const ids = $derived(elements.filter((e) => !e.locked).map((e) => e.id));
  const same = <T,>(get: (e: LayoutElement) => T): T | "" => {
    const v = get(first);
    return elements.every((e) => get(e) === v) ? v : "";
  };
  const mode = $derived(same((e) => String(e.props?.text_mode ?? "stable")));
  const size = $derived(same((e) => (typeof e.props?.text_size === "number" ? e.props.text_size : stableTextPx(e, nes))));
  const chars = $derived(same((e) => (typeof e.props?.chars === "number" ? e.props.chars : defaultChars(e))));
  const tags = $derived(elements.every((e) => e.type === "nametag"));
  const keepRows = $derived(elements.every((e) => e.props?.rows !== "collapse"));

  function setMode(value: string): void {
    if (value === "fixed") {
      // Start from the size shown now, per element, so nothing jumps.
      editor.setProps(
        (e) => ({ text_mode: "fixed", text_size: typeof e.props?.text_size === "number" ? e.props.text_size : stableTextPx(e, nes) }),
        ids,
      );
    } else editor.setProps({ text_mode: value === "stable" ? null : value }, ids);
  }

  function num(raw: string, min: number, max: number): number | null {
    const v = Math.round(Number(raw));
    return Number.isFinite(v) && raw !== "" ? Math.min(max, Math.max(min, v)) : null;
  }
</script>

<span class="label">{t("studio.text_size")}</span>
<label class="field">{t("studio.text_mode")}
  <select value={mode} onchange={(e) => setMode(e.currentTarget.value)}>
    {#if mode === ""}<option value="" disabled>{t("studio.mixed")}</option>{/if}
    <option value="stable">{t("studio.text_stable")}</option>
    <option value="fixed">{t("studio.text_fixed")}</option>
    <option value="fit">{t("studio.text_fit")}</option>
  </select>
</label>
{#if mode === "fixed"}
  <label class="field">{t("studio.text_px")}
    <input
      type="number"
      min="8"
      max="200"
      step={nes ? 8 : 1}
      value={size}
      placeholder={t("studio.mixed")}
      onchange={(e) => editor.setProps({ text_size: num(e.currentTarget.value, 8, 200) }, ids)}
    />
  </label>
{:else if mode === "stable"}
  <label class="field" title={t("studio.text_chars_hint")}>{t("studio.text_chars")}
    <input
      type="number"
      min="1"
      max="32"
      value={chars}
      placeholder={t("studio.mixed")}
      onchange={(e) => editor.setProps({ chars: num(e.currentTarget.value, 1, 32) }, ids)}
    />
  </label>
  <p class="muted small">{t("studio.text_stable_hint")}</p>
{/if}
{#if tags && mode !== "fit"}
  <label class="check"><input type="checkbox" checked={keepRows} onchange={(e) => editor.setProps({ rows: e.currentTarget.checked ? null : "collapse" }, ids)} /> {t("studio.keep_rows")}</label>
{/if}

<style>
  .label {
    font-size: 13px;
    color: var(--muted);
  }
</style>
