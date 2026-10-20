import { defineConfig, mergeConfig, loadEnv } from 'vite';
import base from './vite.config';
// Local acceptance only: reuse existing browser-provider settings in memory.
// No credentials are copied into this checkout or written to evidence logs.
const provider = loadEnv('development', 'E:/Study/RoamSync', 'AMAP_');
export default mergeConfig(base, defineConfig({
  define: { 'import.meta.env.VITE_DISCOVERY_PRODUCT': JSON.stringify('true'),
    'import.meta.env.VITE_AMAP_WEB_KEY': JSON.stringify(provider.AMAP_WEB_KEY || ''),
    'import.meta.env.VITE_AMAP_SECURITY_CODE': JSON.stringify(provider.AMAP_SECURITY_CODE || ''),
    'import.meta.env.VITE_TRAVEL_CONTENT_CONTRACT': JSON.stringify('place-content-v1'),
    'import.meta.env.VITE_ASSISTANT_CONTEXT_CONTRACT': JSON.stringify('assistant-context-v1') },
  server: { host: '127.0.0.1', port: 3022, strictPort: true,
    proxy: { '/api': { target: 'http://127.0.0.1:18022', changeOrigin: true, headers: { 'x-roamsync-access': 'evidence-local-test-only' } } } }
}));
