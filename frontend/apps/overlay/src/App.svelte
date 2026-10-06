<script lang="ts">
  // OBS browser source: a 1920x1080 stage scaled to the source size.
  // Also the renderer of the studio (thumbnails, editor preview, layout
  // builder): see lib/host.svelte.ts for the modes.
  import { onMount, type Component } from "svelte";
  import { definitions } from "./lib/definitions.svelte";
  import { text, type Lang } from "./lib/format";
  import { host, overlayMode } from "./lib/host.svelte";
  import { customId } from "./lib/layoutdef";
  import { look } from "./lib/look.svelte";
  import { scene, sceneSlug } from "./lib/scene.svelte";
  import { stageStyle, hiddenBlocks } from "./lib/theme";
  import type { SceneState } from "./lib/types";
  import { slotView, type SlotView } from "./lib/view";
  import Custom from "./layouts/Custom.svelte";
  import FourPlayers from "./layouts/FourPlayers.svelte";
  import OneVsOne from "./layouts/OneVsOne.svelte";
  import OneVsOneCam from "./layouts/OneVsOneCam.svelte";
  import Replay from "./layouts/Replay.svelte";
  import Single from "./layouts/Single.svelte";
  import SingleCompact from "./layouts/SingleCompact.svelte";
  import TwoByOneVsOne from "./layouts/TwoByOneVsOne.svelte";
  import TwoByOneVsOneCam from "./layouts/TwoByOneVsOneCam.svelte";

  type LayoutProps = { state: SceneState; views: SlotView[]; lang: Lang };
  const LAYOUTS: Record<string, Component<LayoutProps>> = {
    single: Single,
    single_compact: SingleCompact,
    "1v1": OneVsOne,
    "2x1v1": TwoByOneVsOne,
    "1v1_cam": OneVsOneCam,
    "2x1v1_cam": TwoByOneVsOneCam,
    "4p": FourPlayers,
    replay: Replay,
  };

  const W = 1920;
  const H = 1080;
  let scale = $state(1);
  const slug = sceneSlug();
  const params = new URLSearchParams(location.search);
  const mode = overlayMode(slug, params);
  const studio = mode === "preview" || mode === "edit";
  // Thumbnails: one demo frame instead of an animation.
  const still = params.get("still") === "1";
  const tickMs = still ? 0 : 100;

  // In the studio the edited (unsaved) scene replaces the stored one; the data
  // underneath is demo data or, on request, the live data of the saved scene.
  const current = $derived.by((): SceneState | null => {
    const s = scene.state;
    if (!s) return null;
    return studio && host.config ? { ...s, scene: host.config.scene } : s;
  });
  const lang = $derived<Lang>((params.get("lang") as Lang) ?? current?.scene.settings.lang ?? "de");
  const views = $derived(current ? current.slots.map((s) => slotView(s, scene.frames[s.slot])) : []);
  const isCustom = $derived(current ? customId(current.scene.layout) !== null || mode === "edit" : false);
  const Layout = $derived(current && !isCustom ? LAYOUTS[current.scene.layout] : undefined);
  const definition = $derived.by(() => {
    if (!current) return null;
    if (studio && host.config?.definition) return host.config.definition;
    const id = customId(current.scene.layout);
    return id ? (definitions.byId[id] ?? null) : null;
  });
  const dark = $derived(params.get("bg") === "dark" || current?.scene.settings.background === "dark");
  // NES is the standard style; "modern" only when the scene (or ?style=) says so.
  const nes = $derived((params.get("style") ?? current?.scene.settings.style ?? "nes") === "nes");
  const themeStyle = $derived(stageStyle(current?.scene.settings.theme));
  const hide = $derived(hiddenBlocks(current?.scene.settings.show));
  $effect(() => {
    look.nes = nes;
  });

  // Own layouts: fetch the definition whenever the scene names a new revision.
  $effect(() => {
    const s = current;
    if (!s || (studio && host.config?.definition)) return;
    const id = customId(s.scene.layout);
    if (id) definitions.ensure(id, s.scene.layout_rev);
  });

  // Studio: follow the editor's data source (demo or the saved scene live).
  let source: string | null = null;
  $effect(() => {
    if (!studio) return;
    const config = host.config;
    if (!config) return;
    const wanted = config.liveSlug ? `live:${config.liveSlug}` : "demo";
    // A still picture is redrawn on every config change; an animation keeps
    // running and picks the new config up on its next tick.
    if (wanted === source && !still) return;
    source = wanted;
    if (config.liveSlug) scene.start(config.liveSlug);
    else
      scene.startDemo(
        () => (host.config ? { scene: host.config.scene, slots: host.config.slots, names: host.config.names } : null),
        tickMs,
      );
  });

  function fit(): void {
    scale = Math.min(innerWidth / W, innerHeight / H);
  }

  onMount(() => {
    fit();
    addEventListener("resize", fit);
    let refresh: ReturnType<typeof setInterval> | undefined;
    if (mode === "live" && slug) {
      scene.start(slug);
    } else if (mode === "demo" && slug) {
      // The saved scene with demo data; its settings are re-read now and then.
      let info: Awaited<ReturnType<typeof scene.loadInfo>> = null;
      const load = async (): Promise<void> => {
        info = (await scene.loadInfo(slug)) ?? info;
      };
      void load().then(() => scene.startDemo(() => info, tickMs));
      refresh = setInterval(() => void load().then(() => still && scene.startDemo(() => info, 0)), 5000);
    } else if (studio) {
      host.listen(mode);
    }
    return () => {
      removeEventListener("resize", fit);
      clearInterval(refresh);
      scene.stop();
    };
  });
</script>

<div
  class="stage"
  class:dark
  class:nes
  class:editing={mode === "edit"}
  data-hide={isCustom ? "" : hide}
  style={themeStyle}
  style:transform="scale({scale})"
>
  {#if !slug || scene.missing}
    <div class="notice">{text(lang, "no_scene")}: {slug ?? "?"}</div>
  {:else if current && isCustom}
    <Custom state={current} {views} {lang} {definition} editing={mode === "edit"} />
  {:else if current && Layout}
    <Layout state={current} {views} {lang} />
  {/if}
  {#if mode === "live" && slug && !scene.connected && !scene.missing}
    <div class="offline">{text(lang, "offline")}</div>
  {/if}
</div>

<style>
  .stage {
    position: absolute;
    left: 0;
    top: 0;
    width: 1920px;
    height: 1080px;
    transform-origin: 0 0;
    overflow: hidden;
  }
  .stage.dark {
    background: radial-gradient(ellipse at center, #141c33 0%, #070a14 100%);
  }
  .notice {
    position: absolute;
    inset: 0;
    display: grid;
    place-items: center;
    font-size: 40px;
    color: var(--muted);
  }
  .offline {
    position: absolute;
    right: 12px;
    bottom: 10px;
    font-size: 14px;
    color: var(--bad);
    opacity: 0.8;
  }
</style>
