const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("scistudioDesktop", {
  platform: process.platform,
  versions: {
    electron: process.versions.electron,
    chrome: process.versions.chrome
  },
  // #1784: the in-app Package Manager applies a staged package update by asking
  // the main process to relaunch, so a fresh Python interpreter imports the new
  // package code (already-imported modules are not re-imported in-process).
  relaunch: () => ipcRenderer.invoke("scistudio:relaunch")
});
