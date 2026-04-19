interface ImportMetaEnv {
  readonly VITE_STIMPACT_BASE_URL?: string;
  readonly VITE_STIMPACT_PROJECT_ID?: string;
  readonly VITE_STIMPACT_BROWSER_KEY?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
