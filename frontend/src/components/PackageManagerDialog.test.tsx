import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type * as ApiModule from "../lib/api";
import type { InstalledPackage, PackageUpdateStatus } from "../types/api";

const listInstalledPackages = vi.fn();
const checkPackageUpdates = vi.fn();
const updatePackage = vi.fn();
const rollbackPackage = vi.fn();
const deletePackage = vi.fn();
const installLocalPackage = vi.fn();
const listBlocks = vi.fn();
const getBlockSchema = vi.fn();
const openNativeDialog = vi.fn();

vi.mock("../lib/api", async (importOriginal) => {
  // The app store imports non-api helpers (e.g. setWorkflowWriteStartedListener)
  // from this module, so keep the original module and override only `api`.
  const actual = await importOriginal<typeof ApiModule>();
  return {
    ...actual,
    api: {
      ...actual.api,
      listInstalledPackages: (...a: unknown[]) => listInstalledPackages(...a),
      checkPackageUpdates: (...a: unknown[]) => checkPackageUpdates(...a),
      updatePackage: (...a: unknown[]) => updatePackage(...a),
      rollbackPackage: (...a: unknown[]) => rollbackPackage(...a),
      deletePackage: (...a: unknown[]) => deletePackage(...a),
      installLocalPackage: (...a: unknown[]) => installLocalPackage(...a),
      listBlocks: (...a: unknown[]) => listBlocks(...a),
      getBlockSchema: (...a: unknown[]) => getBlockSchema(...a),
      openNativeDialog: (...a: unknown[]) => openNativeDialog(...a),
    },
  };
});

import { PackageManagerDialog } from "./PackageManagerDialog";

function installedPackage(overrides: Partial<InstalledPackage> = {}): InstalledPackage {
  return {
    package_name: "scistudio-blocks-demo",
    version: "1.0.0",
    install_path: "/p/scistudio-blocks-demo-1.0.0",
    modules: ["scistudio_blocks_demo"],
    has_backup: false,
    backup_version: "",
    bundled: false,
    ...overrides,
  };
}

function updateStatus(overrides: Partial<PackageUpdateStatus> = {}): PackageUpdateStatus {
  return {
    package_name: "scistudio-blocks-demo",
    current_version: "1.0.0",
    channel: "alpha",
    manifest_url: "https://example.com/m.json",
    status: "update",
    available_version: "1.2.0",
    min_core_base: "0.2.1",
    notes: "fix",
    reason: "",
    update_available: true,
    ...overrides,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  listBlocks.mockResolvedValue({ blocks: [] });
});

afterEach(() => cleanup());

describe("PackageManagerDialog (#1784)", () => {
  it("renders nothing when closed", () => {
    const { container } = render(<PackageManagerDialog open={false} onClose={() => {}} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("lists installed packages with an available update and applies it", async () => {
    listInstalledPackages.mockResolvedValue({ packages: [installedPackage()] });
    checkPackageUpdates.mockResolvedValue({ core_base: "0.2.1", statuses: [updateStatus()] });
    updatePackage.mockResolvedValue({
      package_name: "scistudio-blocks-demo",
      version: "1.2.0",
      action: "update",
      previous_version: "1.0.0",
      needs_relaunch: true,
    });
    const relaunch = vi.fn().mockResolvedValue(undefined);
    (window as unknown as { scistudioDesktop: unknown }).scistudioDesktop = { relaunch };

    render(<PackageManagerDialog open onClose={() => {}} />);

    expect(await screen.findByText("scistudio-blocks-demo")).toBeTruthy();
    expect(screen.getByText("→ v1.2.0")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: /^update$/i }));
    await waitFor(() => expect(updatePackage).toHaveBeenCalledWith("scistudio-blocks-demo"));

    const restart = await screen.findByRole("button", { name: /restart now/i });
    fireEvent.click(restart);
    expect(relaunch).toHaveBeenCalledTimes(1);
  });

  it("degrades gracefully when the desktop bridge has no relaunch method (#1792)", async () => {
    listInstalledPackages.mockResolvedValue({ packages: [installedPackage()] });
    checkPackageUpdates.mockResolvedValue({ core_base: "0.2.1", statuses: [updateStatus()] });
    updatePackage.mockResolvedValue({
      package_name: "scistudio-blocks-demo",
      version: "1.2.0",
      action: "update",
      previous_version: "1.0.0",
      needs_relaunch: true,
    });
    // OTA-newer frontend on an older shell: the bridge exists but predates the
    // `relaunch` method. Must not throw "relaunch is not a function".
    (window as unknown as { scistudioDesktop: unknown }).scistudioDesktop = {};

    render(<PackageManagerDialog open onClose={() => {}} />);
    await screen.findByText("scistudio-blocks-demo");

    fireEvent.click(screen.getByRole("button", { name: /^update$/i }));
    const restart = await screen.findByRole("button", { name: /restart now/i });
    expect(() => fireEvent.click(restart)).not.toThrow();
    expect(await screen.findByText(/quit and reopen SciStudio/i)).toBeTruthy();
  });

  it("offers rollback when a backup exists and deletes on request", async () => {
    listInstalledPackages.mockResolvedValue({
      packages: [installedPackage({ has_backup: true, backup_version: "0.9.0" })],
    });
    checkPackageUpdates.mockResolvedValue({ core_base: "0.2.1", statuses: [] });
    deletePackage.mockResolvedValue({
      package_name: "scistudio-blocks-demo",
      version: "1.0.0",
      action: "delete",
      previous_version: "",
      needs_relaunch: true,
    });

    render(<PackageManagerDialog open onClose={() => {}} />);
    await screen.findByText("scistudio-blocks-demo");
    expect(screen.getByRole("button", { name: /rollback/i })).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: /delete/i }));
    await waitFor(() => expect(deletePackage).toHaveBeenCalledWith("scistudio-blocks-demo"));
  });

  it("lists a bundled package as updatable but not deletable", async () => {
    listInstalledPackages.mockResolvedValue({
      packages: [installedPackage({ bundled: true, install_path: "" })],
    });
    checkPackageUpdates.mockResolvedValue({ core_base: "0.2.1", statuses: [updateStatus()] });

    render(<PackageManagerDialog open onClose={() => {}} />);
    await screen.findByText("scistudio-blocks-demo");
    expect(screen.getByText("bundled")).toBeTruthy();
    expect(screen.getByRole("button", { name: /^update$/i })).toBeTruthy();
    expect(screen.queryByRole("button", { name: /delete/i })).toBeNull();
  });

  it("shows an empty state when no packages are installed", async () => {
    listInstalledPackages.mockResolvedValue({ packages: [] });
    checkPackageUpdates.mockResolvedValue({ core_base: "0.2.1", statuses: [] });
    render(<PackageManagerDialog open onClose={() => {}} />);
    expect(await screen.findByText(/no packages installed yet/i)).toBeTruthy();
  });
});
