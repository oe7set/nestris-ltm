<script lang="ts">
  import { onMount } from "svelte";
  import AttentionBell from "./components/AttentionBell.svelte";
  import CommandPalette from "./components/CommandPalette.svelte";
  import ConfirmHost from "./components/ConfirmHost.svelte";
  import DatabaseProblem from "./components/DatabaseProblem.svelte";
  import Toasts from "./components/Toasts.svelte";
  import { api } from "./lib/api";
  import { attention } from "./lib/attention.svelte";
  import { i18n, t, tDynamic, type MessageKey } from "./lib/i18n.svelte";
  import { router } from "./lib/router.svelte";
  import { session } from "./lib/session.svelte";
  import { uiPrefs } from "./lib/uiPrefs.svelte";
  import Audit from "./routes/Audit.svelte";
  import Dashboard from "./routes/Dashboard.svelte";
  import Events from "./routes/Events.svelte";
  import GameDetail from "./routes/GameDetail.svelte";
  import GameNew from "./routes/GameNew.svelte";
  import Games from "./routes/Games.svelte";
  import Login from "./routes/Login.svelte";
  import Pages from "./routes/Pages.svelte";
  import PlayerDetail from "./routes/PlayerDetail.svelte";
  import Players from "./routes/Players.svelte";
  import Regie from "./routes/Regie.svelte";
  import Results from "./routes/Results.svelte";
  import Settings from "./routes/Settings.svelte";
  import Spool from "./routes/Spool.svelte";
  import StationsHub from "./routes/StationsHub.svelte";
  import Tournament from "./routes/Tournament.svelte";
  import Studio from "./routes/Studio.svelte";
  import StudioLayout from "./routes/StudioLayout.svelte";
  import StudioScene from "./routes/StudioScene.svelte";
  import Updates from "./routes/Updates.svelte";

  type NavItem = { route: string; href: string; label: MessageKey; also?: string[] };
  // Grouped by task: running the event, its data, the look, the system.
  const navGroups: { label: MessageKey; items: NavItem[] }[] = [
    {
      label: "nav.group.live",
      items: [
        { route: "dashboard", href: "/", label: "nav.dashboard" },
        { route: "regie", href: "/regie", label: "nav.regie" },
        { route: "tournament", href: "/tournament", label: "nav.tournament" },
      ],
    },
    {
      label: "nav.group.data",
      items: [
        { route: "players", href: "/players", label: "nav.players", also: ["player"] },
        { route: "games", href: "/games", label: "nav.games", also: ["game", "game-new"] },
        { route: "events", href: "/events", label: "nav.events" },
        { route: "results", href: "/results", label: "nav.results" },
      ],
    },
    {
      label: "nav.group.design",
      items: [{ route: "studio", href: "/studio", label: "nav.studio", also: ["studio-scene", "studio-layout"] }],
    },
    {
      label: "nav.group.system",
      items: [
        { route: "stations", href: "/stations", label: "nav.stations_devices" },
        { route: "audit", href: "/audit", label: "nav.audit" },
        { route: "updates", href: "/updates", label: "nav.updates" },
        { route: "database", href: "/database", label: "nav.database" },
        { route: "spool", href: "/spool", label: "nav.spool" },
        { route: "settings", href: "/settings", label: "nav.settings" },
        { route: "pages", href: "/pages", label: "nav.pages" },
      ],
    },
  ];

  const current = $derived(router.current);

  // A helper login: Regie, Turnier (hearts), players, games, results.
  const HELPER_ROUTES = new Set(["dashboard", "regie", "tournament", "players", "games", "results"]);
  const visibleGroups = $derived(
    session.isAdmin
      ? navGroups
      : navGroups
          .map((g) => ({ ...g, items: g.items.filter((i) => HELPER_ROUTES.has(i.route)) }))
          .filter((g) => g.items.length),
  );

  $effect(() => {
    void session.refresh();
  });

  onMount(() => {
    // While the server is unreachable (no answer at all), keep asking; and
    // while the database is down under a running app, watch for its return.
    const timer = setInterval(async () => {
      if (session.me === null && !session.dbState) {
        await session.refresh();
      } else if (session.me !== null && session.dbState) {
        try {
          const health = await api<{ database: { ready: boolean } }>("/api/health");
          if (health.database.ready) session.dbRecovered();
        } catch {
          // still down
        }
      }
    }, 3000);
    return () => clearInterval(timer);
  });

  // The bell polls only while someone is signed in.
  const signedIn = $derived(session.me?.authenticated === true);
  $effect(() => {
    if (signedIn) return attention.start();
  });

  function isActive(item: NavItem): boolean {
    return current.name === item.route || (item.also ?? []).includes(current.name);
  }

  // Turnier in focus mode: the bracket gets the whole window.
  const focus = $derived(
    current.name === "tournament" && uiPrefs.tournamentFocus && current.query.get("tab") !== "matches",
  );

  // Phones: the navigation folds into a menu button above the page.
  let menuOpen = $state(false);
  const currentLabel = $derived(
    navGroups.flatMap((g) => g.items).find((item) => isActive(item))?.label ?? null,
  );
  $effect(() => {
    void current.name;
    menuOpen = false;
  });

  // Quick search: Ctrl+K / ⌘K anywhere.
  let paletteOpen = $state(false);
  const palettePages = $derived(
    visibleGroups.flatMap((g) => g.items).map((i) => ({ label: t(i.label), href: i.href })),
  );
  function onGlobalKey(e: KeyboardEvent): void {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k" && session.me?.authenticated) {
      e.preventDefault();
      paletteOpen = !paletteOpen;
    } else if (e.key === "Escape") {
      menuOpen = false;
    }
  }

  // The browser tab names the page (history, screen readers, many tabs).
  $effect(() => {
    document.title = currentLabel ? `${t(currentLabel)} · NestrisLTM` : "NestrisLTM";
  });
