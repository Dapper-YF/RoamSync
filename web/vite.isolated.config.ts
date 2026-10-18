import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { readFileSync } from "node:fs";

// Canonical product code against the already authorized isolated service.
// The private source is server-only and never added to Vite's client defines.
export default defineConfig(() => {
  const path = process.env.ROAMSYNC_ISOLATED_ENV_FILE;
  if (!path) throw Error("Explicit existing isolated environment file required");
  const token = readFileSync(path, "utf8").split(/\r?\n/)
    .find(line => line.startsWith("ROAMSYNC_INTEGRATION_TOKEN="))?.slice("ROAMSYNC_INTEGRATION_TOKEN=".length).trim();
  if (!token) throw Error("Existing isolated service token required");
  return {
    plugins: [react(), { name: "isolated-local-boundary", configureServer(server) {
      server.middlewares.use((req, res, next) => {
        const hosts = ["127.0.0.1:3016", "localhost:3016"];
        if (!hosts.includes(req.headers.host || "") || req.headers["sec-fetch-site"] === "cross-site"
            || (req.headers.origin && !hosts.map(host => `http://${host}`).includes(req.headers.origin))) {
          res.statusCode = 403; res.end("Local preview only"); return;
        }
        next();
      });
    } }],
    server: { host: "127.0.0.1", port: 3016, strictPort: true,
      fs: { deny: [".env", ".env.*", "**/.private-integration/**", "**/*.{crt,pem}"] },
      proxy: { "/api": { target: "http://127.0.0.1:18004", changeOrigin: true,
        configure(proxy) { proxy.on("proxyReq", req => {
          req.removeHeader("X-RoamSync-Access"); req.removeHeader("Authorization");
          req.setHeader("X-RoamSync-Access", token);
        }); },
      } },
    },
  };
});
