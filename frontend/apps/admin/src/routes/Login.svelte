<script lang="ts">
  import { t } from "../lib/i18n.svelte";
  import { session } from "../lib/session.svelte";

  let username = $state("");
  let password = $state("");
  let repeat = $state("");
  let error = $state<string | null>(null);
  let busy = $state(false);

  const me = $derived(session.me);
  const setupMode = $derived(me?.needs_setup ?? false);

  async function submit(event: SubmitEvent): Promise<void> {
    event.preventDefault();
    error = null;
    if (setupMode) {
      if (password.length < 8) return void (error = t("setup.too_short"));
      if (password !== repeat) return void (error = t("setup.mismatch"));
    }
    busy = true;
    try {
      if (setupMode) await session.setup(username, password);
      else await session.login(username, password);
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    } finally {
      busy = false;
    }
  }
</script>

<div class="wrap">
  <form class="panel" onsubmit={submit}>
    <div class="brand">NestrisLTM</div>
    <h1>{setupMode ? t("setup.title") : t("login.title")}</h1>
    {#if setupMode && !me?.can_setup}
      <p class="hint">{t("setup.remote")}</p>
    {:else}
      {#if setupMode}<p class="hint">{t("setup.intro")}</p>{/if}
      <label class="field">
        {t("login.username")}
        <input bind:value={username} autocomplete="username" required minlength={setupMode ? 2 : 1} />
      </label>
      <label class="field">
        {t("login.password")}
        <input
          type="password"
          bind:value={password}
          autocomplete={setupMode ? "new-password" : "current-password"}
          required
        />
      </label>
      {#if setupMode}
        <label class="field">
          {t("setup.repeat")}
          <input type="password" bind:value={repeat} autocomplete="new-password" required />
        </label>
      {/if}
      {#if error}<div class="error-box">{error}</div>{/if}
      <button class="primary" type="submit" disabled={busy}>
        {setupMode ? t("setup.submit") : t("login.submit")}
      </button>
    {/if}
  </form>
</div>

<style>
  .wrap {
    min-height: 100vh;
    display: grid;
    place-items: center;
    padding: 16px;
  }
  form {
    width: min(380px, 100%);
    display: grid;
    gap: 12px;
    padding: 24px;
  }
  .brand {
    color: var(--accent);
    font-weight: 700;
    font-size: 20px;
  }
  h1 {
    margin: 0;
  }
</style>
