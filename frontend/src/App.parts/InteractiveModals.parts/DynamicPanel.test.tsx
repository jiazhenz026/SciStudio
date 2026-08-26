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

  it("unmounts a panel that finished loading after the effect was torn down", async () => {
    // StrictMode mounts, unmounts, and mounts again. `mountDynamicPanel` is
    // async, so the teardown lands while the module is still loading: the
    // cleanup finds no instance to unmount, and `mount()` then puts the panel's
    // DOM in the container anyway. Left there, the second pass mounts a second
    // copy on top and the reader sees the panel twice.
    let release: (() => void) | undefined;
    const held = new Promise<void>((resolve) => {
      release = resolve;
    });
    const unmount = vi.fn();
    const mount = vi.fn((container: HTMLElement) => {
      container.appendChild(document.createTextNode("PANEL UI"));
      return { unmount };
    });
    const importer = vi.fn(async () => {
      await held;
      return { default: { apiVersion: "1", mount } };
    });

    const { unmount: unmountTree } = render(
      <DynamicPanel
        manifest={MANIFEST}
        blockId="block-1"
        panelPayload={{}}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
        importer={importer}
      />,
    );

    // Tear down first, then let the import resolve — the ordering the race has.
    unmountTree();
    release?.();

    await waitFor(() => expect(mount).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(unmount).toHaveBeenCalledTimes(1));
  });

  // #2195 — the panel that locks the user out: it mounts fine, so there is no
  // error surface, and it wires neither Continue nor Cancel. The overlay covers
  // the Toolbar's Stop button, so without host-owned chrome the app is gone.
  describe("host-owned escape hatch (#2195)", () => {
    /** A module that mounts successfully and offers the user no way out. */
    function exitlessImporter() {
      const mount = vi.fn((container: HTMLElement) => {
        container.textContent = "NO WAY OUT";
        return { unmount: vi.fn() };
      });
      return { mount, importer: vi.fn(async () => ({ default: { apiVersion: "1", mount } })) };
    }

    it("cancels an exit-less mounted panel on ESC", async () => {
      const onConfirm = vi.fn();
      const onCancel = vi.fn();
      const { mount, importer } = exitlessImporter();

      render(
        <DynamicPanel
          manifest={MANIFEST}
          blockId="block-1"
          panelPayload={{}}
          onConfirm={onConfirm}
          onCancel={onCancel}
          importer={importer}
        />,
      );

      await waitFor(() => expect(mount).toHaveBeenCalled());
      expect(screen.queryByTestId("dynamic-panel-error")).not.toBeInTheDocument();

      fireEvent.keyDown(document, { key: "Escape" });
      expect(onCancel).toHaveBeenCalledTimes(1);
      expect(onConfirm).not.toHaveBeenCalled();
    });

    it("cancels an exit-less mounted panel from the title-bar close control", async () => {
      const onConfirm = vi.fn();
      const onCancel = vi.fn();
      const { mount, importer } = exitlessImporter();

      render(
        <DynamicPanel
          manifest={MANIFEST}
          blockId="block-1"
          panelPayload={{}}
          onConfirm={onConfirm}
          onCancel={onCancel}
          importer={importer}
        />,
      );

      await waitFor(() => expect(mount).toHaveBeenCalled());
      fireEvent.click(screen.getByTestId("dynamic-panel-close"));
      expect(onCancel).toHaveBeenCalledTimes(1);
      expect(onConfirm).not.toHaveBeenCalled();
    });

    it("leaves the panel's own content area alone, so a panel with its own Cancel keeps it", async () => {
      const onCancel = vi.fn();
      // The tutorial panel's shape: it draws its own Cancel in the content area.
      const mount = vi.fn((container: HTMLElement, host: PanelHostApi) => {
        const own = document.createElement("button");
        own.textContent = "Cancel";
        own.dataset.testid = "panel-own-cancel";
        own.addEventListener("click", () => host.cancel());
        container.appendChild(own);
        return { unmount: vi.fn() };
      });
      const importer = vi.fn(async () => ({ default: { apiVersion: "1", mount } }));

      render(
        <DynamicPanel
          manifest={MANIFEST}
          blockId="block-1"
          panelPayload={{}}
          onConfirm={vi.fn()}
          onCancel={onCancel}
          importer={importer}
        />,
      );

      await waitFor(() => expect(mount).toHaveBeenCalled());
      // Two distinct controls: one host-drawn in the title bar, one the panel's
      // own inside the mount container. Neither is inside the other.
      const mountPoint = screen.getByTestId("dynamic-panel-mount");
      const own = screen.getByTestId("panel-own-cancel");
      const hostClose = screen.getByTestId("dynamic-panel-close");
      expect(mountPoint).toContainElement(own);
      expect(mountPoint).not.toContainElement(hostClose);

      fireEvent.click(own);
      expect(onCancel).toHaveBeenCalledTimes(1);
    });

    it("names the block in the title bar, falling back to the block id", async () => {
      const { importer } = exitlessImporter();
      const { rerender } = render(
        <DynamicPanel
          manifest={MANIFEST}
          blockId="block-1"
          blockName="review_labels"
          panelPayload={{}}
          onConfirm={vi.fn()}
          onCancel={vi.fn()}
          importer={importer}
        />,
      );
      expect(screen.getByTestId("dynamic-panel-titlebar")).toHaveTextContent("review_labels");

      rerender(
        <DynamicPanel
          manifest={MANIFEST}
          blockId="block-1"
          blockName="   "
          panelPayload={{}}
          onConfirm={vi.fn()}
          onCancel={vi.fn()}
          importer={importer}
        />,
      );
      expect(screen.getByTestId("dynamic-panel-titlebar")).toHaveTextContent("block-1");
    });

    it("still exits on ESC when the module never loaded at all", async () => {
      const onCancel = vi.fn();
      render(
        <DynamicPanel
          manifest={{ ...MANIFEST, module_url: "" }}
          blockId="block-1"
          panelPayload={{}}
          onConfirm={vi.fn()}
          onCancel={onCancel}
          importer={vi.fn(async () => ({}))}
        />,
      );

      await screen.findByTestId("dynamic-panel-error");
      fireEvent.keyDown(document, { key: "Escape" });
      expect(onCancel).toHaveBeenCalledTimes(1);
    });

    it("ignores keys that are not ESC", async () => {
      const onCancel = vi.fn();
      const { mount, importer } = exitlessImporter();
      render(
        <DynamicPanel
          manifest={MANIFEST}
          blockId="block-1"
          panelPayload={{}}
          onConfirm={vi.fn()}
          onCancel={onCancel}
          importer={importer}
        />,
      );
      await waitFor(() => expect(mount).toHaveBeenCalled());

      fireEvent.keyDown(document, { key: "Enter" });
      fireEvent.keyDown(document, { key: "a" });
      expect(onCancel).not.toHaveBeenCalled();
    });

    it("unbinds ESC once the panel is gone", async () => {
      const onCancel = vi.fn();
      const { mount, importer } = exitlessImporter();
      const { unmount } = render(
        <DynamicPanel
          manifest={MANIFEST}
          blockId="block-1"
          panelPayload={{}}
          onConfirm={vi.fn()}
          onCancel={onCancel}
          importer={importer}
        />,
      );
      await waitFor(() => expect(mount).toHaveBeenCalled());

      unmount();
      fireEvent.keyDown(document, { key: "Escape" });
      expect(onCancel).not.toHaveBeenCalled();
    });
  });
});
