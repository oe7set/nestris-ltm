<script lang="ts">
  // Hearts of one player in a 1-vs-1 match, with − / + (Regie, Matches).
  import { t } from "../lib/i18n.svelte";

  interface Props {
    current: number;
    max: number;
    /** Player name for the button labels. */
    name: string;
    disabled?: boolean;
    size?: number;
    onlose: () => void;
    ongain: () => void;
  }
  let { current, max, name, disabled = false, size = 18, onlose, ongain }: Props = $props();
</script>

<span class="hearts-ctl">
  <span class="hearts" role="img" aria-label={t("hearts.label", { n: current, max })} style:font-size={`${size}px`}>
    {#each Array.from({ length: max }, (_, i) => i) as i (i)}<span class="heart" class:empty={i >= current}>♥</span>{/each}
  </span>
  <button
    class="mini"
    aria-label={t("hearts.lose", { name })}
    title={t("matches.lose")}
    disabled={disabled || current <= 0}
    onclick={onlose}>−</button
  >
  <button
    class="mini"
    aria-label={t("hearts.gain", { name })}
    title={t("matches.gain")}
    disabled={disabled || current >= max}
    onclick={ongain}>+</button
  >
</span>

<style>
  .hearts-ctl {
    display: inline-flex;
    align-items: center;
    gap: 6px;
  }
  .hearts {
    display: inline-flex;
    gap: 2px;
    line-height: 1;
  }
  .heart {
    color: #e5343a;
    text-shadow: 0 0 1px #000;
  }
  .heart.empty {
    color: transparent;
    -webkit-text-stroke: 1.5px #9aa4b2;
  }
  .mini {
    min-width: 30px;
    justify-content: center;
    padding: 2px 8px;
  }
</style>
