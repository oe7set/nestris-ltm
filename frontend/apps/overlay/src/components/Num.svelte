<script lang="ts">
  // A number that counts up/down smoothly to its new value.
  import { cubicOut } from "svelte/easing";
  import { Tween } from "svelte/motion";
  import { fmt } from "../lib/format";

  interface Props {
    value: number | null | undefined;
    duration?: number;
  }
  let { value, duration = 450 }: Props = $props();

  const tween = new Tween(0, { duration: 0, easing: cubicOut });
  let first = true;

  $effect(() => {
    const target = value ?? 0;
    // Jump on the first value and on big drops (new round), animate otherwise.
    const jump = first || target < tween.current - 50_000;
    void tween.set(target, { duration: jump ? 0 : duration });
    first = false;
  });
</script>

{value === null || value === undefined ? "–" : fmt(tween.current)}
