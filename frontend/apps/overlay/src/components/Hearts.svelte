<script lang="ts">
  // Hearts of a player in a 1-vs-1 match (8-bit pixel hearts, own artwork).
  // A lost heart stays as a dark silhouette; losing one flashes it briefly.
  interface Props {
    current: number | null;
    max: number;
    size?: number; // pixel size of one heart pixel
    align?: "left" | "right";
  }
  let { current, max, size = 3, align = "left" }: Props = $props();

  // O = outline, R = red, W = highlight. 11 x 10 pixels.
  const SHAPE = [
    "..OO...OO..",
    ".ORRO.ORRO.",
    "ORWRRORRRRO",
    "ORRRRRRRRRO",
    "ORRRRRRRRRO",
    ".ORRRRRRRO.",
    "..ORRRRRO..",
    "...ORRRO...",
    "....ORO....",
    ".....O.....",
  ];
  const PIXELS = SHAPE.flatMap((row, y) => [...row].map((c, x) => ({ x, y, c })).filter((p) => p.c !== "."));
  const FULL: Record<string, string> = { O: "#1a0a0c", R: "#e8203a", W: "#ffe8ea" };
  const EMPTY: Record<string, string> = { O: "#8f8f9c", R: "#1c1c26", W: "#1c1c26" };

  const have = $derived(Math.max(0, current ?? 0));
  let breaking = $state<number | null>(null);
  let previous: number | null = null;
  let timer: ReturnType<typeof setTimeout> | undefined;

  $effect(() => {
    const now = have;
    if (previous !== null && now < previous) {
      breaking = now; // index of the heart that was just lost
      clearTimeout(timer);
      timer = setTimeout(() => (breaking = null), 1200);
    }
    previous = now;
  });

  const order = $derived(
    align === "right" ? Array.from({ length: max }, (_, i) => max - 1 - i) : Array.from({ length: max }, (_, i) => i),
  );
</script>

<span class="hearts" role="img" aria-label="{have}/{max}">
  {#each order as i (i)}
    {@const full = i < have}
    <svg
      class:breaking={breaking === i}
      width={11 * size}
      height={10 * size}
      viewBox="0 0 11 10"
      shape-rendering="crispEdges"
    >
      {#each PIXELS as p (`${p.x},${p.y}`)}
        <rect x={p.x} y={p.y} width="1" height="1" fill={(full ? FULL : EMPTY)[p.c]} />
      {/each}
    </svg>
  {/each}
</span>

<style>
  .hearts {
    display: inline-flex;
    gap: 6px;
    flex: none;
    filter: drop-shadow(0 2px 0 #000a);
  }
  svg {
    display: block;
  }
  .breaking {
    animation: lost 1.2s steps(2, jump-none) 1;
  }
  @keyframes lost {
    0%,
    20%,
    40%,
    60% {
      transform: scale(1.25);
      filter: brightness(2.2);
    }
    10%,
    30%,
    50%,
    70% {
      transform: scale(1);
      filter: none;
    }
    100% {
      transform: scale(1);
    }
  }
</style>
