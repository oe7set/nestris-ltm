<script lang="ts">
  // Stations & devices: the stations themselves (identity, live state, per
  // event visibility) and their software (versions, updates of stations,
  // readers and terminals) used to be two pages listing the same stations.
  import { router } from "../lib/router.svelte";
  import { t } from "../lib/i18n.svelte";
  import Devices from "./Devices.svelte";
  import Stations from "./Stations.svelte";

  type Tab = "stations" | "devices";
  let tab = $state<Tab>(router.current.query.get("tab") === "devices" ? "devices" : "stations");

  function setTab(next: Tab): void {
    tab = next;
    router.setQuery({ tab: next === "stations" ? null : next });
  }
</script>

<div class="tabs">
  <button class:on={tab === "stations"} onclick={() => setTab("stations")}>{t("stations.tab_stations")}</button>
  <button class:on={tab === "devices"} onclick={() => setTab("devices")}>{t("stations.tab_devices")}</button>
</div>
{#if tab === "stations"}
  <Stations />
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
