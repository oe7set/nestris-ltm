<script lang="ts">
  import { t } from "../lib/i18n.svelte";

  interface Props {
    total: number;
    limit: number;
    offset: number;
    onchange: (offset: number) => void;
  }
  let { total, limit, offset, onchange }: Props = $props();
</script>

{#if total > 0}
  <div class="row pager">
    <span class="muted small">
      {t("common.range", { from: offset + 1, to: Math.min(offset + limit, total), total })}
    </span>
    <span class="spacer"></span>
    <button disabled={offset === 0} onclick={() => onchange(Math.max(0, offset - limit))}>
      ‹ {t("common.prev")}
    </button>
    <button disabled={offset + limit >= total} onclick={() => onchange(offset + limit)}>
      {t("common.next")} ›
    </button>
  </div>
{/if}

<style>
  .pager {
    margin-top: 10px;
  }
  @media (max-width: 640px) {
    .pager button {
      min-height: 40px;
      flex: 1;
      justify-content: center;
    }
    .pager .muted {
      flex-basis: 100%;
    }
  }
</style>
