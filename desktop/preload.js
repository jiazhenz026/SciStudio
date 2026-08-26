const { contextBridge, ipcRenderer } = require("electron");

// Sandboxed preloads (desktop/main.js sets `sandbox: true`) may only require
// Electron's restricted built-in set, so this channel cannot be imported from
// ./menu — a relative require would abort the preload before the bridge is
// exposed. Keep the literal in sync with MENU_ACTION_CHANNEL in desktop/menu.js.
const MENU_ACTION_CHANNEL = "scistudio:menu-action";

contextBridge.exposeInMainWorld("scistudioDesktop", {
  platform: process.platform,
  versions: {
    electron: process.versions.electron,
    chrome: process.versions.chrome
  },
  // #1784: the in-app Package Manager applies a staged package update by asking
  // the main process to relaunch, so a fresh Python interpreter imports the new
  // package code (already-imported modules are not re-imported in-process).
  relaunch: () => ipcRenderer.invoke("scistudio:relaunch"),
  // Application-menu actions (desktop/menu.js). Subscribe with a callback that
  // receives the action id; returns an unsubscribe function. The frontend
  // dispatches these in App.parts/useDesktopMenuActions.ts.
  onMenuAction: (callback) => {
    const listener = (_event, action) => callback(action);
    ipcRenderer.on(MENU_ACTION_CHANNEL, listener);
    return () => ipcRenderer.removeListener(MENU_ACTION_CHANNEL, listener);
  }
});
