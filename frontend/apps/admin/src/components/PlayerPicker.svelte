<script lang="ts">
  // Search-as-you-type selection of a player.
  import { api } from "../lib/api";
  import { t } from "../lib/i18n.svelte";
  import type { Page, Player } from "../lib/types";

  interface Props {
    value: number | null;
    initialLabel?: string | null;
    excludeId?: number;
    onselect: (player: Player) => void;
  }
  let { value, initialLabel = null, excludeId, onselect }: Props = $props();

  let query = $state("");
  let results = $state<Player[]>([]);
  let open = $state(false);
  let label = $state<string | null>(null);
  let timer: ReturnType<typeof setTimeout> | undefined;

  const shown = $derived(label ?? initialLabel);

  function search(): void {
    clearTimeout(timer);
    timer = setTimeout(async () => {
      const page = await api<Page<Player>>("/api/players", { query: { q: query, limit: 12 } });
      results = page.items.filter((p) => p.id !== excludeId);
      open = true;
    }, 200);
  }

  function choose(player: Player): void {
    label = player.nickname;
    query = "";
    open = false;
    onselect(player);
  }
</script>

<div class="picker">
  {#if value !== null && shown}
    <div class="current">{shown}</div>
  {/if}
  <input
    type="search"
    placeholder={t("game.player_search")}
    bind:value={query}
    oninput={search}
    onfocus={search}
    onblur={() => setTimeout(() => (open = false), 150)}
  />
  {#if open && results.length}
    <ul>
      {#each results as player (player.id)}
        <li>
          <button type="button" class="link" onmousedown={() => choose(player)}>
            {player.nickname}
            {#if player.first_name || player.last_name}
              <span class="muted small">{player.first_name ?? ""} {player.last_name ?? ""}</span>
            {/if}
          </button>
        </li>
      {/each}
    </ul>
  {/if}
</div>

<style>
  .picker {
    position: relative;
    display: grid;
    gap: 6px;
  }
  .current {
    font-weight: 600;
  }
  ul {
    position: absolute;
    top: 100%;
    left: 0;
    right: 0;
    z-index: 10;
    margin: 4px 0 0;
    padding: 4px 0;
    list-style: none;
    background: var(--panel-2);
    border: 1px solid var(--line);
    border-radius: 8px;
    max-height: 260px;
    overflow: auto;
  }
  li button {
    width: 100%;
    text-align: left;
    padding: 6px 12px;
    color: var(--text);
    display: flex;
    gap: 8px;
  }
  li button:hover {
    background: var(--panel);
  }
</style>
