import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Isolated development only. Production remains built from canonical Compose.
export default defineConfig({
  plugins: [react()],
  define: { "import.meta.env.VITE_DISCOVERY_PRODUCT": JSON.stringify("true"), "import.meta.env.VITE_ASSISTANT_CONTEXT_CONTRACT": JSON.stringify("assistant-context-v1"), "import.meta.env.VITE_TRAVEL_CONTENT_CONTRACT": JSON.stringify("place-content-v1") },
  server: { host: "127.0.0.1", port: 3020, strictPort: true,
    fs: { deny: [".env", ".env.*", "**/*.{pem,crt}"] }, proxy: { "/api": "http://127.0.0.1:18020" } },
});
