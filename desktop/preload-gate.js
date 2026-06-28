// #1848: preload for the alpha activation gate window (resources/alpha-gate.html).
// Alpha-only; removed in beta together with the rest of the gate.
const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("scistudioAlphaGate", {
  // Machine fingerprint + whether a public key is configured in this build.
  getInfo: () => ipcRenderer.invoke("scistudio:alpha-gate-info"),
  // Verify + persist a pasted token. Resolves { ok, reason }.
  activate: (token) => ipcRenderer.invoke("scistudio:alpha-activate", token),
  // Copy the fingerprint to the clipboard via the main process.
  copy: (text) => ipcRenderer.invoke("scistudio:alpha-copy", text),
  // Give up and quit the app.
  quit: () => ipcRenderer.invoke("scistudio:alpha-quit")
});
