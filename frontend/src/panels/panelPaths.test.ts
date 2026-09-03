/**
 * ADR-054 spec 1, T-011 — the reload trigger's address (FR-030, FR-032).
 *
 * FR-032 is the requirement with the trap in it: the reload must fire for panel
 * files the *agent* wrote on the person's behalf, not only for files the person
 * wrote. An agent writes a file with its own editing tools, so there is no
 * request the product could attach an identity to — which is exactly why this
 * reads the panel id out of the path. A path is the one thing both writers
 * leave behind.
 */

import { describe, expect, it } from "vitest";

import { isPanelProjectPath, panelIdForProjectPath } from "./panelPaths";

describe("panelIdForProjectPath", () => {
  it("names the panel a file inside its directory belongs to", () => {
    expect(panelIdForProjectPath("panels/core.table/index.html")).toBe("core.table");
    expect(panelIdForProjectPath("panels/core.table/panel.json")).toBe("core.table");
    // Anything inside the directory is part of the panel, however deep.
    expect(panelIdForProjectPath("panels/core.table/assets/style.css")).toBe("core.table");
  });

  it("recognises the legacy drop-in directory on the same terms (FR-020)", () => {
    expect(panelIdForProjectPath("previewers/myproj.image/index.html")).toBe("myproj.image");
  });

  it("accepts backslashes, because a watcher on Windows may produce them", () => {
    // A reload that silently stopped working on one platform is precisely the
    // half-working trigger FR-032 exists to rule out.
    expect(panelIdForProjectPath("panels\\core.table\\index.html")).toBe("core.table");
  });

  it("names no panel for a flat module-form drop-in", () => {
    // `previewers/thing.py` is the ADR-048 module form: it belongs to no panel
    // *directory* and is reloaded by rebuilding the registry, not by remounting
    // one panel.
    expect(panelIdForProjectPath("previewers/thing.py")).toBeNull();
    expect(panelIdForProjectPath("panels/thing.py")).toBeNull();
  });

  it("names no panel for anything outside a panel directory", () => {
    expect(panelIdForProjectPath("blocks/loader.py")).toBeNull();
    expect(panelIdForProjectPath("data/raw/cells.tif")).toBeNull();
    expect(panelIdForProjectPath("workflows/main.yaml")).toBeNull();
  });

  it("never reads a traversal segment as a panel id", () => {
    expect(panelIdForProjectPath("panels/../secrets/index.html")).toBeNull();
  });

  it("answers null for anything that is not a usable path", () => {
    expect(panelIdForProjectPath("")).toBeNull();
    expect(panelIdForProjectPath(null)).toBeNull();
    expect(panelIdForProjectPath(undefined)).toBeNull();
    expect(panelIdForProjectPath(7)).toBeNull();
    expect(panelIdForProjectPath({})).toBeNull();
  });

  it("agrees with its own predicate", () => {
    expect(isPanelProjectPath("panels/core.table/index.html")).toBe(true);
    expect(isPanelProjectPath("blocks/loader.py")).toBe(false);
  });
});
