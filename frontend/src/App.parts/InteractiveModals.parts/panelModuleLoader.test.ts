import { describe, expect, it, vi } from "vitest";

import type { PanelManifestDescriptor } from "../../store/types";
import {
  PANEL_HOST_API_VERSION,
  type PanelHostApi,
  type PanelInstance,
  isPanelModule,
  mountDynamicPanel,
} from "./panelModuleLoader";

const GOOD_URL = "/api/interactive/panels/pkg.panel/index.js";

function makeHost(overrides: Partial<PanelHostApi> = {}): PanelHostApi {
  return {
    apiVersion: PANEL_HOST_API_VERSION,
    blockId: "block-1",
    panelPayload: { question: "left or right?" },
    confirm: vi.fn(),
    cancel: vi.fn(),
    ...overrides,
  };
}

function manifest(partial: Partial<PanelManifestDescriptor> = {}): PanelManifestDescriptor {
  return {
    panel_id: "pkg.panel",
    module_url: GOOD_URL,
    export_name: "default",
    api_version: "1",
    ...partial,
  };
}

describe("mountDynamicPanel", () => {
  it("mounts a valid PanelModule and lets it drive host.confirm(decision)", async () => {
    const confirm = vi.fn();
    const host = makeHost({ confirm });
    const decision = { choice: "left", note: "looks good" };

    // The package panel calls host.confirm with its JSON-safe decision on submit.
    const mount = vi.fn((container: HTMLElement, h: PanelHostApi): PanelInstance => {
      container.textContent = "MOUNTED PACKAGE PANEL";
      h.confirm(decision);
      return { unmount: vi.fn() };
    });
    const importer = vi.fn(async () => ({ default: { apiVersion: "1", mount } }));
    const container = document.createElement("div");

    const result = await mountDynamicPanel(manifest(), container, host, importer);

    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(typeof result.instance.unmount).toBe("function");
    }
    expect(importer).toHaveBeenCalledWith(GOOD_URL);
    expect(mount).toHaveBeenCalledWith(container, host);
    expect(confirm).toHaveBeenCalledWith(decision);
    expect(container.textContent).toBe("MOUNTED PACKAGE PANEL");
  });

  it("reads a non-default named export", async () => {
    const mount = vi.fn((): PanelInstance => ({ unmount: vi.fn() }));
    const importer = vi.fn(async () => ({ PkgPanel: { apiVersion: "1", mount } }));

    const result = await mountDynamicPanel(
      manifest({ export_name: "PkgPanel" }),
      document.createElement("div"),
      makeHost(),
      importer,
    );

    expect(result.ok).toBe(true);
    expect(mount).toHaveBeenCalledTimes(1);
  });

  it("rejects a remote module_url with a typed failure and never imports", async () => {
    const importer = vi.fn(async () => ({}));

    const result = await mountDynamicPanel(
      manifest({ module_url: "https://evil.cdn.example/mod.js" }),
      document.createElement("div"),
      makeHost(),
      importer,
    );

    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.reason).toBe("remote_url_rejected");
    expect(importer).not.toHaveBeenCalled();
  });

  it("rejects a protocol-relative module_url", async () => {
    const importer = vi.fn(async () => ({}));

    const result = await mountDynamicPanel(
      manifest({ module_url: "//evil.cdn.example/mod.js" }),
      document.createElement("div"),
      makeHost(),
      importer,
    );

    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.reason).toBe("remote_url_rejected");
    expect(importer).not.toHaveBeenCalled();
  });

  it("returns invalid_module_url when the manifest has no module_url", async () => {
    const importer = vi.fn(async () => ({}));

    const result = await mountDynamicPanel(
      manifest({ module_url: "" }),
      document.createElement("div"),
      makeHost(),
      importer,
    );

    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.reason).toBe("invalid_module_url");
    expect(importer).not.toHaveBeenCalled();
  });

  it("refuses an incompatible manifest api_version before importing", async () => {
    const importer = vi.fn(async () => ({}));

    const result = await mountDynamicPanel(
      manifest({ api_version: "2" }),
      document.createElement("div"),
      makeHost(),
      importer,
    );

    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.reason).toBe("api_version_mismatch");
    expect(importer).not.toHaveBeenCalled();
  });

  it("refuses a module whose apiVersion is incompatible", async () => {
    const mount = vi.fn((): PanelInstance => ({ unmount: vi.fn() }));
    const importer = vi.fn(async () => ({ default: { apiVersion: "2", mount } }));

    const result = await mountDynamicPanel(
      manifest(),
      document.createElement("div"),
      makeHost(),
      importer,
    );

    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.reason).toBe("api_version_mismatch");
    expect(mount).not.toHaveBeenCalled();
  });

  it("returns export_missing when the named export is absent", async () => {
    const importer = vi.fn(async () => ({ somethingElse: {} }));

    const result = await mountDynamicPanel(
      manifest(),
      document.createElement("div"),
      makeHost(),
      importer,
    );

    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.reason).toBe("export_missing");
  });

  it("returns not_a_panel_module when the export is not a PanelModule", async () => {
    const importer = vi.fn(async () => ({ default: { apiVersion: "1" /* no mount */ } }));

    const result = await mountDynamicPanel(
      manifest(),
      document.createElement("div"),
      makeHost(),
      importer,
    );

    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.reason).toBe("not_a_panel_module");
  });

  it("returns import_failed (no throw) when the importer rejects", async () => {
    const importer = vi.fn(async () => {
      throw new Error("network down");
    });

    const result = await mountDynamicPanel(
      manifest(),
      document.createElement("div"),
      makeHost(),
      importer,
    );

    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.reason).toBe("import_failed");
      expect(result.message).toContain("network down");
    }
  });

  it("returns mount_failed (no throw) when mount() throws", async () => {
    const mount = vi.fn(() => {
      throw new Error("boom");
    });
    const importer = vi.fn(async () => ({ default: { apiVersion: "1", mount } }));

    const result = await mountDynamicPanel(
      manifest(),
      document.createElement("div"),
      makeHost(),
      importer,
    );

    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.reason).toBe("mount_failed");
  });

  it("returns mount_failed when mount() returns an invalid instance", async () => {
    const mount = vi.fn(() => ({}) as unknown as PanelInstance);
    const importer = vi.fn(async () => ({ default: { apiVersion: "1", mount } }));

    const result = await mountDynamicPanel(
      manifest(),
      document.createElement("div"),
      makeHost(),
      importer,
    );

    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.reason).toBe("mount_failed");
  });
});

describe("isPanelModule", () => {
  it("accepts an object with mount + apiVersion", () => {
    expect(isPanelModule({ apiVersion: "1", mount: () => ({ unmount() {} }) })).toBe(true);
  });

  it("rejects non-modules", () => {
    expect(isPanelModule(null)).toBe(false);
    expect(isPanelModule({})).toBe(false);
    expect(isPanelModule({ apiVersion: "1" })).toBe(false);
    expect(isPanelModule({ mount: () => undefined })).toBe(false);
  });
});
