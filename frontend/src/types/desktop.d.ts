// Ambient typing for the Electron preload bridge (desktop/preload.js).
// Present only in the bundled desktop app; guard usage with optional chaining.

export interface ScistudioDesktopBridge {
  platform: string;
  versions: { electron: string; chrome: string };
  /** #1784: relaunch the app so a fresh interpreter loads updated packages. */
  relaunch: () => Promise<void>;
}

declare global {
  interface Window {
    scistudioDesktop?: ScistudioDesktopBridge;
  }
}

export {};
