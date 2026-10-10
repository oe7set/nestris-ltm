<script lang="ts">
  // A failed load: what went wrong and a retry button.
  import { t } from "../lib/i18n.svelte";

  interface Props {
    text: string;
    onretry?: () => void;
  }
  let { text, onretry }: Props = $props();
</script>

<div class="error-box row" role="alert">
  <span class="msg">{text}</span>
  {#if onretry}
    <span class="spacer"></span>
    <button onclick={onretry}>{t("common.retry")}</button>
  {/if}
</div>

<style>
  .error-box {
    margin-bottom: 12px;
  }
  .msg {
    overflow-wrap: anywhere;
  }
</style>
