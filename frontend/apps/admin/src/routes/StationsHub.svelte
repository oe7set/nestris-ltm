<script lang="ts">
  // Stations & devices: the stations themselves (identity, live state, per
  // event visibility) and their software (versions, updates of stations,
  // readers and terminals) used to be two pages listing the same stations.
  import { router } from "../lib/router.svelte";
  import { t } from "../lib/i18n.svelte";
  import Devices from "./Devices.svelte";
  import StationConfig from "./StationConfig.svelte";
  import StationPerformance from "./StationPerformance.svelte";
  import Stations from "./Stations.svelte";

  type Tab = "stations" | "perf" | "config" | "devices";
  const TABS: Tab[] = ["stations", "perf", "config", "devices"];
  const initial = router.current.query.get("tab") as Tab | null;
  let tab = $state<Tab>(initial && TABS.includes(initial) ? initial : "stations");

  function setTab(next: Tab): void {
    tab = next;
    router.setQuery({ tab: next === "stations" ? null : next });
  }
</script>

<div class="tabs">
  <button class:on={tab === "stations"} onclick={() => setTab("stations")}>{t("stations.tab_stations")}</button>
  <button class:on={tab === "perf"} onclick={() => setTab("perf")}>{t("stations.tab_perf")}</button>
  <button class:on={tab === "config"} onclick={() => setTab("config")}>{t("stations.tab_config")}</button>
  <button class:on={tab === "devices"} onclick={() => setTab("devices")}>{t("stations.tab_devices")}</button>
</div>
{#if tab === "stations"}
  <Stations />
{:else if tab === "perf"}
  <StationPerformance />
{:else if tab === "config"}
  <StationConfig />
{:else}
  <Devices />
{/if}

<style>
  .tabs {
    display: flex;
    gap: 6px;
    margin-bottom: 14px;
  }
  .tabs button.on {
    border-color: var(--accent);
    color: var(--accent);
  }
</style>
