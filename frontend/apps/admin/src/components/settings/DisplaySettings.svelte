<script lang="ts">
  // Einstellungen → Highscore-Anzeige: the public highscore / bracket display
  // (/view/highscore, beamer or OBS). Changes reach every open display at
  // once over its WebSocket. Moved here from the tournament console.
  import { onMount } from "svelte";
  import { api } from "../../lib/api";
  import { copyText } from "../../lib/clipboard";
  import { t } from "../../lib/i18n.svelte";
  import { toasts } from "../../lib/toast.svelte";

  interface ViewSettings {
    font_scale: number;
    autoscroll: boolean;
    effects_enabled: boolean;
    banners_enabled: boolean;
    box_opacity: number;
  }

  let view = $state<ViewSettings | null>(null);
  let celebration = $state(true);
  let scroll = $state(0);
  let origin = $state(location.origin);
  const timers: Record<string, ReturnType<typeof setTimeout>> = {};

  async function load(): Promise<void> {
    try {
      const snap = await api<{ view_settings: ViewSettings; celebration: { enabled: boolean } }>("/api/tournament/state");
      view = snap.view_settings;
      celebration = snap.celebration?.enabled !== false;
    } catch (e) {
      toasts.error(e);
    }
  }

  async function post(path: string, body: Record<string, unknown>): Promise<void> {
    try {
      await api(path, { method: "POST", body });
    } catch (e) {
      toasts.error(e);
      await load();
    }
  }

  /** Sliders: update at once, send after a short pause (like the console did). */
  function debounced(key: string, fn: () => void, ms = 250): void {
    clearTimeout(timers[key]);
    timers[key] = setTimeout(fn, ms);
  }

  function setView(change: Partial<ViewSettings>, debounce = false): void {
    if (!view) return;
    view = { ...view, ...change };
    const send = () => void post("/api/tournament/view/settings", change);
    if (debounce) debounced(Object.keys(change).join(","), send);
    else send();
  }

  const transparency = $derived(view ? Math.round((1 - view.box_opacity) * 100) : 0);

  function links(): { label: string; url: string }[] {
    return [
      { label: t("display.link_all"), url: `${origin}/view/highscore` },
      { label: t("display.link_highscore"), url: `${origin}/view/highscore?only=highscore` },
      { label: t("display.link_bracket"), url: `${origin}/view/highscore?only=bracket` },
      { label: t("display.link_transparent"), url: `${origin}/view/highscore?transparent=1` },
    ];
  }

  async function copy(text: string): Promise<void> {
    try {
      await copyText(text);
      toasts.ok(t("common.copied"));
    } catch (e) {
      toasts.error(e);
    }
  }

  onMount(() => {
    void load();
    api<{ base_urls: string[] }>("/api/meta/pages")
      .then((m) => (origin = m.base_urls[1] ?? m.base_urls[0] ?? location.origin))
      .catch(() => {});
  });
</script>

{#if view}
  <section class="panel block">
    <h2>{t("display.look")}</h2>
    <label class="field">
      {t("display.font_scale")} <strong>{view.font_scale.toFixed(1)}×</strong>
      <input type="range" min="0.6" max="2.5" step="0.1" value={view.font_scale}
             oninput={(e) => setView({ font_scale: Number(e.currentTarget.value) }, true)} />
    </label>
    <label class="field">
      {t("display.transparency")} <strong>{transparency}%</strong>
      <input type="range" min="0" max="75" step="5" value={transparency}
             oninput={(e) => setView({ box_opacity: 1 - Number(e.currentTarget.value) / 100 }, true)} />
    </label>
    <div class="checks">
      <label class="check"><input type="checkbox" checked={view.autoscroll} onchange={(e) => setView({ autoscroll: e.currentTarget.checked })} /> {t("display.autoscroll")}</label>
      <label class="check"><input type="checkbox" checked={view.effects_enabled} onchange={(e) => setView({ effects_enabled: e.currentTarget.checked })} /> {t("display.effects")}</label>
      <label class="check"><input type="checkbox" checked={view.banners_enabled} onchange={(e) => setView({ banners_enabled: e.currentTarget.checked })} /> {t("display.banners")}</label>
      <label class="check">
        <input type="checkbox" checked={celebration}
               onchange={(e) => { celebration = e.currentTarget.checked; void post("/api/tournament/celebration", { enabled: celebration }); }} />
        {t("display.celebration")}
      </label>
    </div>
  </section>

  <section class="panel block">
    <h2>{t("display.scroll")}</h2>
    <p class="hint">{t("display.scroll_hint")}</p>
    <div class="row">
      <button onclick={() => { scroll = 0; void post("/api/tournament/view/scroll", { position: 0 }); }}>{t("display.top")}</button>
      <input class="grow" type="range" min="0" max="100" value={scroll}
             oninput={(e) => { scroll = Number(e.currentTarget.value); debounced("scroll", () => void post("/api/tournament/view/scroll", { position: scroll / 100 }), 60); }} />
      <button onclick={() => { scroll = 100; void post("/api/tournament/view/scroll", { position: 1 }); }}>{t("display.bottom")}</button>
    </div>
  </section>
{/if}

<section class="panel block">
  <h2>{t("display.links")}</h2>
  <table>
    <tbody>
      {#each links() as l (l.url)}
        <tr>
          <td>{l.label}</td>
          <td><code class="mono">{l.url}</code></td>
          <td class="actions">
            <button onclick={() => copy(l.url)}>{t("common.copy")}</button>
            <a class="button" href={l.url} target="_blank" rel="noopener">↗</a>
          </td>
        </tr>
      {/each}
    </tbody>
  </table>
</section>

<style>
  .block {
    margin-bottom: 16px;
    display: grid;
    gap: 12px;
  }
  .block h2 {
    margin: 0;
  }
  .field input[type="range"] {
    width: min(420px, 100%);
  }
  .checks {
    display: flex;
    flex-wrap: wrap;
    gap: 20px;
  }
  .row {
    gap: 10px;
    align-items: center;
  }
  .grow {
    flex: 1;
    max-width: 420px;
  }
  .actions {
    text-align: right;
    white-space: nowrap;
  }
  code {
    color: var(--link);
  }
</style>
