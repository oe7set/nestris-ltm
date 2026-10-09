<script lang="ts">
  // Remote configuration of the stations: a template for all stations plus
  // per-station overrides. Saving sends the merged set; the station stores
  // it and restarts its recognition after the running game.
  import { onMount } from "svelte";
  import { api } from "../lib/api";
  import { dateTime } from "../lib/format";
  import { i18n, t, tDynamic } from "../lib/i18n.svelte";
  import { toasts } from "../lib/toast.svelte";
  import {
    FORM_KEYS,
    GROUPS,
    display,
    getPath,
    leafPaths,
    parseInput,
    setPath,
    sourceOf,
    type ConfigOverview,
    type ConfigStation,
    type Field,
    type Values,
  } from "../lib/stationConfig";

  const TEMPLATE = "__template__";

  let data = $state<ConfigOverview | null>(null);
  let selected = $state<string>(TEMPLATE);
  let draft = $state<Values>({});
  let dirty = $state(false);
  let raw = $state("");
  let rawError = $state<string | null>(null);
  let showRaw = $state(false);
  let copyTargets = $state<string[]>([]);
  let busy = $state(false);

  const station = $derived<ConfigStation | null>(
    selected === TEMPLATE ? null : (data?.stations.find((s) => s.id === selected) ?? null),
  );
  const report = $derived(station?.report ?? null);
  const template = $derived<Values | null>(data?.template ?? null);
  const extraKeys = $derived(leafPaths(draft).filter((k) => !FORM_KEYS.has(k)));

  async function load(): Promise<void> {
    try {
      data = await api<ConfigOverview>("/api/station-config");
      if (!dirty) resetDraft();
    } catch (e) {
      toasts.error(e);
    }
  }

  function resetDraft(): void {
    const base = selected === TEMPLATE ? template : station?.overrides;
    draft = structuredClone($state.snapshot(base ?? {})) as Values;
    raw = JSON.stringify(draft, null, 2);
    rawError = null;
    dirty = false;
  }

  function select(id: string): void {
    selected = id;
    dirty = false;
    copyTargets = [];
    resetDraft();
  }

  function setValue(field: Field, input: string): void {
    draft = setPath(draft, field.key, parseInput(field, input));
    raw = JSON.stringify(draft, null, 2);
    dirty = true;
  }

  function clearValue(key: string): void {
    draft = setPath(draft, key, undefined);
    raw = JSON.stringify(draft, null, 2);
    dirty = true;
  }

  function applyRaw(): void {
    try {
      const parsed = JSON.parse(raw || "{}");
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error("{ … }");
      draft = parsed as Values;
      rawError = null;
      dirty = true;
    } catch (e) {
      rawError = e instanceof Error ? e.message : String(e);
    }
  }

  async function run(fn: () => Promise<unknown>, message: string): Promise<void> {
    busy = true;
    try {
      await fn();
      toasts.ok(message);
      dirty = false;
      await load();
    } catch (e) {
      toasts.error(e);
    } finally {
      busy = false;
    }
  }

  function save(): void {
    const body = { values: $state.snapshot(draft) };
    if (selected === TEMPLATE) {
      void run(() => api("/api/station-config/template", { method: "PUT", body }), t("sconf.saved"));
    } else {
      void run(
        () => api(`/api/stations/${encodeURIComponent(selected)}/config`, { method: "PUT", body }),
        t("sconf.saved"),
      );
    }
  }

  function dropOverrides(): void {
    if (!confirm(t("sconf.drop_confirm"))) return;
    void run(() => api(`/api/stations/${encodeURIComponent(selected)}/config`, { method: "DELETE" }), t("sconf.saved"));
  }

  function resend(): void {
    void run(() => api(`/api/stations/${encodeURIComponent(selected)}/config/apply`, { method: "POST" }), t("sconf.sent"));
  }

  function scanDevices(): void {
    void run(
      () => api(`/api/stations/${encodeURIComponent(selected)}/config/devices`, { method: "POST" }),
      t("sconf.scanning"),
    );
  }

  function copy(): void {
    if (!copyTargets.length) return;
    void run(
      () =>
        api(`/api/stations/${encodeURIComponent(selected)}/config/copy`, {
          method: "POST",
          body: { targets: $state.snapshot(copyTargets) },
        }),
      t("sconf.copied", { n: copyTargets.length }),
    );
    copyTargets = [];
  }

  onMount(() => {
    void load();
    // Reports change after an apply (pending -> restarting -> applied).
    const timer = setInterval(load, 3000);
    return () => clearInterval(timer);
  });

  function stateClass(s: ConfigStation): string {
    const st = s.report?.state;
    if (!s.report) return "";
    if (st === "rejected") return "bad";
    if (s.in_sync) return "ok";
    return "warn";
  }

  // Placeholder: what the station would run without this layer's value.
  function placeholder(key: string): string {
    if (selected === TEMPLATE) return "";
    const fromTemplate = getPath(template, key);
    if (fromTemplate !== undefined) return display(fromTemplate);
    return display(getPath(report?.effective, key));
  }

  const devices = $derived(report?.devices ?? null);
  const formats = $derived.by(() => {
    const device = String(getPath(draft, "capture.device") ?? getPath(report?.effective, "capture.device") ?? "");
    return devices?.capture.find((d) => d.path === device)?.formats ?? [];
  });
