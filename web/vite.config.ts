import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 3000,
    strictPort: true,
    proxy: {
      "/api": "http://127.0.0.1:8000",
    },
  },
  preview: { host: "127.0.0.1", port: 3000, strictPort: true },
  test: {
    environment: "jsdom",
    // DiscoveryApp mounts a broad route tree; unrestricted file workers can
    // starve its async navigation check past Vitest's 5 s per-test budget.
    maxWorkers: 2,
    setupFiles: "./src/test/setup.ts",
    globals: true,
    include: ["src/**/*.test.{ts,tsx}"],
    css: true,
  },
});
