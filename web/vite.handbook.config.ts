import {defineConfig,loadEnv} from 'vite';
import react from '@vitejs/plugin-react';
export default defineConfig(()=>{
 const env=loadEnv('development','..','');
 return {plugins:[react()],define:{'import.meta.env.VITE_DISCOVERY_PRODUCT':JSON.stringify('true'),'import.meta.env.VITE_ASSISTANT_CONTEXT_CONTRACT':JSON.stringify('assistant-context-v1'),'import.meta.env.VITE_TRAVEL_CONTENT_CONTRACT':JSON.stringify('place-content-v1'),'import.meta.env.VITE_AMAP_WEB_KEY':JSON.stringify(env.VITE_AMAP_WEB_KEY||env.AMAP_WEB_KEY||''),'import.meta.env.VITE_AMAP_SECURITY_CODE':JSON.stringify(env.VITE_AMAP_SECURITY_CODE||env.AMAP_SECURITY_CODE||'')},server:{host:'127.0.0.1',port:3033,strictPort:true,proxy:{'/api':{target:'http://127.0.0.1:18033',headers:{'X-RoamSync-Access':'handbook-isolated-only'}}}}};
});
