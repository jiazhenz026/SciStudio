import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { PanelManifestDescriptor } from "../../store/types";
import { DynamicPanel } from "./DynamicPanel";
import type { PanelHostApi } from "./panelModuleLoader";

afterEach(cleanup);

const MANIFEST: PanelManifestDescriptor = {
  panel_id: "pkg.panel",
  module_url: "/api/interactive/panels/pkg.panel/index.js",
  export_name: "default",
  api_version: "1",
};

describe("<DynamicPanel>", () => {
  it("mounts a package panel and routes host.confirm to onConfirm", async () => {
    const onConfirm = vi.fn();
    const onCancel = vi.fn();
    const decision = { choice: "right" };
    const mount = vi.fn((container: HTMLElement, host: PanelHostApi) => {
      container.textContent = "PACKAGE PANEL UI";
      // Simulate the package panel's own submit button.
      host.confirm(decision);
      return { unmount: vi.fn() };
    });
    const importer = vi.fn(async () => ({ default: { apiVersion: "1", mount } }));

    render(
      <DynamicPanel
        manifest={MANIFEST}
        blockId="block-1"
        panelPayload={{ q: 1 }}
        onConfirm={onConfirm}
        onCancel={onCancel}
        importer={importer}
      />,
    );

    await waitFor(() => expect(mount).toHaveBeenCalled());
    expect(screen.getByTestId("dynamic-panel-mount")).toHaveTextContent("PACKAGE PANEL UI");
    expect(onConfirm).toHaveBeenCalledWith(decision);
  });

  it("renders a visible error surface with a working Cancel exit on load failure", async () => {
    const onConfirm = vi.fn();
    const onCancel = vi.fn();
    // Remote URL → typed failure → error surface (never a silent null).
    const importer = vi.fn(async () => ({}));

    render(
      <DynamicPanel
        manifest={{ ...MANIFEST, module_url: "https://evil.cdn.example/mod.js" }}
        blockId="block-1"
        panelPayload={{}}
        onConfirm={onConfirm}
        onCancel={onCancel}
        importer={importer}
      />,
    );

    const error = await screen.findByTestId("dynamic-panel-error");
    expect(error).toBeInTheDocument();
    expect(importer).not.toHaveBeenCalled();

    fireEvent.click(screen.getByTestId("dynamic-panel-cancel"));
    expect(onCancel).toHaveBeenCalledTimes(1);
    expect(onConfirm).not.toHaveBeenCalled();
  });
});
