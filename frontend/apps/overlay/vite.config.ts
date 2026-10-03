/// <reference types="vitest/config" />
import { svelte } from "@sveltejs/vite-plugin-svelte";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";

// Served by NestrisLTM: the page at /o/<scene>, the bundle under /overlay-assets/.
const outDir = fileURLToPath(new URL("../../../src/nestris_ltm/web/overlay", import.meta.url));
const backend = process.env.NLTM_BACKEND ?? "http://127.0.0.1:7990";

export default defineConfig({
  base: "/overlay-assets/",
  plugins: [svelte()],
  build: { outDir, emptyOutDir: true, sourcemap: false },
  server: {
    port: 5174,
    proxy: {
      "/api": backend,
      "/kiosk": backend,
      "/ws": { target: backend, ws: true },
    },
  },
  test: { environment: "node", include: ["src/**/*.test.ts"] },
});
