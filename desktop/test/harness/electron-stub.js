"use strict";

// #2280 (AU1 P2-4): a minimal stand-in for the `electron` module, so the real
// desktop/main.js can be driven from plain Node by run-scenario.js. It records
// what main.js does with windows, the tray, menus, dialogs, the clipboard,
// relaunch and quit; it launches nothing.
//
// Knobs a scenario sets on `state`:
//   pick                  value (or function returning a promise) the splash
//                         picker resolves with
//   pickerPresent         whether the splash exposes the picker function
//   splashLoad            "ok" | "fail" (did-fail-load) | "hang" (never loads)
//   connectionPageScript  whether the connection page's script runs and sends
//                         its first `get-state` (connection.html does, on load)
//   mainPreloadError      the main window's preload throws (#2179)
//   dialogResponse        button index every message box answers with
//                         (every message box's options are kept in `dialogs`)
//   backendAliveProbe     called at app.relaunch() to record backend liveness

const { EventEmitter } = require("events");
const path = require("path");

const { CONNECTION_ACTION_CHANNEL } = require("../../background-mode");

const state = {
  userData: null,
  pick: null,
  pickerPresent: true,
  splashLoad: "ok",
  connectionPageScript: true,
  mainPreloadError: false,
  dialogResponse: 0,
  dialogCalls: 0,
  dialogs: [],
  jsCalls: [],
  relaunches: [],
  externals: [],
  backendAliveProbe: null
};

const handlers = {};
const ipcMain = {
  handlers,
  handle(channel, fn) {
    handlers[channel] = fn;
  }
};

function executeJavaScript(code) {
  state.jsCalls.push(code);
  if (code.includes("typeof window.__scistudioSplashPickMode")) {
    return Promise.resolve(state.pickerPresent);
  }
  if (code.includes("window.__scistudioSplashPickMode(")) {
    return typeof state.pick === "function" ? state.pick() : Promise.resolve(state.pick);
  }
  if (code.includes("__scistudioSplashStatus")) {
    return Promise.resolve(undefined);
  }
  // pageHasRendered, and anything else asking "did it work"
  return Promise.resolve(true);
}

class WebContents extends EventEmitter {
  constructor(win) {
    super();
    this.win = win;
    this.sent = [];
    this.loading = true;
  }
  isLoading() {
    return this.loading;
  }
  executeJavaScript(code) {
    if (this.win && this.win.destroyed) {
      return Promise.reject(new Error("WebContents was destroyed"));
    }
    return executeJavaScript(code);
  }
  send(channel, payload) {
    this.sent.push({ channel, payload });
  }
  setWindowOpenHandler(fn) {
    this.windowOpenHandler = fn;
  }
}

class App extends EventEmitter {
  constructor() {
    super();
    this.name = "SciStudio";
    this.isPackaged = false;
    this.readyPromise = new Promise((resolve) => {
      this.readyResolve = resolve;
    });
    this.exited = null;
    this.quitCalled = 0;
    this.quitting = false;
    this.lockData = null;
  }
  whenReady() {
    return this.readyPromise;
  }
  isReady() {
    return true;
  }
  getPath(name) {
    return name === "userData" ? state.userData : path.join(state.userData, name);
  }
  requestSingleInstanceLock(data) {
    this.lockData = data;
    return true;
  }
  relaunch(options) {
    state.relaunches.push({
      options: options === undefined ? "default" : options,
      backendAlive: state.backendAliveProbe ? state.backendAliveProbe() : null
    });
  }
  exit(code) {
    this.exited = code;
  }
  // Like Electron: before-quit, then every window closes without a
  // window-all-closed event. A before-quit listener can prevent the quit
  // (#2327: main.js does while the backend stops), and a later quit() emits
  // before-quit again. `quitting` turns true only once a quit goes through.
  quit() {
    this.quitCalled += 1;
    if (this.quitting) {
      return;
    }
    let prevented = false;
    this.emit("before-quit", {
      preventDefault() {
        prevented = true;
      }
    });
    if (prevented) {
      return;
    }
    this.quitting = true;
    for (const window of BrowserWindow.getAllWindows()) {
      window.close();
    }
  }
}

