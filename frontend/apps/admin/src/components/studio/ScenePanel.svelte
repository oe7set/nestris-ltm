<script lang="ts">
  // Scene tab of the studio: name, OBS address, layout, look and colours.
  import { copyText } from "../../lib/clipboard";
  import { t, tDynamic } from "../../lib/i18n.svelte";
  import { SHOW_KEYS, THEME_DEFAULTS, THEME_KEYS, type SceneSettings } from "../../lib/studio";
  import { toasts } from "../../lib/toast.svelte";

  interface Props {
    name: string;
    slug: string;
    settings: SceneSettings;
    layoutTitle: string;
    /** A built-in layout: blocks are switched here, not as elements. */
    builtin: boolean;
    onchangelayout: () => void;
  }
  let { name = $bindable(), slug, settings = $bindable(), layoutTitle, builtin, onchangelayout }: Props = $props();

  const url = $derived(`${location.origin}/o/${slug}`);

  async function copyUrl(): Promise<void> {
    try {
      await copyText(url);
      toasts.ok(t("studio.url_copied"));
    } catch (e) {
      toasts.error(e);
    }
  }
</script>

<section class="panel block">
  <h2>{t("studio.general")}</h2>
  <label class="field">{t("common.name")}<input bind:value={name} maxlength="128" /></label>
  <div class="field">
    <span>{t("studio.obs_url")}</span>
    <div class="row url">
      <code class="mono" title={url}>/o/{slug}</code>
      <button class="small" onclick={copyUrl}>{t("studio.copy")}</button>
      <a class="small" href="/o/{slug}" target="_blank" rel="noopener">{t("studio.open_overlay")} ↗</a>
    </div>
    <span class="muted small">{t("studio.obs_hint")}</span>
  </div>
  <div class="field">
    <span>{t("scenes.layout")}</span>
    <button class="layout-btn" onclick={onchangelayout}>{layoutTitle} — {t("studio.change")}</button>
  </div>
  <p class="muted small">{t("studio.flow_in_regie")} <a href="#/regie">{t("nav.regie")} →</a></p>
</section>

<section class="panel block">
  <h2>{t("studio.look")}</h2>
  <div class="seg">
    <button aria-pressed={settings.style === "nes"} class:on={settings.style === "nes"} onclick={() => (settings.style = "nes")}>NES</button>
    <button aria-pressed={settings.style === "modern"} class:on={settings.style === "modern"} onclick={() => (settings.style = "modern")}>Modern</button>
  </div>
  <label class="field">{t("scenes.title_override")}<input bind:value={settings.title} maxlength="64" placeholder={name} /></label>
  <div class="two">
    <label class="field">
      {t("settings.language")}
      <select bind:value={settings.lang}><option value="de">Deutsch</option><option value="en">English</option></select>
    </label>
    <label class="field">
      {t("scenes.background")}
      <select bind:value={settings.background}>
        <option value="transparent">{t("scenes.bg_transparent")}</option>
        <option value="dark">{t("scenes.bg_dark")}</option>
      </select>
    </label>
  </div>
  {#if builtin}
    <label class="check"><input type="checkbox" bind:checked={settings.camera_frames} /> {t("scenes.camera_frames")}</label>
  {/if}
</section>

{#if builtin}
  <section class="panel block">
    <h2>{t("studio.blocks")}</h2>
    <div class="grid2">
      {#each SHOW_KEYS as k (k)}
        <label class="check"><input type="checkbox" bind:checked={settings.show[k]} /> {tDynamic(`studio.block_${k}`, k)}</label>
      {/each}
    </div>
  </section>
{/if}

<section class="panel block">
  <div class="row"><h2>{t("studio.colors")}</h2><span class="spacer"></span>
    <button class="link small" onclick={() => (settings.theme = {})}>{t("studio.reset_colors")}</button></div>
  <div class="grid2">
    {#each THEME_KEYS as k (k)}
      <label class="color">
        <input
          type="color"
          value={settings.theme[k] ?? THEME_DEFAULTS[k]}
          oninput={(e) => (settings.theme = { ...settings.theme, [k]: e.currentTarget.value })}
        />
        <span class:custom={!!settings.theme[k]}>{tDynamic(`studio.color_${k}`, k)}</span>
        {#if settings.theme[k]}
          <button class="link small" aria-label={t("studio.reset_colors")} onclick={() => { const { [k]: _, ...rest } = settings.theme; settings.theme = rest; }}>↺</button>
        {/if}
      </label>
    {/each}
  </div>
</section>

<style>
  .block {
    display: grid;
    gap: 10px;
  }
  h2 {
    margin: 0;
    font-size: 15px;
  }
  .url {
    gap: 8px;
    flex-wrap: wrap;
  }
  .url code {
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .small {
    padding: 2px 8px;
    font-size: 13px;
  }
  .layout-btn {
    text-align: left;
  }
  .two,
  .grid2 {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 8px;
  }
  .color {
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .color input {
    width: 34px;
    height: 26px;
    padding: 0;
    border: 1px solid var(--line);
  }
  .color .custom {
    color: var(--accent);
  }
</style>
