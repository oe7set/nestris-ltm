<script lang="ts">
  // Stations & devices: the stations themselves (identity, live state, per
  // event visibility) and their software (versions, updates of stations,
  // readers and terminals) used to be two pages listing the same stations.
  import Tabs from "../components/Tabs.svelte";
  import { t } from "../lib/i18n.svelte";
  import { tabFromQuery, tabToQuery } from "../lib/tabs";
  import Devices from "./Devices.svelte";
  import StationConfig from "./StationConfig.svelte";
  import StationPerformance from "./StationPerformance.svelte";
  import Stations from "./Stations.svelte";

  type Tab = "stations" | "perf" | "config" | "devices";
  const TABS: Tab[] = ["stations", "perf", "config", "devices"];
  let tab = $state<Tab>(tabFromQuery(TABS));

  function setTab(next: Tab): void {
    tab = next;
    tabToQuery(TABS, next);
  }
</script>

<Tabs
  tabs={TABS.map((id) => ({ id, label: t(`stations.tab_${id}`) }))}
  active={tab}
  onchange={setTab}
/>
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
</style>