const app = new App();

class BrowserWindow extends EventEmitter {
  constructor(opts) {
    super();
    this.opts = opts;
    this.webContents = new WebContents(this);
    this.destroyed = false;
    this.visible = false;
    this.menuRemoved = false;
    BrowserWindow.all.push(this);
  }
  static getAllWindows() {
    return BrowserWindow.all.filter((w) => !w.destroyed);
  }
  // Nothing has focus in a headless run.
  static getFocusedWindow() {
    return null;
  }
  get preloadPath() {
    return String((this.opts.webPreferences || {}).preload || "");
  }
  loadFile(file) {
    this.loaded = file;
    if (file.endsWith(`${path.sep}splash.html`)) {
      if (state.splashLoad === "hang") {
        return;
      }
      if (state.splashLoad === "fail") {
        setImmediate(() => {
          this.webContents.loading = false;
          this.webContents.emit("did-fail-load", {}, -6, "ERR_FILE_NOT_FOUND", file);
        });
        return;
      }
    }
    this.finishLoad();
  }
  loadURL(url) {
    this.loaded = url;
    this.finishLoad();
  }
  finishLoad() {
    setImmediate(() => {
      if (this.destroyed) {
        return;
      }
      if (state.mainPreloadError && this.preloadPath.endsWith(`${path.sep}preload.js`)) {
        this.webContents.emit("preload-error", {}, this.preloadPath, new Error("Cannot find module './x'"));
      }
      this.webContents.loading = false;
      this.webContents.emit("did-finish-load");
      this.emit("ready-to-show");
      // connection.html asks for its state as soon as its script runs.
      if (state.connectionPageScript && String(this.loaded).endsWith(`${path.sep}connection.html`)) {
        const handler = handlers[CONNECTION_ACTION_CHANNEL];
        if (handler) {
          Promise.resolve(handler({ sender: this.webContents }, "get-state")).catch(() => {});
        }
      }
    });
  }
  show() {
    this.visible = true;
  }
  hide() {
    this.visible = false;
  }
  focus() {}
  restore() {}
  isMinimized() {
    return false;
  }
  isVisible() {
    return this.visible;
  }
  isDestroyed() {
    return this.destroyed;
  }
  removeMenu() {
    this.menuRemoved = true;
  }
  close() {
    if (this.destroyed) {
      return;
    }
    this.destroyed = true;
    this.emit("closed");
    if (!app.quitting && BrowserWindow.getAllWindows().length === 0) {
      app.emit("window-all-closed");
    }
  }
}
BrowserWindow.all = [];

const trays = [];
class Tray extends EventEmitter {
  constructor(image) {
    super();
    this.image = image;
    this.menu = null;
    trays.push(this);
  }
  setToolTip(text) {
    this.tooltip = text;
  }
  setContextMenu(menu) {
    this.menu = menu;
  }
  isDestroyed() {
    return false;
  }
}

const Menu = {
  current: null,
  buildFromTemplate: (template) => ({ template }),
  setApplicationMenu: (menu) => {
    Menu.current = menu;
  }
};

const clipboard = {
  text: null,
  writeText(text) {
    clipboard.text = text;
  }
};

const dialog = {
  async showMessageBox(...args) {
    state.dialogCalls += 1;
    state.dialogs.push(args[args.length - 1]);
    return { response: state.dialogResponse };
  }
};

const nativeImage = {
  createFromPath: (p) => ({
    path: p,
    template: false,
    setTemplateImage(value) {
      this.template = value;
    }
  })
};

module.exports = {
  state,
  app,
  BrowserWindow,
  Menu,
  Tray,
  trays,
  clipboard,
  dialog,
  ipcMain,
  nativeImage,
  nativeTheme: { shouldUseDarkColors: false },
  session: { defaultSession: { clearCache: async () => {} } },
  shell: {
    openPath: async () => "",
    openExternal: async (url) => {
      state.externals.push(url);
      return "";
    }
  }
};
