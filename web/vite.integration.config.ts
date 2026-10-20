import { mergeConfig } from "vite";
import unified from "./vite.unified.config";

// Acceptance only: same application and flags, independent API and port.
export default mergeConfig(unified, {
  server: { port: 3021, proxy: { "/api": "http://127.0.0.1:18021" } },
});
