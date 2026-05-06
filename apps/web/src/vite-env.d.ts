/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE?: string;
  /** MapTiler API key — tiles + geocoding no cliente (PRD: MapLibre + MapTiler) */
  readonly VITE_MAPTILER_API_KEY?: string;
  /** Google Identity Services OAuth client ID (public, browser-side). */
  readonly VITE_GOOGLE_CLIENT_ID?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
