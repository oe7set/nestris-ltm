// Who is signed in; drives the login/setup gate in App.svelte.

import { api, setUnauthorizedHandler } from "./api";
import type { Me } from "./types";

class Session {
  me = $state<Me | null>(null);
  error = $state<string | null>(null);

  constructor() {
    setUnauthorizedHandler(() => {
      if (this.me) this.me = { ...this.me, authenticated: false };
    });
  }

  async refresh(): Promise<void> {
    try {
      this.me = await api<Me>("/api/auth/me");
      this.error = null;
    } catch (e) {
      this.error = e instanceof Error ? e.message : String(e);
    }
  }

  async login(username: string, password: string, remember = true): Promise<void> {
    await api("/api/auth/login", { method: "POST", body: { username, password, remember } });
    await this.refresh();
  }

  async setup(username: string, password: string): Promise<void> {
    await api("/api/auth/setup", { method: "POST", body: { username, password } });
    await this.refresh();
  }

  async logout(): Promise<void> {
    await api("/api/auth/logout", { method: "POST" });
    await this.refresh();
  }
}

export const session = new Session();
