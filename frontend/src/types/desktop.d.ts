// Ambient typing for the Electron preload bridge (desktop/preload.js).
// Present only in the bundled desktop app; guard usage with optional chaining.

/**
 * Action ids sent by the desktop application menu (desktop/menu.js) over the
 * "scistudio:menu-action" IPC channel. Keep in sync with MENU_ACTIONS there.
 */
export type ScistudioDesktopMenuAction =
  | "projects-home"
  | "new-project"
  | "save"
  | "save-as"
  | "bring-in-my-work"
  | "package-manager"
  | "learning-center";

export interface ScistudioDesktopBridge {
  platform: string;
  versions: { electron: string; chrome: string };
  /** #1784: relaunch the app so a fresh interpreter loads updated packages. */
  relaunch: () => Promise<void>;
  /** Capture only the owning SciStudio window, including iframe compositor pixels. */
  captureGui?: (request: {
    rect: { x: number; y: number; width: number; height: number };
  }) => Promise<{
    png_base64: string;
    width: number;
    height: number;
  }>;
  /**
   * Open an external URL in the user's default application via the main
   * process's validated `shell.openExternal` handler. Optional: shells built
   * before #2361 predate the bridge, and the browser build has none; callers
   * fall back to `window.open`.
   */
  openExternal?: (url: string) => Promise<void>;
  /**
   * Subscribe to application-menu actions. Returns an unsubscribe function.
   * Only present in the desktop shell; absent in the browser build.
   */
  onMenuAction: (callback: (action: ScistudioDesktopMenuAction) => void) => () => void;
}

declare global {
  interface Window {
    scistudioDesktop?: ScistudioDesktopBridge;
  }
}

export {};
