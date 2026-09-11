"use strict";

// Application menu for the desktop shell.
//
// The default Electron menu only offered File > Exit; this template replaces
// it with the app-level entries the owner asked for: project navigation and
// save actions under File, the in-app Package Manager under Packages, and the
// Learning Center plus update check under Help.
//
// Most entries are frontend actions: the main process cannot reach the React
// store, so menu clicks are forwarded to the renderer over
// MENU_ACTION_CHANNEL. The preload bridge exposes them as
// window.scistudioDesktop.onMenuAction (desktop/preload.js) and the frontend
// dispatches them in App.parts/useDesktopMenuActions.ts. Keep the action ids
// below in sync with ScistudioDesktopMenuAction in frontend/src/types/desktop.d.ts.
//
// #2280 adds two shell-level entries that never reach the renderer: the
// External AI connection window, and the Startup Mode choice (ask at every
// launch, or always start in one mode). The tray menu of external-AI mode is
// built here too, so both menus stay pure and unit-testable.

const { STARTUP_SETTINGS } = require("./background-mode");

// Also declared as a literal in desktop/preload.js — the sandboxed preload
// cannot require this file, so keep the two in sync.
const MENU_ACTION_CHANNEL = "scistudio:menu-action";

const MENU_ACTIONS = Object.freeze([
  "projects-home",
  "new-project",
  "save",
  "save-as",
  "bring-in-my-work",
  "package-manager",
  "learning-center",
]);

const STARTUP_MODE_ITEMS = Object.freeze([
  { setting: STARTUP_SETTINGS.ASK, label: "Ask at Every Launch" },
  { setting: STARTUP_SETTINGS.DESKTOP, label: "Always Open the Desktop App" },
  { setting: STARTUP_SETTINGS.EXTERNAL_AI, label: "Always Run for External AI" },
]);

function menuActionClick(sendMenuAction, action) {
  return () => sendMenuAction(action);
}

// #2280: the remembered launch choice stays changeable after "don't ask
// again" (owner decision 1). Radio items: exactly one is checked, and clicking
// one hands its setting to main.js, which persists it and rebuilds the menus.
function buildStartupModeSubmenu(startupSetting, setStartupSetting) {
  return STARTUP_MODE_ITEMS.map(({ setting, label }) => ({
    label,
    type: "radio",
    checked: startupSetting === setting,
    click: () => setStartupSetting(setting),
  }));
}

// `platform` (process.platform) and `appName` (app.name) are injected so the
// template stays unit-testable without Electron. `sendMenuAction` forwards an
// action id to the renderer; `checkForUpdates` runs the OTA update check and
// `showAbout` opens the #2097 About dialog; `showConnectionWindow`,
// `startupSetting` and `setStartupSetting` serve #2280 (desktop/main.js owns
// all of them).
function buildMenuTemplate({
  platform,
  appName,
  sendMenuAction,
  checkForUpdates,
  showAbout,
  showConnectionWindow,
  startupSetting = STARTUP_SETTINGS.ASK,
  setStartupSetting,
}) {
  const isMac = platform === "darwin";
  const send = (action) => menuActionClick(sendMenuAction, action);
  // #2097: About reports the effective (post-OTA-patch) build, not the
  // installer baseline the default menu would show.
  const about = { label: "About SciStudio", click: () => showAbout() };

  const fileSubmenu = [
    { label: "Projects Home", click: send("projects-home") },
    { label: "New Project…", accelerator: "CmdOrCtrl+N", click: send("new-project") },
    { type: "separator" },
    // Save accelerators mirror the renderer's own keybindings
    // (App.parts/useAppKeyboardShortcuts.ts). The menu accelerator wins over
    // the in-page listener in the desktop shell, so the action arrives here.
    { label: "Save", accelerator: "CmdOrCtrl+S", click: send("save") },
    { label: "Save As…", accelerator: "CmdOrCtrl+Shift+S", click: send("save-as") },
    { type: "separator" },
    { label: "Bring In My Work…", click: send("bring-in-my-work") },
    { type: "separator" },
    // #2280: in desktop mode this switches the running app to external-AI
    // mode (tray, connection window, stays resident); in external-AI mode it
    // reopens the connection window.
    { label: "External AI Connection…", click: () => showConnectionWindow() },
    {
      label: "Startup Mode",
      submenu: buildStartupModeSubmenu(startupSetting, setStartupSetting),
    },
    { type: "separator" },
    ...(isMac ? [] : [about, { type: "separator" }]),
    isMac ? { role: "close" } : { role: "quit", label: "Exit" },
  ];

  const helpSubmenu = [
    { label: "Learning Center", click: send("learning-center") },
    { type: "separator" },
    { label: "Check for Updates…", click: () => checkForUpdates() },
  ];

  const template = [
    { label: "File", submenu: fileSubmenu },
    // The role menus keep text editing (copy/paste), zoom, reload, and window
    // management working; replacing the default menu wholesale means the
    // standard roles have to be restored explicitly.
    { role: "editMenu" },
    { role: "viewMenu" },
    { role: "windowMenu" },
    {
      label: "Packages",
      submenu: [{ label: "Package Manager…", click: send("package-manager") }],
    },
    { label: "Help", submenu: helpSubmenu },
  ];
  if (isMac) {
    template.unshift({
      label: appName,
      submenu: [
        about,
        { type: "separator" },
        { role: "services" },
        { type: "separator" },
        { role: "hide" },
        { role: "hideOthers" },
        { role: "unhide" },
        { type: "separator" },
        { role: "quit" },
      ],
    });
  }
  return template;
}

// #2280: the tray menu, present only in external-AI mode (owner decision 2).
// `view` is background-mode.connectionView(); the address and the actions that
// need a working service are enabled only while it is running.
function buildTrayMenuTemplate({
  view,
  showConnectionWindow,
  copyAddress,
  openDesktopWindow,
  setStartupSetting,
  stopAndQuit,
}) {
  const statusLine = view.address
    ? `Service: ${view.label} at ${view.address}`
    : `Service: ${view.label}`;
  return [
    { label: statusLine, enabled: false },
    { type: "separator" },
    { label: "Open Connection Window", click: () => showConnectionWindow() },
    { label: "Copy Address", enabled: view.canCopy, click: () => copyAddress() },
    { label: "Open in Desktop Mode", enabled: view.canOpenDesktop, click: () => openDesktopWindow() },
    { type: "separator" },
    {
      label: "Startup Mode",
      submenu: buildStartupModeSubmenu(view.startupSetting, setStartupSetting),
    },
    { type: "separator" },
    { label: "Stop and Quit", click: () => stopAndQuit() },
  ];
}

module.exports = {
  MENU_ACTION_CHANNEL,
  MENU_ACTIONS,
  STARTUP_MODE_ITEMS,
  buildMenuTemplate,
  buildStartupModeSubmenu,
  buildTrayMenuTemplate,
};
