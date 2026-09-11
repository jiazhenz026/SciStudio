const { contextBridge, ipcRenderer } = require("electron");

// #2280: bridge for the external-AI connection window (desktop/connection.html).
//
// Sandboxed preloads may only require Electron's restricted built-in set, so
// these channel names cannot be imported from ./background-mode — a relative
// require would abort the preload before the bridge is exposed (#2179). Keep
// them in sync with CONNECTION_ACTION_CHANNEL / CONNECTION_STATE_CHANNEL in
// desktop/background-mode.js; desktop/test/background-mode.test.js pins them.
const CONNECTION_ACTION_CHANNEL = "scistudio:connection-action";
const CONNECTION_STATE_CHANNEL = "scistudio:connection-state";

contextBridge.exposeInMainWorld("scistudioConnection", {
  // Every action resolves with the current view (see connectionView in
  // desktop/background-mode.js); the main process validates the action name.
  act: (action, payload) => ipcRenderer.invoke(CONNECTION_ACTION_CHANNEL, action, payload),
  // Pushed whenever the service status changes; returns an unsubscribe function.
  onState: (callback) => {
    const listener = (_event, view) => callback(view);
    ipcRenderer.on(CONNECTION_STATE_CHANNEL, listener);
    return () => ipcRenderer.removeListener(CONNECTION_STATE_CHANNEL, listener);
  }
});
