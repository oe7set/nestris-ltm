<script lang="ts">
  // The items of lib/attention.svelte.ts as links to where they are fixed.
  import { attention, attentionText } from "../lib/attention.svelte";
  import { t } from "../lib/i18n.svelte";

  interface Props {
    /** Called when an item is followed (e.g. to close a popover). */
    onpick?: () => void;
  }
  let { onpick }: Props = $props();
</script>

{#if !attention.items.length}
  <p class="ok muted small">✓ {attention.loaded ? t("attention.none") : t("common.loading")}</p>
{:else}
  <ul>
    {#each attention.items as item (item.code)}
      <li class={item.severity}>
        <a href={`#${item.link}`} onclick={() => onpick?.()}>
          <span class="mark" aria-hidden="true">{item.severity === "error" ? "!" : item.severity === "warn" ? "▲" : "i"}</span>
          <span>{attentionText(item)}</span>
        </a>
      </li>
    {/each}
  </ul>
{/if}

<style>
  ul {
    list-style: none;
    margin: 0;
    padding: 0;
    display: grid;
    gap: 4px;
  }
  a {
    display: flex;
    gap: 10px;
    align-items: baseline;
    padding: 6px 8px;
    border-radius: 6px;
    color: var(--text);
  }
  a:hover {
    background: var(--panel-2);
    text-decoration: none;
  }
  .mark {
    flex: none;
    width: 18px;
    height: 18px;
    border-radius: 50%;
    display: inline-grid;
    place-items: center;
    font-size: 11px;
    font-weight: 700;
    color: #0b1020;
    background: var(--muted);
  }
  .error .mark {
    background: var(--bad);
  }
  .warn .mark {
    background: var(--warn);
  }
  .ok {
    margin: 0;
  }
</style>
