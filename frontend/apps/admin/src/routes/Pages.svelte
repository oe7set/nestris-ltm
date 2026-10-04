<script lang="ts">
  import { copyText } from "../lib/clipboard";
  import { onMount } from "svelte";
  import { api } from "../lib/api";
  import { i18n, t, type MessageKey } from "../lib/i18n.svelte";
  import { toasts } from "../lib/toast.svelte";
  import type { PageInfo } from "../lib/types";

  const GROUPS: PageInfo["group"][] = ["admin", "display", "overlay", "diagnostics", "api", "tray"];

  let pages = $state<PageInfo[]>([]);
  let baseUrls = $state<string[]>([]);
  let base = $state("");

  onMount(async () => {
    try {
      const r = await api<{ pages: PageInfo[]; base_urls: string[] }>("/api/meta/pages");
      pages = r.pages;
      baseUrls = r.base_urls;
      // Prefer a LAN address: OBS and kiosk screens usually run on other PCs.
      base = r.base_urls[1] ?? r.base_urls[0] ?? location.origin;
    } catch (e) {
      toasts.error(e);
    }
  });

  function url(p: PageInfo): string {
    const scheme = p.path.startsWith("/ws") ? base.replace(/^http/, "ws") : base;
    return scheme + p.path;
  }

  async function copy(text: string): Promise<void> {
    try {
      await copyText(text);
      toasts.ok(t("common.copied"));
    } catch (e) {
      toasts.error(e);
    }
  }
</script>

<h1>{t("pages.title")}</h1>
<p class="hint">{t("pages.intro")}</p>

<div class="row base">
  <span class="muted small">{t("pages.addresses")}:</span>
  {#each baseUrls as b (b)}
    <label class="check"><input type="radio" bind:group={base} value={b} /> <span class="mono">{b}</span></label>
  {/each}
</div>

{#each GROUPS as group (group)}
  {@const items = pages.filter((p) => p.group === group)}
  {#if items.length}
    <h2>{t(`pages.group.${group}` as MessageKey)}</h2>
    <div class="list">
      {#each items as p (p.id)}
        <div class="panel item" class:planned={p.status === "planned"}>
          <div class="row">
            <strong>{i18n.locale === "en" ? p.title_en : p.title_de}</strong>
            {#if p.status === "planned"}
              <span class="badge">{t("pages.planned", { n: p.phase ?? "?" })}</span>
            {:else if group !== "tray"}
              <span class="badge {p.public ? 'ok' : ''}">{p.public ? t("pages.public") : t("pages.login")}</span>
            {/if}
          </div>
          <div class="muted small">{i18n.locale === "en" ? p.description_en : p.description_de}</div>
          {#if group !== "tray"}
            <div class="row link">
              <code class="mono">{group === "admin" ? p.path : url(p)}</code>
              {#if p.status === "available"}
                {#if group === "admin"}
                  <a class="button" href={p.path.replace(/^\//, "")}>{t("common.open")}</a>
                {:else}
                  {#if !p.path.startsWith("/ws")}<a class="button" href={p.path} target="_blank" rel="noopener">{t("common.open")}</a>{/if}
                  <button onclick={() => copy(url(p))}>{t("common.copy")}</button>
                {/if}
              {/if}
            </div>
          {/if}
        </div>
      {/each}
    </div>
  {/if}
{/each}

<style>
  .base {
    margin-bottom: 18px;
    gap: 14px;
  }
  h2 {
    margin-top: 22px;
  }
  .list {
    display: grid;
    gap: 10px;
    grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  }
  .item {
    display: grid;
    gap: 6px;
    align-content: start;
  }
  .item.planned {
    opacity: 0.6;
  }
  .link code {
    flex: 1;
    min-width: 0;
    overflow-wrap: anywhere;
    color: var(--link);
  }
</style>
