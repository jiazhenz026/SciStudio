"use strict";

// Unit tests for the application-menu template (desktop/menu.js).
// Run with: npm --prefix desktop test   (Node built-in runner).

const test = require("node:test");
const assert = require("node:assert/strict");
const {
  MENU_ACTIONS,
  STARTUP_MODE_ITEMS,
  buildMenuTemplate,
  buildTrayMenuTemplate,
} = require("../menu");
const { STARTUP_SETTINGS, connectionView } = require("../background-mode");

function makeDeps(platform, startupSetting = STARTUP_SETTINGS.ASK) {
  const sent = [];
  const settings = [];
  let updateChecks = 0;
  let aboutShown = 0;
  let connectionShown = 0;
  const template = buildMenuTemplate({
    platform,
    appName: "SciStudio",
    sendMenuAction: (action) => sent.push(action),
    checkForUpdates: () => {
      updateChecks += 1;
    },
    showAbout: () => {
      aboutShown += 1;
    },
    showConnectionWindow: () => {
      connectionShown += 1;
    },
    startupSetting,
    setStartupSetting: (setting) => settings.push(setting),
  });
  return {
    sent,
    settings,
    updateChecks: () => updateChecks,
    aboutShown: () => aboutShown,
    connectionShown: () => connectionShown,
    template,
  };
}

function topLevel(template, label) {
  const entry = template.find((item) => item.label === label);
  assert.ok(entry, `expected a top-level "${label}" menu`);
  return entry;
}

function clickItem(submenu, label) {
  const item = submenu.find((entry) => entry.label === label);
  assert.ok(item, `expected a "${label}" menu item`);
  assert.equal(typeof item.click, "function", `"${label}" must be clickable`);
  item.click();
}

test("File menu offers projects home, new project, save actions, bring in my work, and the #2280 entries", () => {
  const { sent, template } = makeDeps("win32");
  const file = topLevel(template, "File");
  const labels = file.submenu.map((item) => item.label || item.type);

  assert.deepEqual(labels, [
    "Projects Home",
    "New Project…",
    "separator",
    "Save",
    "Save As…",
    "separator",
    "Bring In My Work…",
    "separator",
    "External AI Connection…",
    "Startup Mode",
    "separator",
    "About SciStudio",
    "separator",
    "Exit",
  ]);

  clickItem(file.submenu, "Projects Home");
  clickItem(file.submenu, "New Project…");
  clickItem(file.submenu, "Save");
  clickItem(file.submenu, "Save As…");
  clickItem(file.submenu, "Bring In My Work…");
  assert.deepEqual(sent, [
    "projects-home",
    "new-project",
    "save",
    "save-as",
    "bring-in-my-work",
  ]);
});

test("Packages menu opens the in-app Package Manager", () => {
  const { sent, template } = makeDeps("win32");
  const packages = topLevel(template, "Packages");
  clickItem(packages.submenu, "Package Manager…");
  assert.deepEqual(sent, ["package-manager"]);
});

test("Help menu opens the Learning Center and runs the update check", () => {
  const { sent, updateChecks, template } = makeDeps("linux");
  const help = topLevel(template, "Help");
  clickItem(help.submenu, "Learning Center");
  clickItem(help.submenu, "Check for Updates…");
  assert.deepEqual(sent, ["learning-center"]);
  assert.equal(updateChecks(), 1);
});

test("standard role menus stay available (edit/view/window)", () => {
  const { template } = makeDeps("win32");
  const roles = template.map((item) => item.role).filter(Boolean);
  assert.ok(roles.includes("editMenu"));
  assert.ok(roles.includes("viewMenu"));
  assert.ok(roles.includes("windowMenu"));
});

test("macOS gets the app menu with About, and Close instead of Exit", () => {
  const { aboutShown, template } = makeDeps("darwin");
  const appMenu = template[0];
  assert.equal(appMenu.label, "SciStudio");
  clickItem(appMenu.submenu, "About SciStudio");
  assert.equal(aboutShown(), 1);
  const file = topLevel(template, "File");
  const last = file.submenu[file.submenu.length - 1];
  assert.equal(last.role, "close");
  // About lives in the app menu on macOS, not in File.
  assert.ok(!file.submenu.some((item) => item.label === "About SciStudio"));
});

test("About opens the #2097 dialog from the File menu on Windows/Linux", () => {
  const { aboutShown, template } = makeDeps("win32");
  clickItem(topLevel(template, "File").submenu, "About SciStudio");
  assert.equal(aboutShown(), 1);
});

test("Save accelerators mirror the renderer keybindings", () => {
  const { template } = makeDeps("win32");
  const file = topLevel(template, "File");
  assert.equal(
    file.submenu.find((item) => item.label === "Save").accelerator,
    "CmdOrCtrl+S",
  );
  assert.equal(
    file.submenu.find((item) => item.label === "Save As…").accelerator,
    "CmdOrCtrl+Shift+S",
  );
});

