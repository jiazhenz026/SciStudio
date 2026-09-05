// ADR-054 T-010's host half — reading a panel, saving it, and reverting.
//
// The audit found the three editing endpoints shipped with no consumer: FR-024
// (read), FR-025 to FR-027 (save, with the copy-into-project a save on a
// read-only panel performs) and FR-029 (revert) were reachable only from
// `curl`, which is what made SC-004 impossible to verify against the product.
// These tests drive the host side of all three.

import { beforeEach, describe, expect, it, vi } from "vitest";

import type * as LibApi from "../../lib/api";
import { resetAppStore } from "../../testUtils";
import { useAppStore } from "../index";
import { revertPanelOverride } from "../usePanelRevert";

const readPanelSource = vi.fn();
const savePanelSource = vi.fn();
const revertPanelOverrideApi = vi.fn();
const listPanels = vi.fn();
const listPanelChoices = vi.fn();

vi.mock("../../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof LibApi>();
  return {
    ...actual,
    api: {
      ...actual.api,
      readPanelSource: (...args: unknown[]) => readPanelSource(...args),
      savePanelSource: (...args: unknown[]) => savePanelSource(...args),
      revertPanelOverride: (...args: unknown[]) => revertPanelOverrideApi(...args),
      listPanels: (...args: unknown[]) => listPanels(...args),
      listPanelChoices: (...args: unknown[]) => listPanelChoices(...args),
    },
  };
});

beforeEach(() => {
  resetAppStore();
  useAppStore.setState({ tabs: [], activeTabId: null });
  vi.clearAllMocks();
  readPanelSource.mockImplementation(async (panelId: string) => ({
    panel_id: panelId,
    tier: "core",
    entry: "index.html",
    source: "<!doctype html><title>core</title>\n",
    declaration: "{}\n",
    editable: false,
    shadows: null,
    descriptor: null,
  }));
  savePanelSource.mockImplementation(async (panelId: string) => ({
    panel_id: panelId,
    tier: "project",
    copied: true,
    descriptor: null,
  }));
  revertPanelOverrideApi.mockImplementation(async (panelId: string) => ({
    panel_id: panelId,
    removed_tier: "project",
    restored_tier: "core",
    descriptor: null,
  }));
  listPanels.mockResolvedValue({ panels: [], diagnostics: [] });
  listPanelChoices.mockResolvedValue({ choices: [] });
});

async function openedPanelTab(panelId: string) {
  useAppStore.getState().openPanelSourceTab(panelId);
  await vi.waitFor(() => {
    const tab = useAppStore.getState().tabs[0];
    expect(tab.kind === "file" && tab.loading).toBe(false);
  });
  const tab = useAppStore.getState().tabs[0];
  if (tab.kind !== "file") throw new Error("expected a file tab");
  return tab;
}

describe("openPanelSourceTab (FR-024)", () => {
  it("reads any resolved panel's document, whichever tier it came from", async () => {
    const tab = await openedPanelTab("core.plot.basic");

    expect(readPanelSource).toHaveBeenCalledWith("core.plot.basic");
    expect(tab.content).toBe("<!doctype html><title>core</title>\n");
    expect(tab.panelSourceId).toBe("core.plot.basic");
    expect(tab.language).toBe("html");
  });

  it("opens a core panel EDITABLE, because saving it is what performs the copy", async () => {
    // FR-025 forbids asking where a save goes and FR-026 answers for the
    // read-only tiers. A read-only tab here would leave SC-004's "copy a
    // built-in panel into a project" with no affordance at all.
    const tab = await openedPanelTab("core.plot.basic");
    expect(tab.readOnly).toBe(false);
  });

  it("says which tier a save will land in, before the save", async () => {
    const tab = await openedPanelTab("core.plot.basic");
    expect(tab.displayName).toBe("core.plot.basic (core)");
  });

  it("focuses the tab it already opened rather than stacking duplicates", async () => {
    await openedPanelTab("core.plot.basic");
    useAppStore.getState().openPanelSourceTab("core.plot.basic");
    expect(useAppStore.getState().tabs).toHaveLength(1);
    expect(readPanelSource).toHaveBeenCalledTimes(1);
  });
});

describe("saving a panel tab (FR-025 to FR-027, FR-030)", () => {
  it("saves through the panel route, not the project-file one", async () => {
    const tab = await openedPanelTab("core.plot.basic");
    useAppStore.getState().updateFileTabContent(tab.id, "<!doctype html><title>mine</title>\n");

    await useAppStore.getState().saveFileTab(tab.id);

    expect(savePanelSource).toHaveBeenCalledWith(
      "core.plot.basic",
      "<!doctype html><title>mine</title>\n",
    );
  });

  it("follows the panel into the project when the save copied it (FR-026)", async () => {
    const tab = await openedPanelTab("core.plot.basic");
    useAppStore.getState().updateFileTabContent(tab.id, "edited");

    await useAppStore.getState().saveFileTab(tab.id);

    const saved = useAppStore.getState().tabs[0];
    expect(saved.kind === "file" && saved.displayName).toBe("core.plot.basic (project)");
    expect(saved.kind === "file" && saved.dirty).toBe(false);
  });

  it("reloads every mounted instance of the panel it just wrote (FR-030)", async () => {
    // The counter `usePanelReloadToken` reads. Without this bump SC-004's
    // "see the mounted panel redraw without reopening the view" rests entirely
    // on a file watcher that cannot have been watching a directory the save
    // itself created.
    const tab = await openedPanelTab("core.plot.basic");
    expect(useAppStore.getState().panelDocumentVersions["core.plot.basic"]).toBeUndefined();

    await useAppStore.getState().saveFileTab(tab.id);

    expect(useAppStore.getState().panelDocumentVersions["core.plot.basic"]).toBe(1);
  });

  it("surfaces a refusal instead of leaving a tab that looks saved", async () => {
    const alert = vi.spyOn(window, "alert").mockImplementation(() => {});
    savePanelSource.mockRejectedValueOnce(new Error("no project is open"));
    const tab = await openedPanelTab("core.plot.basic");
    useAppStore.getState().updateFileTabContent(tab.id, "edited");

    await useAppStore.getState().saveFileTab(tab.id);

    expect(alert).toHaveBeenCalledWith(expect.stringContaining("no project is open"));
    const after = useAppStore.getState().tabs[0];
    expect(after.kind === "file" && after.dirty).toBe(true);
    alert.mockRestore();
  });
});

describe("revertPanelOverride (FR-029, FR-030)", () => {
  it("deletes the shadowing copy and reloads the panel that comes back", async () => {
    const result = await revertPanelOverride("core.plot.basic");

    expect(revertPanelOverrideApi).toHaveBeenCalledWith("core.plot.basic");
    expect(result.restored_tier).toBe("core");
    expect(useAppStore.getState().panelDocumentVersions["core.plot.basic"]).toBe(1);
  });
});
