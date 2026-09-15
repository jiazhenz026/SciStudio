const { contextBridge, ipcRenderer } = require("electron");

// Sandboxed preloads (desktop/main.js sets `sandbox: true`) may only require
// Electron's restricted built-in set, so this channel cannot be imported from
// ./menu — a relative require would abort the preload before the bridge is
// exposed. Keep the literal in sync with MENU_ACTION_CHANNEL in desktop/menu.js.
const MENU_ACTION_CHANNEL = "scistudio:menu-action";
// Keep in sync with INSTALLER_PROGRESS_CHANNEL in desktop/main.js (#2396).
const INSTALLER_PROGRESS_CHANNEL = "scistudio:installer-progress";

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
  // #2361: links inside rendered project markdown must reach the user's default
  // browser. window.open would ask Electron for a child BrowserWindow the main
  // window has no handler for, so the renderer asks the main process, which
  // validates the scheme and forwards to shell.openExternal.
  openExternal: (url) => ipcRenderer.invoke("scistudio:open-external", url),
  // #2396: install the next installer from inside the app. The page asks; the
  // main process owns the manifest, the download, the native confirmation and
  // the install. The reinstall notice feature-detects this object and falls
  // back to its copyable address without it.
  installer: {
    getOffer: () => ipcRenderer.invoke("scistudio:installer-offer"),
    download: () => ipcRenderer.invoke("scistudio:installer-download"),
    install: () => ipcRenderer.invoke("scistudio:installer-install"),
    openReleasePage: () => ipcRenderer.invoke("scistudio:installer-open-release-page"),
    // Subscribe to { received, total } byte counts; returns an unsubscribe function.
    onProgress: (callback) => {
      const listener = (_event, progress) => callback(progress);
      ipcRenderer.on(INSTALLER_PROGRESS_CHANNEL, listener);
      return () => ipcRenderer.removeListener(INSTALLER_PROGRESS_CHANNEL, listener);
    }
  },
  // Application-menu actions (desktop/menu.js). Subscribe with a callback that
  // receives the action id; returns an unsubscribe function. The frontend
  // dispatches these in App.parts/useDesktopMenuActions.ts.
  onMenuAction: (callback) => {
    const listener = (_event, action) => callback(action);
    ipcRenderer.on(MENU_ACTION_CHANNEL, listener);
    return () => ipcRenderer.removeListener(MENU_ACTION_CHANNEL, listener);
  }
});
