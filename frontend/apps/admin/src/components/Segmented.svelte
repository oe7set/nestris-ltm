<script lang="ts" generics="T extends string">
  // One choice out of a few, shown as joined buttons (radio group).
  interface Props {
    /** Visible label in front (also the group's accessible name). */
    label?: string;
    options: { value: T; label: string; title?: string }[];
    value: T;
    onchange: (value: T) => void;
    disabled?: boolean;
  }
  let { label, options, value, onchange, disabled = false }: Props = $props();

  const id = `seg-${Math.random().toString(36).slice(2, 8)}`;
</script>

<div class="segmented">
  {#if label}<span class="seg-label" {id}>{label}</span>{/if}
  <div class="seg" role="radiogroup" aria-labelledby={label ? id : undefined}>
    {#each options as option (option.value)}
      <button
        type="button"
        role="radio"
        aria-checked={option.value === value}
        class:on={option.value === value}
        title={option.title}
        {disabled}
        onclick={() => option.value !== value && onchange(option.value)}>{option.label}</button
      >
    {/each}
  </div>
</div>

<style>
  .segmented {
    display: grid;
    gap: 4px;
    justify-items: start;
  }
  .seg-label {
    font-size: 12px;
    color: var(--muted);
  }
</style>
