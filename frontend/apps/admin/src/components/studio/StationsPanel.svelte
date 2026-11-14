<script lang="ts">
  // Stations tab of the studio: which station plays in which slot.
  import { SLOT_COLORS } from "../../lib/editor/layoutEditor.svelte";
  import { t } from "../../lib/i18n.svelte";
  import type { SlotRow } from "../../lib/studio";
  import type { StationRow } from "../../lib/types";

  let { slots = $bindable(), stations }: { slots: SlotRow[]; stations: StationRow[] } = $props();
</script>

<section class="panel block">
  <h2>{t("studio.stations")}</h2>
  <p class="muted small">{t("studio.stations_hint")}</p>
  {#each slots as slot (slot.slot)}
    <div class="slot">
      <span class="no" style:--c={SLOT_COLORS[slot.slot % SLOT_COLORS.length]}><span class="dot"></span>{t("studio.slot_long", { n: slot.slot + 1 })}</span>
      <select bind:value={slot.station_id} aria-label={t("studio.slot_long", { n: slot.slot + 1 })}>
        <option value={null}>–</option>
        {#each stations as st (st.id)}<option value={st.id}>{st.name ?? st.id}</option>{/each}
      </select>
      <input placeholder={t("scenes.name_override")} bind:value={slot.name_override} maxlength="64" />
    </div>
  {/each}
</section>

<style>
  .block {
    display: grid;
    gap: 10px;
  }
  h2 {
    margin: 0;
    font-size: 15px;
  }
  .slot {
    display: grid;
    grid-template-columns: 70px minmax(0, 1fr);
    gap: 4px 8px;
    align-items: center;
  }
  .slot input {
    grid-column: 2;
    min-width: 0;
  }
  .no {
    font-size: 13px;
    white-space: nowrap;
  }
  .dot {
    display: inline-block;
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--c);
    margin-right: 6px;
  }
</style>
