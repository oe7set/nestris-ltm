<script lang="ts">
  // OBS browser source: a 1920x1080 stage scaled to the source size.
  import { onMount, type Component } from "svelte";
  import { text, type Lang } from "./lib/format";
  import { scene, sceneSlug } from "./lib/scene.svelte";
  import type { SceneState } from "./lib/types";
  import { slotView, type SlotView } from "./lib/view";
  import FourPlayers from "./layouts/FourPlayers.svelte";
  import OneVsOne from "./layouts/OneVsOne.svelte";
  import Single from "./layouts/Single.svelte";
  import SingleCompact from "./layouts/SingleCompact.svelte";
  import TwoByOneVsOne from "./layouts/TwoByOneVsOne.svelte";

  type LayoutProps = { state: SceneState; views: SlotView[]; lang: Lang };
  const LAYOUTS: Record<string, Component<LayoutProps>> = {
    single: Single,
    single_compact: SingleCompact,
    "1v1": OneVsOne,
    "2x1v1": TwoByOneVsOne,
    "4p": FourPlayers,
  };

  const W = 1920;
  const H = 1080;
  let scale = $state(1);
  const slug = sceneSlug();
  const params = new URLSearchParams(location.search);

  const current = $derived(scene.state);
  const lang = $derived<Lang>((params.get("lang") as Lang) ?? current?.scene.settings.lang ?? "de");
  const views = $derived(current ? current.slots.map((s) => slotView(s, scene.frames[s.slot])) : []);
  const Layout = $derived(current ? LAYOUTS[current.scene.layout] : undefined);
  const dark = $derived(params.get("bg") === "dark" || current?.scene.settings.background === "dark");

  function fit(): void {
    scale = Math.min(innerWidth / W, innerHeight / H);
  }

  onMount(() => {
    fit();
    addEventListener("resize", fit);
    if (slug) scene.start(slug);
    return () => removeEventListener("resize", fit);
  });
</script>

<div class="stage" class:dark style:transform="scale({scale})">
  {#if !slug || scene.missing}
    <div class="notice">{text(lang, "no_scene")}: {slug ?? "?"}</div>
  {:else if current && Layout}
    <Layout state={current} {views} {lang} />
  {/if}
  {#if slug && !scene.connected && !scene.missing}
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
