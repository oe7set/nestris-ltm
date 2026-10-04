<script lang="ts">
  import Toasts from "./components/Toasts.svelte";
  import { i18n, t, type MessageKey } from "./lib/i18n.svelte";
  import { router } from "./lib/router.svelte";
  import { session } from "./lib/session.svelte";
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
  import Scenes from "./routes/Scenes.svelte";
  import Settings from "./routes/Settings.svelte";
  import Stations from "./routes/Stations.svelte";
  import Tournament from "./routes/Tournament.svelte";
  import Devices from "./routes/Devices.svelte";
  import Updates from "./routes/Updates.svelte";

  const nav: { route: string; href: string; label: MessageKey; also?: string[] }[] = [
    { route: "dashboard", href: "/", label: "nav.dashboard" },
    { route: "players", href: "/players", label: "nav.players", also: ["player"] },
    { route: "games", href: "/games", label: "nav.games", also: ["game", "game-new"] },
    { route: "events", href: "/events", label: "nav.events" },
    { route: "tournament", href: "/tournament", label: "nav.tournament" },
    { route: "scenes", href: "/scenes", label: "nav.scenes" },
    { route: "stations", href: "/stations", label: "nav.stations" },
    { route: "devices", href: "/devices", label: "nav.devices" },
    { route: "audit", href: "/audit", label: "nav.audit" },
    { route: "settings", href: "/settings", label: "nav.settings" },
    { route: "updates", href: "/updates", label: "nav.updates" },
    { route: "pages", href: "/pages", label: "nav.pages" },
  ];

  const current = $derived(router.current);

  $effect(() => {
    void session.refresh();
  });

  function isActive(item: (typeof nav)[number]): boolean {
    return current.name === item.route || (item.also ?? []).includes(current.name);
  }
</script>

{#if session.me === null}
  <div class="center muted">{session.error ?? t("common.loading")}</div>
{:else if !session.me.authenticated}
  <Login />
{:else}
  <div class="layout">
    <aside>
      <a class="brand" href="#/">NestrisLTM</a>
      <nav>
        {#each nav as item (item.route)}
          <a href={`#${item.href}`} class:active={isActive(item)}>{t(item.label)}</a>
        {/each}
      </nav>
      <div class="foot">
        <div class="lang">
          <button class:on={i18n.locale === "de"} onclick={() => i18n.set("de")}>DE</button>
          <button class:on={i18n.locale === "en"} onclick={() => i18n.set("en")}>EN</button>
        </div>
        <div class="muted small">{t("nav.signed_in", { name: session.me.name ?? "" })}</div>
        {#if session.me.kind === "session"}
          <button class="link small" onclick={() => session.logout()}>{t("nav.logout")}</button>
        {/if}
      </div>
    </aside>
    <main>
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
        {:else if current.name === "tournament"}
          <Tournament />
        {:else if current.name === "scenes"}
          <Scenes />
        {:else if current.name === "stations"}
          <Stations />
        {:else if current.name === "audit"}
          <Audit />
        {:else if current.name === "settings"}
          <Settings />
        {:else if current.name === "updates"}
          <Updates />
        {:else if current.name === "devices"}
          <Devices />
        {:else if current.name === "pages"}
          <Pages />
        {:else}
          <p class="muted">{t("common.not_found")}</p>
        {/if}
      {/key}
    </main>
  </div>
{/if}
<Toasts />

<style>
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
  @media (max-width: 760px) {
    .layout {
      grid-template-columns: 1fr;
    }
    aside {
      position: static;
      height: auto;
    }
    nav {
      grid-template-columns: repeat(auto-fill, minmax(110px, 1fr));
    }
    main {
      padding: 16px;
    }
  }
</style>
