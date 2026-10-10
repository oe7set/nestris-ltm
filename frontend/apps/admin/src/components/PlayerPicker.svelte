<script lang="ts">
  // Search-as-you-type selection of a player (combobox: arrow keys, Enter,
  // Escape; mouse and touch work as well).
  import { api } from "../lib/api";
  import { t } from "../lib/i18n.svelte";
  import type { Page, Player } from "../lib/types";

  interface Props {
    value: number | null;
    initialLabel?: string | null;
    excludeId?: number;
    onselect: (player: Player) => void;
    /** Visible label (default: the search hint is the accessible name). */
    label?: string;
  }
  let { value, initialLabel = null, excludeId, onselect, label: fieldLabel }: Props = $props();

  const listId = `picker-${Math.random().toString(36).slice(2, 8)}`;

  let query = $state("");
  let results = $state<Player[]>([]);
  let open = $state(false);
  let loading = $state(false);
  let failed = $state(false);
  let active = $state(-1);
  let chosen = $state<string | null>(null);
  let timer: ReturnType<typeof setTimeout> | undefined;
  let seq = 0;

  const shown = $derived(chosen ?? initialLabel);

  function search(): void {
    clearTimeout(timer);
    timer = setTimeout(async () => {
      const mine = ++seq;
      loading = true;
      failed = false;
      try {
        const page = await api<Page<Player>>("/api/players", { query: { q: query, limit: 12 } });
        if (mine !== seq) return; // a newer search is on its way
        results = page.items.filter((p) => p.id !== excludeId);
      } catch {
        if (mine !== seq) return;
        results = [];
        failed = true;
      } finally {
        if (mine === seq) loading = false;
      }
      active = results.length ? 0 : -1;
      open = true;
    }, 200);
  }

  function choose(player: Player): void {
    chosen = player.nickname;
    query = "";
    open = false;
    active = -1;
    onselect(player);
  }

  function onkeydown(e: KeyboardEvent): void {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      if (!open) search();
      else if (results.length) active = (active + 1) % results.length;
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      if (results.length) active = (active - 1 + results.length) % results.length;
    } else if (e.key === "Enter") {
      if (open && active >= 0 && results[active]) {
        e.preventDefault();
        choose(results[active]!);
      }
    } else if (e.key === "Escape" && open) {
      // Close the list, not the dialog around the picker.
      e.preventDefault();
      e.stopPropagation();
      open = false;
    }
  }
</script>

<div class="picker">
  {#if value !== null && shown}
    <div class="current">{shown}</div>
  {/if}
  <input
    type="search"
    role="combobox"
    aria-label={fieldLabel ?? t("game.player_search")}
    aria-expanded={open}
    aria-controls={listId}
    aria-autocomplete="list"
    aria-activedescendant={open && active >= 0 ? `${listId}-${active}` : undefined}
    placeholder={t("game.player_search")}
    autocomplete="off"
    bind:value={query}
    oninput={search}
    onfocus={search}
    {onkeydown}
    onblur={() => setTimeout(() => (open = false), 150)}
  />
  {#if open}
    <ul id={listId} role="listbox">
      {#each results as player, i (player.id)}
        <li id={`${listId}-${i}`} role="option" aria-selected={i === active}>
          <button
            type="button"
            class="link"
            class:active={i === active}
            tabindex="-1"
            onmousedown={(e) => {
              e.preventDefault();
              choose(player);
            }}
          >
            {player.nickname}
            {#if player.first_name || player.last_name}
              <span class="muted small">{player.first_name ?? ""} {player.last_name ?? ""}</span>
            {/if}
          </button>
        </li>
      {:else}
        <li class="empty muted small">
          {loading ? t("common.loading") : failed ? t("picker.failed") : t("picker.none")}
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
    padding: 8px 12px;
    color: var(--text);
    display: flex;
    gap: 8px;
  }
  li button:hover,
  li button.active {
    background: var(--panel);
  }
  li.empty {
    padding: 8px 12px;
  }
</style>
