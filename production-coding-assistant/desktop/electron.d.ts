declare global {
  interface Window {
    desktopBridge?: {
      getMeta: () => Promise<{ isDev: boolean; backendEntrypoint: string }>;
      onBackendLog: (callback: (message: string) => void) => () => void;
    };
  }
}

export {};