test("every forwarded action id is a known MENU_ACTIONS entry", () => {
  // Guards the contract with frontend/src/types/desktop.d.ts
  // (ScistudioDesktopMenuAction): clicking every clickable item must only
  // ever produce ids the frontend knows how to dispatch. The #2280 entries are
  // shell-level and must never reach the renderer.
  const { sent, template } = makeDeps("win32");
  const walk = (items) => {
    for (const item of items || []) {
      if (item.submenu) walk(item.submenu);
      if (item.click) item.click();
    }
  };
  walk(template);
  assert.ok(sent.length > 0);
  for (const action of sent) {
    assert.ok(MENU_ACTIONS.includes(action), `unknown menu action "${action}"`);
  }
});

// --------------------------------------------------------------------------- //
// #2280: launch modes.
// --------------------------------------------------------------------------- //

test("File > External AI Connection opens the connection window on every platform", () => {
  for (const platform of ["win32", "darwin", "linux"]) {
    const { connectionShown, sent, template } = makeDeps(platform);
    clickItem(topLevel(template, "File").submenu, "External AI Connection…");
    assert.equal(connectionShown(), 1, platform);
    assert.deepEqual(sent, [], "it is a shell action, not a renderer action");
  }
});

test("File > Startup Mode is a radio group that reflects the remembered choice", () => {
  for (const setting of Object.values(STARTUP_SETTINGS)) {
    const { template } = makeDeps("win32", setting);
    const startup = topLevel(template, "File").submenu.find((item) => item.label === "Startup Mode");
    assert.ok(startup, "expected a Startup Mode submenu");
    assert.deepEqual(
      startup.submenu.map((item) => item.label),
      ["Ask at Every Launch", "Always Open the Desktop App", "Always Run for External AI"],
    );
    assert.ok(startup.submenu.every((item) => item.type === "radio"));
    const checked = startup.submenu.filter((item) => item.checked);
    assert.equal(checked.length, 1, "exactly one radio item is checked");
    assert.equal(STARTUP_MODE_ITEMS.find((i) => i.label === checked[0].label).setting, setting);
  }
});

test("File > Startup Mode hands the chosen setting to main.js (owner decision 1)", () => {
  const { settings, template } = makeDeps("linux", STARTUP_SETTINGS.EXTERNAL_AI);
  const startup = topLevel(template, "File").submenu.find((item) => item.label === "Startup Mode");
  clickItem(startup.submenu, "Ask at Every Launch");
  clickItem(startup.submenu, "Always Open the Desktop App");
  assert.deepEqual(settings, [STARTUP_SETTINGS.ASK, STARTUP_SETTINGS.DESKTOP]);
});

function makeTray(viewInput) {
  const calls = [];
  const view = connectionView(viewInput);
  const template = buildTrayMenuTemplate({
    view,
    showConnectionWindow: () => calls.push("show-connection"),
    copyAddress: () => calls.push("copy"),
    openDesktopWindow: () => calls.push("open-desktop"),
    setStartupSetting: (setting) => calls.push(`startup:${setting}`),
    stopAndQuit: () => calls.push("stop-and-quit"),
  });
  return { calls, template };
}

test("tray menu carries the owner's five entries plus the Startup Mode choice", () => {
  const { template } = makeTray({ status: "running", address: "http://127.0.0.1:51234" });
  const labels = template.map((item) => item.label || item.type);
  assert.deepEqual(labels, [
    "Service: Running at http://127.0.0.1:51234",
    "separator",
    "Open Connection Window",
    "Copy Address",
    "Open in Desktop Mode",
    "separator",
    "Startup Mode",
    "separator",
    "Stop and Quit",
  ]);
  // The status line is information, not an action.
  assert.equal(template[0].enabled, false);
});

test("tray menu actions reach main.js", () => {
  const { calls, template } = makeTray({ status: "running", address: "http://127.0.0.1:51234" });
  clickItem(template, "Open Connection Window");
  clickItem(template, "Copy Address");
  clickItem(template, "Open in Desktop Mode");
  clickItem(template.find((item) => item.label === "Startup Mode").submenu, "Always Run for External AI");
  clickItem(template, "Stop and Quit");
  assert.deepEqual(calls, [
    "show-connection",
    "copy",
    "open-desktop",
    "startup:external-ai",
    "stop-and-quit",
  ]);
});

test("tray menu offers the address and desktop mode only while the service runs", () => {
  for (const status of ["starting", "stopping", "stopped", "crashed", "failed", "unresponsive"]) {
    const { template } = makeTray({ status, address: "http://127.0.0.1:51234" });
    assert.equal(template[0].label.includes("127.0.0.1"), false, status);
    assert.equal(template.find((item) => item.label === "Copy Address").enabled, false, status);
    assert.equal(template.find((item) => item.label === "Open in Desktop Mode").enabled, false, status);
  }
  const { template } = makeTray({ status: "crashed" });
  assert.equal(template[0].label, "Service: Stopped unexpectedly");
  // Stop and Quit is always available.
  assert.notEqual(template.find((item) => item.label === "Stop and Quit").enabled, false);
});
