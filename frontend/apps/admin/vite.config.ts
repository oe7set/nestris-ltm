/// <reference types="vitest/config" />
import { svelte } from "@sveltejs/vite-plugin-svelte";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";

// The Python app serves the build from src/nestris_ltm/web/admin.
const outDir = fileURLToPath(new URL("../../../src/nestris_ltm/web/admin", import.meta.url));
// `pnpm dev` proxies the API to a running NestrisLTM (default port 7990).
const backend = process.env.NLTM_BACKEND ?? "http://127.0.0.1:7990";

export default defineConfig({
  plugins: [svelte()],
  build: { outDir, emptyOutDir: true, sourcemap: false },
  server: {
    port: 5173,
    proxy: {
      "/api": backend,
      "/ws": { target: backend, ws: true },
    },
  },
  test: { environment: "node", include: ["src/**/*.test.ts"] },
});
