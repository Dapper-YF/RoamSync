import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Local isolated preview only, never production port or proxy.
export default defineConfig({
  plugins: [react()],
  server: { host: "127.0.0.1", port: 3019, strictPort: true,
    fs: { deny: [".env", ".env.*", "**/*.{pem,crt}"] },
    proxy: { "/api": "http://127.0.0.1:18019" } },
});
