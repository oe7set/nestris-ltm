<script lang="ts">
  // Score difference A - B over the round (above the line: A leads).
  import { diffSeries } from "../lib/graph";

  interface Props {
    a: [number, number][] | undefined;
    b: [number, number][] | undefined;
    width?: number;
    height?: number;
  }
  let { a, b, width = 300, height = 120 }: Props = $props();
  const uid = $props.id();

  const points = $derived(diffSeries(a ?? [], b ?? []));
  const geometry = $derived.by(() => {
    if (points.length < 2) return null;
    const t0 = points[0]![0];
    const t1 = Math.max(points[points.length - 1]![0], t0 + 1);
    const maxAbs = Math.max(1, ...points.map((p) => Math.abs(p[1])));
    const x = (t: number) => ((t - t0) / (t1 - t0)) * width;
    const y = (d: number) => height / 2 - (d / maxAbs) * (height / 2 - 4);
    const line = points.map((p, i) => `${i ? "L" : "M"}${x(p[0]).toFixed(1)},${y(p[1]).toFixed(1)}`).join("");
    const area = `${line}L${x(t1).toFixed(1)},${height / 2}L0,${height / 2}Z`;
    return { line, area };
  });
</script>

<svg {width} {height} viewBox="0 0 {width} {height}">
  <defs>
    <clipPath id="{uid}-top"><rect x="0" y="0" {width} height={height / 2} /></clipPath>
    <clipPath id="{uid}-bottom"><rect x="0" y={height / 2} {width} height={height / 2} /></clipPath>
  </defs>
  <line x1="0" x2={width} y1={height / 2} y2={height / 2} class="zero" />
  {#if geometry}
    <path d={geometry.area} class="area a" clip-path="url(#{uid}-top)" />
    <path d={geometry.area} class="area b" clip-path="url(#{uid}-bottom)" />
    <path d={geometry.line} class="line" />
  {/if}
</svg>

<style>
  svg {
    display: block;
    background: var(--panel);
    border: 2px solid var(--frame);
    border-radius: 8px;
  }
  .zero {
    stroke: var(--muted);
    stroke-dasharray: 4 4;
    stroke-width: 1;
  }
  .line {
    fill: none;
    stroke: var(--text);
    stroke-width: 2;
  }
  .area.a {
    fill: color-mix(in srgb, var(--side-a) 45%, transparent);
  }
  .area.b {
    fill: color-mix(in srgb, var(--side-b) 45%, transparent);
  }
</style>
