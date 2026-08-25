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

function menuActionClick(sendMenuAction, action) {
  return () => sendMenuAction(action);
}

// `platform` (process.platform) and `appName` (app.name) are injected so the
// template stays unit-testable without Electron. `sendMenuAction` forwards an
// action id to the renderer; `checkForUpdates` runs the OTA update check and
// `showAbout` opens the #2097 About dialog (desktop/main.js owns all three).
function buildMenuTemplate({ platform, appName, sendMenuAction, checkForUpdates, showAbout }) {
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

module.exports = { MENU_ACTION_CHANNEL, MENU_ACTIONS, buildMenuTemplate };