</script>

{#if session.me === null && session.dbState}
  <div class="gate"><DatabaseProblem onready={() => session.refresh()} /></div>
{:else if session.me === null}
  <div class="center muted">{session.error ?? t("common.loading")}</div>
{:else if !session.me.authenticated}
  <Login />
{:else}
  <a class="skip" href="#main-content" onclick={(e) => { e.preventDefault(); document.getElementById("main-content")?.focus(); }}>{t("nav.skip")}</a>
  <div class="layout" class:focus>
    <aside class:open={menuOpen}>
      <div class="top">
        <a class="brand" href="#/">NestrisLTM</a>
        <AttentionBell />
        <button
          class="menu-btn"
          aria-expanded={menuOpen}
          aria-controls="main-nav"
          onclick={() => (menuOpen = !menuOpen)}
        >
          <span aria-hidden="true">{menuOpen ? "✕" : "☰"}</span>
          {currentLabel ? t(currentLabel) : t("nav.menu")}
        </button>
      </div>
      <button class="search-btn" onclick={() => (paletteOpen = true)} aria-keyshortcuts="Control+K">
        🔍 {t("palette.title")} <kbd>Strg K</kbd>
      </button>
      <nav id="main-nav">
        {#each visibleGroups as group (group.label)}
          <span class="group">{t(group.label)}</span>
          {#each group.items as item (item.route)}
            <a
              href={`#${item.href}`}
              class:active={isActive(item)}
              aria-current={isActive(item) ? "page" : undefined}
              onclick={() => (menuOpen = false)}>{t(item.label)}</a
            >
          {/each}
        {/each}
      </nav>
      <div class="foot">
        <div class="lang">
          <button aria-pressed={i18n.locale === "de"} class:on={i18n.locale === "de"} onclick={() => i18n.set("de")}>DE</button>
          <button aria-pressed={i18n.locale === "en"} class:on={i18n.locale === "en"} onclick={() => i18n.set("en")}>EN</button>
        </div>
        <div class="muted small">
          {t("nav.signed_in", { name: session.me.name ?? "" })}
          {#if !session.isAdmin}<span class="badge">{t("roles.helper")}</span>{/if}
        </div>
        {#if session.me.kind === "session"}
          <button class="link small" onclick={() => session.logout()}>{t("nav.logout")}</button>
        {/if}
      </div>
    </aside>
    <main id="main-content" tabindex="-1">
      {#if session.dbState && current.name !== "database"}
        <div class="db-banner" role="alert">
          <span class="dot bad"></span>
          <span>{t("db.banner", { title: tDynamic(`db.state.${session.dbState}.title`, session.dbState) })}</span>
          <a href="#/database">{t("db.banner_link")}</a>
        </div>
      {/if}
      {#key current.name + JSON.stringify(current.params)}
        {#if current.name === "dashboard"}
          <Dashboard />
        {:else if current.name === "players"}
          <Players />
        {:else if current.name === "player"}
          <PlayerDetail id={Number(current.params.id)} />
        {:else if current.name === "games"}
          <Games />
        {:else if current.name === "game-new"}
          <GameNew />
        {:else if current.name === "game"}
          <GameDetail id={Number(current.params.id)} />
        {:else if current.name === "events"}
          <Events />
        {:else if current.name === "results"}
          <Results />
        {:else if current.name === "tournament"}
          <Tournament />
        {:else if current.name === "regie"}
          <Regie />
        {:else if current.name === "stations"}
          <StationsHub />
        {:else if current.name === "audit"}
          <Audit />
        {:else if current.name === "settings"}
          <Settings />
        {:else if current.name === "updates"}
          <Updates />
        {:else if current.name === "studio"}
          <Studio />
        {:else if current.name === "studio-scene"}
          <!-- keyed: going from one scene to another (duplicate) loads it fresh -->
          {#key current.params.id}
            <StudioScene id={current.params.id ?? ""} />
          {/key}
        {:else if current.name === "studio-layout"}
          {#key current.params.id}
            <StudioLayout id={current.params.id ?? "new"} />
          {/key}
        {:else if current.name === "pages"}
          <Pages />
        {:else if current.name === "database"}
          <DatabaseProblem />
        {:else if current.name === "spool"}
          <Spool />
        {:else}
          <p class="muted">{t("common.not_found")}</p>
        {/if}
      {/key}
    </main>
  </div>
{/if}
<svelte:window onkeydown={onGlobalKey} />
{#if session.me?.authenticated}
  <CommandPalette open={paletteOpen} onclose={() => (paletteOpen = false)} pages={palettePages} />
{/if}
<Toasts />
<ConfirmHost />

<style>
  .search-btn {
    justify-content: space-between;
    width: 100%;
    color: var(--muted);
    font-size: 13px;
  }
  .search-btn kbd {
    font-size: 10px;
    border: 1px solid var(--line);
    border-radius: 4px;
    padding: 0 4px;
  }
  .skip {
    position: absolute;
    left: 8px;
    top: -40px;
    z-index: 200;
    background: var(--accent);
    color: var(--accent-ink);
    padding: 6px 12px;
    border-radius: 6px;
  }
  .skip:focus {
    top: 8px;
  }
  main:focus {
    outline: none;
  }
  .gate {
    padding: 24px 16px;
    display: grid;
    justify-items: center;
  }
  .db-banner {
    display: flex;
    gap: 10px;
    align-items: center;
    flex-wrap: wrap;
    border: 1px solid #7f1d1d;
    background: #2a1215;
    color: #fecaca;
    border-radius: 8px;
    padding: 8px 12px;
    margin-bottom: 14px;
  }
  .center {
    display: grid;
    place-items: center;
    min-height: 100vh;
  }
  .layout {
    display: grid;
    grid-template-columns: 210px 1fr;
    min-height: 100vh;
  }
  aside {
    background: #0a0f1d;
    border-right: 1px solid var(--line);
    padding: 16px 12px;
    display: flex;
    flex-direction: column;
    gap: 16px;
    position: sticky;
    top: 0;
    height: 100vh;
  }
  .top {
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .brand {
    color: var(--accent);
    font-weight: 700;
    font-size: 19px;
    letter-spacing: 0.5px;
    padding: 0 8px;
  }
  .brand:hover {
    text-decoration: none;
  }
  nav {
    display: grid;
    gap: 2px;
  }
  nav a {
    color: var(--text);
    padding: 8px 10px;
    border-radius: 8px;
  }
  nav a:hover {
    background: var(--panel);
    text-decoration: none;
  }
  nav a.active {
    background: var(--panel-2);
    color: var(--accent);
  }
  nav .group {
    margin: 12px 10px 2px;
    font-size: 11px;
    letter-spacing: 1px;
    text-transform: uppercase;
    color: var(--muted);
  }
  nav .group:first-child {
    margin-top: 0;
  }
  .foot {
    margin-top: auto;
    display: grid;
    gap: 6px;
    padding: 0 8px;
  }
  .lang {
    display: flex;
    gap: 4px;
  }
  .lang button {
    padding: 2px 8px;
    font-size: 12px;
  }
  .lang button.on {
    border-color: var(--accent);
    color: var(--accent);
  }
  main {
    padding: 20px 24px 40px;
    min-width: 0;
  }
  /* Editors whose side panels run down to the window's bottom edge. */
  main:has(:global(.fill-page)) {
    padding-bottom: 12px;
  }
  .menu-btn {
    display: none;
  }
  .layout.focus {
    grid-template-columns: 1fr;
  }
  .layout.focus > aside {
    display: none;
  }
  .layout.focus main {
    padding: 8px 12px 12px;
  }
  @media (max-width: 760px) {
    .layout {
      grid-template-columns: 1fr;
    }
    aside {
      height: auto;
      padding: 8px 12px;
      gap: 8px;
      z-index: 30;
      border-right: none;
      border-bottom: 1px solid var(--line);
    }
    .top {
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .menu-btn {
      display: block;
      margin-left: auto;
      min-height: 40px;
      min-width: 0;
      flex: 0 1 auto;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .brand {
      flex: none;
    }
    aside:not(.open) nav,
    aside:not(.open) .search-btn,
    aside:not(.open) .foot {
      display: none;
    }
    aside.open {
      max-height: 100vh;
      overflow-y: auto;
    }
    nav {
      grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
    }
    nav a {
      padding: 10px 12px;
    }
    nav .group {
      grid-column: 1 / -1;
    }
    .foot {
      padding-bottom: 8px;
    }
    main {
      padding: 12px 12px 96px;
    }
  }
</style>
