import { mergeConfig } from "vite";
import base from "./vite.config";

// The real-provider acceptance runtime owns separate data and API port.
export default mergeConfig(base, {
  server: { port: 3001, proxy: { "/api": "http://127.0.0.1:8001" } },
});
