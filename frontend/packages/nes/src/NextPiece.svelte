<script lang="ts">
  import { PIECES, drawBlock, levelColors } from "./nes";

  interface Props {
    piece: string | null | undefined;
    level: number | null | undefined;
    cell?: number;
  }
  let { piece, level, cell = 24 }: Props = $props();

  let canvas: HTMLCanvasElement;

  $effect(() => {
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    const shape = piece ? PIECES[piece] : undefined;
    if (!shape) return;
    const colors = levelColors(level);
    const width = Math.max(...shape.cells.map(([x]) => x)) + 1;
    const height = Math.max(...shape.cells.map(([, y]) => y)) + 1;
    const ox = ((4 - width) * cell) / 2;
    const oy = ((2 - height) * cell) / 2;
    for (const [x, y] of shape.cells) drawBlock(ctx, shape.kind, ox + x * cell, oy + y * cell, cell, colors);
  });
</script>

<canvas bind:this={canvas} width={cell * 4} height={cell * 2}></canvas>

<style>
  canvas {
    display: block;
    image-rendering: pixelated;
  }
</style>
