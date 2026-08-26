"use strict";

// Unit tests for the application-menu template (desktop/menu.js).
// Run with: npm --prefix desktop test   (Node built-in runner).

const test = require("node:test");
const assert = require("node:assert/strict");
const { MENU_ACTIONS, buildMenuTemplate } = require("../menu");

function makeDeps(platform) {
  const sent = [];
  let updateChecks = 0;
  let aboutShown = 0;
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
  });
  return { sent, updateChecks: () => updateChecks, aboutShown: () => aboutShown, template };
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

test("File menu offers projects home, new project, save actions, and bring in my work", () => {
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
  // ever produce ids the frontend knows how to dispatch.
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
