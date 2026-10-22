import {defineConfig,loadEnv} from 'vite';
import react from '@vitejs/plugin-react';

// Local acceptance only; the token is injected by Vite's server, never client code.
const publicMaps=loadEnv('development','E:/Study/RoamSync','AMAP_');
export default defineConfig({
 plugins:[react()],
 define:{'import.meta.env.VITE_DISCOVERY_PRODUCT':JSON.stringify('true'),'import.meta.env.VITE_ASSISTANT_CONTEXT_CONTRACT':JSON.stringify('assistant-context-v1'),'import.meta.env.VITE_TRAVEL_CONTENT_CONTRACT':JSON.stringify('place-content-v1'),'import.meta.env.VITE_AMAP_WEB_KEY':JSON.stringify(publicMaps.AMAP_WEB_KEY||''),'import.meta.env.VITE_AMAP_SECURITY_CODE':JSON.stringify(publicMaps.AMAP_SECURITY_CODE||'')},
 server:{host:'127.0.0.1',port:3042,strictPort:true,proxy:{'/api':{target:'http://127.0.0.1:18042',headers:{'X-RoamSync-Access':'product-c-isolated-only'}}}},
});
