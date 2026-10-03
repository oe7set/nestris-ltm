<script lang="ts">
  // 10x20 NES playfield on a canvas, redrawn on every frame (up to 60 Hz).
  import { drawBlock, levelColors, parseRows } from "../lib/nes";

  interface Props {
    rows: string[] | null | undefined;
    level: number | null | undefined;
    cell?: number;
    dim?: boolean;
  }
  let { rows, level, cell = 32, dim = false }: Props = $props();

  let canvas: HTMLCanvasElement;

  $effect(() => {
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.imageSmoothingEnabled = false;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    const grid = parseRows(rows);
    if (!grid) return;
    const colors = levelColors(level);
    for (let y = 0; y < 20; y++) {
      const row = grid[y]!;
      for (let x = 0; x < 10; x++) {
        const c = row[x]!;
        if (c > 0) drawBlock(ctx, c, x * cell, y * cell, cell, colors);
      }
    }
  });
</script>

<canvas bind:this={canvas} width={cell * 10} height={cell * 20} class:dim></canvas>

<style>
  canvas {
    display: block;
    image-rendering: pixelated;
    transition: opacity 0.4s, filter 0.4s;
  }
  canvas.dim {
    opacity: 0.45;
    filter: grayscale(0.6);
  }
</style>
