<script lang="ts">
  // Quick search (Ctrl+K / ⌘K, or the search button in the menu): pages,
  // players by name, games by number ("#123" or "123"). Arrow keys, Enter, Esc.
  import { api } from "../lib/api";
  import { t } from "../lib/i18n.svelte";
  import { router } from "../lib/router.svelte";
  import type { Page, Player } from "../lib/types";

  interface Props {
    open: boolean;
    onclose: () => void;
    pages: { label: string; href: string }[];
  }
  let { open, onclose, pages }: Props = $props();

  interface Hit {
    kind: "page" | "player" | "game";
    label: string;
    sub?: string;
    href: string;
  }

  let dialog = $state<HTMLDialogElement>();
  let input = $state<HTMLInputElement>();
  let q = $state("");
  let players = $state<Player[]>([]);
  let active = $state(0);
  let timer: ReturnType<typeof setTimeout> | undefined;
  let seq = 0;

  const gameNumber = $derived(/^#?\d{1,9}$/.test(q.trim()) ? Number(q.trim().replace("#", "")) : null);
  const hits = $derived<Hit[]>([
    ...(gameNumber !== null
      ? [{ kind: "game" as const, label: t("palette.game", { id: gameNumber }), href: `/games/${gameNumber}` }]
      : []),
    ...pages
      .filter((p) => !q.trim() || p.label.toLowerCase().includes(q.trim().toLowerCase()))
      .map((p) => ({ kind: "page" as const, label: p.label, href: p.href })),
    ...players.map((p) => ({
      kind: "player" as const,
      label: p.nickname,
      sub: [p.first_name, p.last_name].filter(Boolean).join(" ") || undefined,
      href: `/players/${p.id}`,
    })),
  ]);

  $effect(() => {
    if (!dialog) return;
    if (open && !dialog.open) {
      q = "";
      players = [];
      active = 0;
      dialog.showModal();
      queueMicrotask(() => input?.focus());
    } else if (!open && dialog.open) {
      dialog.close();
    }
  });

  function search(): void {
    active = 0;
    clearTimeout(timer);
    const text = q.trim();
    if (text.length < 2 || gameNumber !== null) {
      players = [];
      return;
    }
    timer = setTimeout(async () => {
      const mine = ++seq;
      try {
        const page = await api<Page<Player>>("/api/players", { query: { q: text, limit: 6 } });
        if (mine === seq) players = page.items;
      } catch {
        if (mine === seq) players = [];
      }
    }, 180);
  }

  function go(hit: Hit | undefined): void {
    if (!hit) return;
    onclose();
    router.go(hit.href);
  }

  function onkeydown(e: KeyboardEvent): void {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      active = Math.min(active + 1, hits.length - 1);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      active = Math.max(active - 1, 0);
    } else if (e.key === "Enter") {
      e.preventDefault();
      go(hits[active]);
    }
  }
</script>

<dialog
  bind:this={dialog}
  aria-label={t("palette.title")}
  oncancel={(e) => {
    e.preventDefault();
    onclose();
  }}
  onclick={(e) => e.target === dialog && onclose()}
>
  <input
    bind:this={input}
    bind:value={q}
    oninput={search}
    {onkeydown}
    type="search"
    role="combobox"
    aria-expanded="true"
    aria-controls="palette-list"
    aria-activedescendant={hits.length ? `palette-${active}` : undefined}
    placeholder={t("palette.placeholder")}
    autocomplete="off"
  />
  <ul id="palette-list" role="listbox">
    {#each hits as hit, i (hit.kind + hit.href)}
      <li id={`palette-${i}`} role="option" aria-selected={i === active}>
        <button class:active={i === active} tabindex="-1" onmousemove={() => (active = i)} onclick={() => go(hit)}>
          <span class="kind">{t(`palette.kind_${hit.kind}`)}</span>
          <span>{hit.label}</span>
          {#if hit.sub}<span class="muted small">{hit.sub}</span>{/if}
        </button>
      </li>
    {:else}
      <li class="muted small none">{t("palette.none")}</li>
    {/each}
  </ul>
  <p class="muted small keys">↑↓ · Enter · Esc</p>
</dialog>

<style>
  dialog {
    width: min(560px, calc(100vw - 24px));
    margin-top: 12vh;
    padding: 0;
    background: var(--panel);
    color: var(--text);
    border: 1px solid var(--line);
    border-radius: var(--radius);
  }
  dialog::backdrop {
    background: rgba(3, 6, 15, 0.7);
  }
  input {
    width: 100%;
    font-size: 16px;
    padding: 12px 14px;
    border: none;
    border-bottom: 1px solid var(--line);
    border-radius: 0;
    background: transparent;
  }
  ul {
    list-style: none;
    margin: 0;
    padding: 6px;
    max-height: 50vh;
    overflow: auto;
  }
  li button {
    width: 100%;
    display: flex;
    gap: 10px;
    align-items: baseline;
    background: none;
    border: none;
    text-align: left;
    padding: 8px 10px;
  }
  li button.active {
    background: var(--panel-2);
  }
  .kind {
    flex: none;
    min-width: 64px;
    font-size: 11px;
    text-transform: uppercase;
    color: var(--muted);
  }
  .none {
    padding: 10px;
  }
  .keys {
    margin: 0;
    padding: 6px 14px 10px;
  }
</style>
