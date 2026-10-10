<script lang="ts">
  import { confirmAsync } from "../lib/confirm.svelte";
  import { session } from "../lib/session.svelte";
  import { copyText } from "../lib/clipboard";
  import { onMount } from "svelte";
  import Modal from "../components/Modal.svelte";
  import DisplaySettings from "../components/settings/DisplaySettings.svelte";
  import TournamentSettings from "../components/settings/TournamentSettings.svelte";
  import { router } from "../lib/router.svelte";
  import { api } from "../lib/api";
  import { dateTime } from "../lib/format";
  import { i18n, t, tDynamic } from "../lib/i18n.svelte";
  import { toasts } from "../lib/toast.svelte";

  interface Admin {
    id: number;
    username: string;
    created_at: string;
    last_login_at: string | null;
  }
  interface Token {
    id: number;
    name: string;
    scopes: string[];
    created_at: string;
    last_used_at: string | null;
    revoked_at: string | null;
  }

  // Tabs: general, tournament & scenes, highscore display, access.
  const TABS = ["general", "tournament", "display", "access"] as const;
  type Tab = (typeof TABS)[number];
  const wanted = router.current.query.get("tab");
  let tab = $state<Tab>(TABS.includes(wanted as Tab) ? (wanted as Tab) : "general");
  function setTab(next: Tab): void {
    tab = next;
    router.setQuery({ tab: next === "general" ? null : next });
  }

  let admins = $state<Admin[]>([]);
  let tokens = $state<Token[]>([]);
  let scopes = $state<string[]>([]);
  let newAdmin = $state({ username: "", password: "" });
  let passwordFor = $state<Admin | null>(null);
  let newPassword = $state("");
  let tokenName = $state("");
  let tokenScopes = $state<string[]>(["players:write"]);
  let createdToken = $state<string | null>(null);

  async function load(): Promise<void> {
    try {
      [admins, tokens, scopes] = await Promise.all([
        api<Admin[]>("/api/admins"),
        api<Token[]>("/api/tokens"),
        api<string[]>("/api/tokens/scopes"),
      ]);
    } catch (e) {
      toasts.error(e);
    }
  }

  async function run(fn: () => Promise<unknown>, message?: string): Promise<boolean> {
    try {
      await fn();
      if (message) toasts.ok(message);
      await load();
      return true;
    } catch (e) {
      toasts.error(e);
      return false;
    }
  }

  async function addAdmin(event: SubmitEvent): Promise<void> {
    event.preventDefault();
    if (await run(() => api("/api/admins", { method: "POST", body: newAdmin }), t("common.saved"))) {
      newAdmin = { username: "", password: "" };
    }
  }

  async function createToken(event: SubmitEvent): Promise<void> {
    event.preventDefault();
    try {
      const r = await api<{ token: string }>("/api/tokens", {
        method: "POST",
        body: { name: tokenName, scopes: tokenScopes },
      });
      createdToken = r.token;
      tokenName = "";
      await load();
    } catch (e) {
      toasts.error(e);
    }
  }

  async function copy(text: string): Promise<void> {
    try {
      await copyText(text);
      toasts.ok(t("common.copied"));
    } catch (e) {
      toasts.error(e);
    }
  }

  onMount(() => {
    void load();
  });
</script>

<h1>{t("settings.title")}</h1>