</script>

<p class="hint">{t("sconf.intro")}</p>

<div class="layout">
  <nav class="panel list">
    <button class:on={selected === TEMPLATE} onclick={() => select(TEMPLATE)}>
      <strong>{t("sconf.template")}</strong>
      <span class="muted small">{t("sconf.template_hint")}</span>
    </button>
    {#each data?.stations ?? [] as s (s.id)}
      <button class:on={selected === s.id} onclick={() => select(s.id)}>
        <span class="dot {s.online ? 'ok' : 'bad'}"></span>
        <strong>{s.name ?? s.id}</strong>
        {#if s.report}
          <span class="badge {stateClass(s)}">{tDynamic(`sconf.state.${s.in_sync ? "in_sync" : s.report.state}`, s.report.state)}</span>
        {:else}
          <span class="badge">{t("sconf.unsupported_short")}</span>
        {/if}
      </button>
    {/each}
  </nav>

  <section class="editor">
    {#if station}
      <div class="panel status">
        <div class="row">
          <strong>{station.name ?? station.id}</strong>
          <span class="muted small mono">{station.id}</span>
          {#if report?.version}<span class="muted small">v{report.version}</span>{/if}
        </div>
        {#if !report}
          <p class="warn-text">{t("sconf.unsupported")}</p>
        {:else}
          <p>
            <span class="badge {stateClass(station)}">{tDynamic(`sconf.state.${station.in_sync ? "in_sync" : report.state}`, report.state)}</span>
            {#if report.rev != null}<span class="muted small mono">rev {report.rev}</span>{/if}
            {#if !station.managed}<span class="muted small">{t("sconf.unmanaged")}</span>{/if}
            {#if station.managed && !station.in_sync && report.state !== "pending" && report.state !== "restarting"}
              <span class="muted small">{t("sconf.not_in_sync")}</span>
            {/if}
          </p>
          {#if report.error}<p class="error-box small">{report.error}</p>{/if}
          {#if report.locked.length}
            <p class="muted small">{t("sconf.locked_keys")}: <span class="mono">{report.locked.join(", ")}</span></p>
          {/if}
        {/if}
        <div class="row">
          <button disabled={busy || !station.online || !report || !station.managed} onclick={resend}>{t("sconf.resend")}</button>
          <button disabled={busy || !station.online || !report} onclick={scanDevices}>{t("sconf.scan")}</button>
          {#if station.overrides}
            <button class="danger" disabled={busy} onclick={dropOverrides}>{t("sconf.drop")}</button>
          {/if}
        </div>
        {#if station.updated_at}
          <p class="muted small">{t("sconf.updated", { by: station.updated_by ?? "?", at: dateTime(station.updated_at, i18n.locale) })}</p>
        {/if}
        {#if !station.known}<p class="warn-text small">{t("sconf.not_known")}</p>{/if}
      </div>
    {:else}
      <div class="panel status">
        <strong>{t("sconf.template")}</strong>
        <p class="muted small">{t("sconf.template_intro")}</p>
      </div>
    {/if}

    {#each GROUPS as group (group.id)}
      <fieldset class="panel">
        <legend>{tDynamic(`sconf.g.${group.id}`, group.id)}</legend>
        {#each group.fields as field (field.key)}
          {@const value = getPath(draft, field.key)}
          {@const source = station ? sourceOf(field.key, draft, template, report?.locked) : value !== undefined ? "override" : "local"}
          <div class="field">
            <label for="f-{field.key}">
              {tDynamic(`sconf.f.${field.key}`, field.key)}
              <span class="muted small mono">{field.key}</span>
            </label>
            <div class="input">
              {#if field.kind === "bool"}
                <select id="f-{field.key}" value={display(value)} onchange={(e) => setValue(field, e.currentTarget.value)} disabled={source === "locked"}>
                  <option value="">{placeholder(field.key) ? `– (${placeholder(field.key)})` : "–"}</option>
                  <option value="true">{t("common.yes")}</option>
                  <option value="false">{t("common.no")}</option>
                </select>
              {:else if field.kind === "select"}
                <select id="f-{field.key}" value={display(value)} onchange={(e) => setValue(field, e.currentTarget.value)} disabled={source === "locked"}>
                  <option value="">{placeholder(field.key) ? `– (${placeholder(field.key)})` : "–"}</option>
                  {#each field.options ?? [] as opt (opt)}<option value={opt}>{tDynamic(`sconf.o.${field.key}.${opt}`, opt)}</option>{/each}
                </select>
              {:else}
                <input
                  id="f-{field.key}"
                  type={field.kind === "text" ? "text" : "number"}
                  min={field.min}
                  max={field.max}
                  step={field.step ?? (field.kind === "int" ? 1 : "any")}
                  value={display(value)}
                  placeholder={placeholder(field.key)}
                  list={field.key === "capture.device" ? "dev-capture" : field.key === "rfid.port" ? "dev-serial" : field.key === "capture.input_format" ? "dev-formats" : undefined}
                  disabled={source === "locked"}
                  onchange={(e) => setValue(field, e.currentTarget.value)}
                />
              {/if}
              {#if station}
                <span class="badge src-{source}">{tDynamic(`sconf.src.${source}`, source)}</span>
              {/if}
              {#if value !== undefined}
                <button class="link" title={t("sconf.reset")} onclick={() => clearValue(field.key)}>↺</button>
              {/if}
            </div>
            <p class="muted small help">{tDynamic(`sconf.h.${field.key}`, "")}</p>
          </div>
        {/each}
      </fieldset>
    {/each}

    {#if formats.length}
      <p class="muted small">
        {t("sconf.device_formats")}:
        {#each formats as f (f.format)}<span class="mono">{f.format}</span> {f.sizes.join(" ")}; {/each}
      </p>
    {/if}
    <datalist id="dev-capture">{#each devices?.capture ?? [] as d (d.path)}<option value={d.path}></option>{/each}</datalist>
    <datalist id="dev-serial">{#each devices?.serial ?? [] as p (p)}<option value={p}></option>{/each}</datalist>
    <datalist id="dev-formats">{#each formats as f (f.format)}<option value={f.format}></option>{/each}</datalist>

    {#if extraKeys.length}
      <p class="muted small">{t("sconf.extra_keys")}: <span class="mono">{extraKeys.join(", ")}</span></p>
    {/if}

    <details class="panel" bind:open={showRaw}>
      <summary>{t("sconf.raw")}</summary>
      <textarea rows="10" class="mono" bind:value={raw} oninput={() => (dirty = true)}></textarea>
      {#if rawError}<p class="error-box small">{rawError}</p>{/if}
      <button onclick={applyRaw}>{t("sconf.raw_apply")}</button>
    </details>

    <div class="actions">
      <button class="primary" disabled={busy || !dirty} onclick={save}>
        {selected === TEMPLATE ? t("sconf.save_template") : t("sconf.save_station")}
      </button>
      <button disabled={busy || !dirty} onclick={resetDraft}>{t("sconf.discard")}</button>
      {#if station && data}
        <span class="copy">
          <select multiple size="3" bind:value={copyTargets} aria-label={t("sconf.copy_to")}>
            {#each data.stations.filter((s) => s.id !== station.id && s.known) as s (s.id)}
              <option value={s.id}>{s.name ?? s.id}</option>
            {/each}
          </select>
          <button disabled={busy || dirty || !copyTargets.length} onclick={copy}>{t("sconf.copy_to")}</button>
        </span>
      {/if}
    </div>
  </section>
</div>

<style>
  .layout {
    display: grid;
    grid-template-columns: minmax(200px, 260px) 1fr;
    gap: 14px;
    align-items: start;
  }
  @media (max-width: 800px) {
    .layout {
      grid-template-columns: 1fr;
    }
  }
  .list {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  .list button {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 6px;
    text-align: left;
  }
  .list button.on {
    border-color: var(--accent);
  }
  .editor {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }
  .status p {
    margin: 6px 0;
  }
  .row {
    display: flex;
    flex-wrap: wrap;
    align-items: baseline;
    gap: 8px;
  }
  fieldset {
    display: grid;
    gap: 10px;
  }
  .field label {
    display: flex;
    gap: 8px;
    align-items: baseline;
  }
  .field .input {
    display: flex;
    align-items: center;
    gap: 6px;
  }
  .field input,
  .field select {
    width: min(320px, 100%);
  }
  .help {
    margin: 2px 0 0;
  }
  .help:empty {
    display: none;
  }
  .src-override {
    color: var(--accent);
  }
  .src-locked {
    color: var(--warn);
  }
  button.link {
    background: none;
    border: none;
    cursor: pointer;
    color: var(--muted);
  }
  textarea {
    width: 100%;
  }
  .actions {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    align-items: center;
  }
  .copy {
    display: flex;
    gap: 6px;
    align-items: center;
    margin-left: auto;
  }
  .warn-text {
    color: var(--warn);
  }
</style>
