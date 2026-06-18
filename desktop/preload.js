const { contextBridge } = require("electron");

contextBridge.exposeInMainWorld("scistudioDesktop", {
  platform: process.platform,
  versions: {
    electron: process.versions.electron,
    chrome: process.versions.chrome
  }
});
