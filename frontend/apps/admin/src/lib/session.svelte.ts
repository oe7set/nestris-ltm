// Who is signed in; drives the login/setup gate in App.svelte.

import { api, dbUnavailableState, setDbUnavailableHandler, setUnauthorizedHandler } from "./api";
import type { Me } from "./types";

class Session {
  me = $state<Me | null>(null);
  error = $state<string | null>(null);
  /** Database state while the server answers "database unavailable" (else null). */
  dbState = $state<string | null>(null);

  constructor() {
    setUnauthorizedHandler(() => {
      if (this.me) this.me = { ...this.me, authenticated: false };
    });
    setDbUnavailableHandler((state) => {
      this.dbState = state;
    });
  }

  async refresh(): Promise<void> {
    try {
      this.me = await api<Me>("/api/auth/me");
      this.error = null;
      this.dbState = null;
    } catch (e) {
      this.dbState = dbUnavailableState(e);
      this.error = e instanceof Error ? e.message : String(e);
    }
  }

  /** Full admin (not a helper login). */
  get isAdmin(): boolean {
    return this.me?.role !== "helper";
  }

  /** The database is back (seen by the problem screen): clear the banner. */
  dbRecovered(): void {
    this.dbState = null;
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
