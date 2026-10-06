<script lang="ts">
  // A live overlay preview (iframe of the overlay app, 16:9). Either a saved
  // scene with demo data (``slug``) or an unsaved configuration sent to
  // /o/_preview (``config``). Loaded only when visible; ``still`` draws one
  // frame instead of an animation (galleries).
  import { onMount } from "svelte";
  import type { PreviewConfig } from "../lib/studio";

  interface Props {
    slug?: string | null;
    config?: PreviewConfig | null;
    still?: boolean;
    background?: "transparent" | "dark" | "checker";
    title?: string;
    /** Layout builder canvas (/o/_edit: hidden elements show faintly). */
    edit?: boolean;
  }
  let { slug = null, config = null, still = true, background = "dark", title = "", edit = false }: Props = $props();

  let box: HTMLDivElement;
  let frame = $state<HTMLIFrameElement | null>(null);
  let visible = $state(false);
  let ready = false;

  const src = $derived(
    slug
      ? `/o/${encodeURIComponent(slug)}?demo=1${still ? "&still=1" : ""}${background === "dark" ? "&bg=dark" : ""}`
      : `/o/${edit ? "_edit" : "_preview"}?demo=1${still ? "&still=1" : ""}${background === "dark" ? "&bg=dark" : ""}`,
  );

  function send(): void {
    if (!ready || !config || !frame?.contentWindow) return;
    // Plain data only: the overlay is another document.
    frame.contentWindow.postMessage({ type: "preview-config", config: $state.snapshot(config) }, location.origin);
  }

  $effect(() => {
    // A new iframe (other src) must announce itself again before we send.
    void src;
    ready = false;
  });

  $effect(() => {
    // Re-send whenever the configuration changes.
    void JSON.stringify(config);
    send();
  });

  onMount(() => {
    const onMessage = (event: MessageEvent): void => {
      if (event.origin !== location.origin || !frame || event.source !== frame.contentWindow) return;
      const data = event.data as { type?: string };
      if (data?.type === "ready") {
        ready = true;
        send();
      }
    };
    addEventListener("message", onMessage);
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) {
          visible = true;
          observer.disconnect();
        }
      },
      { rootMargin: "200px" },
    );
    observer.observe(box);
    return () => {
      removeEventListener("message", onMessage);
      observer.disconnect();
    };
  });
</script>

<div class="thumb {background}" bind:this={box}>
  {#if visible}
    {#key src}
      <iframe bind:this={frame} {src} {title} tabindex="-1" loading="lazy"></iframe>
    {/key}
  {/if}
</div>

<style>
  .thumb {
    position: relative;
    width: 100%;
    aspect-ratio: 16 / 9;
    border-radius: 8px;
    overflow: hidden;
    border: 1px solid var(--line);
    background: #05070d;
  }
  .thumb.checker {
    background-color: #2a2f3a;
    background-image:
      linear-gradient(45deg, #3a4150 25%, transparent 25%),
      linear-gradient(-45deg, #3a4150 25%, transparent 25%),
      linear-gradient(45deg, transparent 75%, #3a4150 75%),
      linear-gradient(-45deg, transparent 75%, #3a4150 75%);
    background-size: 24px 24px;
    background-position: 0 0, 0 12px, 12px -12px, -12px 0;
  }
  .thumb.transparent {
    background: transparent;
  }
  iframe {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    border: 0;
    pointer-events: none;
    background: transparent;
  }
</style>
