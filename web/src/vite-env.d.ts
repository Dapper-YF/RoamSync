/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_AMAP_WEB_KEY?: string;
  readonly VITE_AMAP_SECURITY_CODE?: string;
  readonly VITE_ASSISTANT_CONTEXT_CONTRACT?: "product-preview" | "assistant-context-v1";
  readonly VITE_TRAVEL_CONTENT_CONTRACT?: "product-preview" | "place-content-v1";
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

interface Window {
  _AMapSecurityConfig?: { securityJsCode?: string; serviceHost?: string };
}