<div class="tabs">
  {#each TABS as name (name)}
    <button class:on={tab === name} onclick={() => setTab(name)}>{tDynamic(`settings.tab_${name}`, name)}</button>
  {/each}
</div>

{#if tab === "tournament"}
  <TournamentSettings />
{:else if tab === "display"}
  <DisplaySettings />
{:else if tab === "general"}
<section class="panel block">
  <h2>{t("settings.language")}</h2>
  <div class="row">
    <button class:primary={i18n.locale === "de"} onclick={() => i18n.set("de")}>Deutsch</button>
    <button class:primary={i18n.locale === "en"} onclick={() => i18n.set("en")}>English</button>
  </div>
</section>
<section class="panel block">
  <h2>{t("nav.updates")}</h2>
  <p class="hint">{t("settings.updates_hint")} <a href="#/updates">{t("nav.updates")} →</a></p>
</section>
{:else}

<section class="panel block">
  <h2>{t("settings.admins")}</h2>
  <table>
    <tbody>
      {#each admins as a (a.id)}
        <tr>
          <td><strong>{a.username}</strong></td>
          <td class="muted small">{t("settings.last_login")}: {dateTime(a.last_login_at, i18n.locale)}</td>
          <td class="actions"><div class="row">
            <button onclick={() => { passwordFor = a; newPassword = ""; }}>{t("settings.change_password")}</button>
            <button
              class="danger"
              disabled={admins.length <= 1}
              onclick={async () => (await confirmAsync({ title: t("settings.delete_admin", { name: a.username }), danger: true, confirmLabel: t("common.delete") })) && run(() => api(`/api/admins/${a.id}`, { method: "DELETE" }))}
            >
              {t("common.delete")}
            </button>
          </div></td>
        </tr>
      {/each}
    </tbody>
  </table>
  <form class="row add" onsubmit={addAdmin}>
    <input placeholder={t("settings.username")} aria-label={t("settings.username")} bind:value={newAdmin.username} required minlength="2" pattern="[A-Za-z0-9._\-]+" autocomplete="off" />
    <input type="password" placeholder={t("settings.password")} aria-label={t("settings.password")} bind:value={newAdmin.password} required minlength="8" autocomplete="new-password" />
    <button type="submit">{t("settings.add_admin")}</button>
  </form>
  {#if session.me?.kind === "session"}
    <div class="row add">
      <span class="hint">{t("settings.logout_all_hint")}</span>
      <span class="spacer"></span>
      <button
        onclick={async () =>
          (await confirmAsync({ title: t("settings.logout_all"), text: t("settings.logout_all_hint") })) &&
          run(() => api("/api/auth/logout-all", { method: "POST" }), t("settings.logout_all_done"))}>{t("settings.logout_all")}</button
      >
    </div>
  {/if}
</section>

<section class="panel block">
  <h2>{t("settings.tokens")}</h2>
  <p class="hint">{t("settings.tokens_hint")}</p>
  <table>
    <tbody>
      {#each tokens as tok (tok.id)}
        <tr class:dim={tok.revoked_at}>
          <td><strong>{tok.name}</strong></td>
          <td>{#each tok.scopes as s (s)}<span class="badge">{s}</span> {/each}</td>
          <td class="muted small">
            {t("settings.last_used")}: {tok.last_used_at ? dateTime(tok.last_used_at, i18n.locale) : t("settings.never")}
          </td>
          <td class="actions">
            {#if tok.revoked_at}
              <span class="badge">{t("settings.revoked")}</span>
            {:else}
              <button
                class="danger"
                onclick={async () =>
                  (await confirmAsync({ title: t("settings.revoke_confirm", { name: tok.name }), text: t("settings.revoke_text"), danger: true, confirmLabel: t("settings.revoke") })) &&
                  run(() => api(`/api/tokens/${tok.id}`, { method: "DELETE" }))}>{t("settings.revoke")}</button
              >
            {/if}
          </td>
        </tr>
      {/each}
    </tbody>
  </table>
  <form class="row add" onsubmit={createToken}>
    <input placeholder={t("settings.token_name")} bind:value={tokenName} required maxlength="64" />
    {#each scopes as s (s)}
      <label class="check"><input type="checkbox" value={s} bind:group={tokenScopes} /> {s}</label>
    {/each}
    <button type="submit" disabled={!tokenScopes.length}>{t("settings.create_token")}</button>
  </form>
</section>
{/if}

{#if passwordFor}
  <Modal title={t("settings.new_password", { name: passwordFor.username })} onclose={() => (passwordFor = null)}>
    <input type="password" bind:value={newPassword} minlength="8" autocomplete="new-password" />
    {#snippet footer()}
      <button onclick={() => (passwordFor = null)}>{t("common.cancel")}</button>
      <button
        class="primary"
        disabled={newPassword.length < 8}
        onclick={async () => {
          if (await run(() => api(`/api/admins/${passwordFor!.id}/password`, { method: "PUT", body: { password: newPassword } }), t("common.saved"))) passwordFor = null;
        }}
      >
        {t("common.save")}
      </button>
    {/snippet}
  </Modal>
{/if}

{#if createdToken}
  <Modal title={t("settings.tokens")} onclose={() => (createdToken = null)}>
    <p>{t("settings.token_created")}</p>
    <div class="row"><code class="mono token">{createdToken}</code><button onclick={() => copy(createdToken!)}>{t("common.copy")}</button></div>
    {#snippet footer()}
      <button class="primary" onclick={() => (createdToken = null)}>{t("common.close")}</button>
    {/snippet}
  </Modal>
{/if}

<style>
  .tabs {
    display: flex;
    gap: 6px;
    margin-bottom: 14px;
    flex-wrap: wrap;
  }
  .tabs button.on {
    border-color: var(--accent);
    color: var(--accent);
  }
  .block {
    margin-bottom: 16px;
  }
  .add {
    margin-top: 12px;
  }
  .actions {
    text-align: right;
  }
  .actions .row {
    justify-content: flex-end;
  }
  tr.dim td {
    opacity: 0.5;
  }
  .token {
    word-break: break-all;
    background: #070b16;
    padding: 6px 8px;
    border-radius: 6px;
    flex: 1;
  }
</style>
