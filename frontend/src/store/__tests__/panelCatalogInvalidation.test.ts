// #2113 — the panel catalogue is a cache of runtime truth, so it must be
// dropped whenever the registries it describes are rebuilt. Mirrors
// `typeCatalogInvalidation.test.ts` (ADR-053 FR-062) one tier over: every
// emitter of `blocks.reloaded` reaches `refresh_all_registries()`, which has
// rebuilt the panel registry alongside types and blocks since #2021, so
// the Panels tab's listing and choices get the same invalidation.

import { beforeEach, describe, expect, it, vi } from "vitest";

import type * as DataApi from "../../lib/api/data";
import { dispatchWorkflowEvent } from "../../hooks/useWebSocket.parts/dispatchEvent";
import { resetAppStore } from "../../testUtils";
import type { WorkflowEventMessage } from "../../types/api";
import { useAppStore } from "../index";
import {
  choosePanel,
  clearPanelChoiceAt,
  loadPanelCatalog,
  rescanPanels,
  resetPanelCatalogLoader,
} from "../usePanelCatalog";

const listPanels = vi.fn();
const listPanelChoices = vi.fn();
const reloadPanels = vi.fn();
const setPanelChoice = vi.fn();
const clearPanelChoice = vi.fn();
vi.mock("../../lib/api/data", async (importOriginal) => {
  const actual = await importOriginal<typeof DataApi>();
  return {
    ...actual,
    dataApi: {
      ...actual.dataApi,
      listPanels: () => listPanels(),
      listPanelChoices: () => listPanelChoices(),
      reloadPanels: () => reloadPanels(),
      setPanelChoice: (...args: unknown[]) => setPanelChoice(...args),
      clearPanelChoice: (...args: unknown[]) => clearPanelChoice(...args),
    },
  };
});

const DEPS = {
  appendLog: vi.fn(),
  setInteractivePrompt: vi.fn(),
  setWorkflow: vi.fn(),
};

function event(type: string): WorkflowEventMessage {
  return { type, data: {}, timestamp: "2026-08-08T00:00:00Z" };
}

beforeEach(() => {
  resetAppStore();
  resetPanelCatalogLoader();
  listPanels.mockReset();
  listPanels.mockResolvedValue({ panels: [], diagnostics: [] });
  listPanelChoices.mockReset();
  listPanelChoices.mockResolvedValue({ choices: [] });
  reloadPanels.mockReset();
  reloadPanels.mockResolvedValue({ reloaded: 0, added: [], removed: [], diagnostics: [] });
  setPanelChoice.mockReset();
  clearPanelChoice.mockReset();
});

describe("the panel catalogue is invalidated, not cached forever", () => {
  it("does not re-fetch while nothing has invalidated it", async () => {
    await loadPanelCatalog();
    await loadPanelCatalog();
    expect(listPanels).toHaveBeenCalledTimes(1);
    expect(listPanelChoices).toHaveBeenCalledTimes(1);
  });

  it("re-fetches on the blocks.reloaded registry event", async () => {
    await loadPanelCatalog();
    expect(useAppStore.getState().panelsLoaded).toBe(true);

    dispatchWorkflowEvent(event("blocks.reloaded"), DEPS);
    await vi.waitFor(() => expect(listPanels).toHaveBeenCalledTimes(2));
    await vi.waitFor(() => expect(listPanelChoices).toHaveBeenCalledTimes(2));
  });

  it("re-routes previews that are already open when the registries change", async () => {
    // A panel registered while a preview is on screen has to reach that
    // preview. `PreviewHost` re-creates its session on target or routing-epoch
    // change and on nothing else, so without the bump the panel kept rendering
    // through the old routing — a project's own Image stayed in the core Array
    // number table until the person clicked to empty canvas and back.
    await loadPanelCatalog();
    const before = useAppStore.getState().panelChoiceVersion;

    dispatchWorkflowEvent(event("blocks.reloaded"), DEPS);

    await vi.waitFor(() => expect(useAppStore.getState().panelChoiceVersion).toBe(before + 1));
  });

  it("leaves unrelated websocket events alone", async () => {
    await loadPanelCatalog();
    dispatchWorkflowEvent(event("git.head_changed"), DEPS);
    dispatchWorkflowEvent(event("block_pty_closed"), DEPS);
    await Promise.resolve();
    expect(listPanels).toHaveBeenCalledTimes(1);
  });
});

describe("rescanPanels — the Reload button", () => {
  it("re-scans the drop-in directories before re-reading the listing", async () => {
    // The order is the whole point: the listing answers from the in-memory
    // registry, so re-fetching without the scan re-reads the stale answer.
    const calls: string[] = [];
    reloadPanels.mockImplementation(() => {
      calls.push("scan");
      return Promise.resolve({ reloaded: 0, added: [], removed: [], diagnostics: [] });
    });
    listPanels.mockImplementation(() => {
      calls.push("list");
      return Promise.resolve({ panels: [], diagnostics: [] });
    });

    await rescanPanels();

    expect(calls).toEqual(["scan", "list"]);
  });

  it("still re-reads the listing when the re-scan fails", async () => {
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});
    reloadPanels.mockRejectedValue(new Error("offline"));

    await expect(rescanPanels()).resolves.toBeUndefined();

    expect(listPanels).toHaveBeenCalled();
    expect(consoleError).toHaveBeenCalled();
    consoleError.mockRestore();
  });
});

describe("choice mutations re-route open previews (#2049 / #2113)", () => {
  it("a forced fetch in flight does not overwrite a concurrent choice write (#2153 review)", async () => {
    // The auto-rescan on a tab revisit forces a catalogue fetch whose choices
    // GET can still be on the wire when the write route answers with the new
    // choice. The stale GET must not land over the write's newer answer.
    let resolveChoices: (value: { choices: unknown[] }) => void = () => {};
    listPanelChoices.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveChoices = resolve;
        }),
    );
    const written = {
      target_type: "Spectrum",
      previewer_id: "user.spectrum.view",
      scope: "user",
      available: true,
    };
    setPanelChoice.mockResolvedValue({ choices: [written] });

    const fetch = loadPanelCatalog({ force: true });
    await vi.waitFor(() => expect(listPanelChoices).toHaveBeenCalledTimes(1));
    await choosePanel("Spectrum", "user.spectrum.view", "user");
    expect(useAppStore.getState().panelChoices).toEqual([written]);

    // The pre-write listing lands late; the epoch guard drops it.
    resolveChoices({ choices: [] });
    await fetch;
    expect(useAppStore.getState().panelChoices).toEqual([written]);
  });

  it("a written choice applies the returned choices and bumps the routing epoch", async () => {
    const choice = {
      target_type: "Spectrum",
      previewer_id: "user.spectrum.view",
      scope: "user",
      available: true,
    };
    setPanelChoice.mockResolvedValue({ choices: [choice] });
    const versionBefore = useAppStore.getState().panelChoiceVersion;

    await choosePanel("Spectrum", "user.spectrum.view", "user");

    expect(setPanelChoice).toHaveBeenCalledWith("Spectrum", "user.spectrum.view", "user");
    expect(useAppStore.getState().panelChoices).toEqual([choice]);
    expect(useAppStore.getState().panelChoiceVersion).toBe(versionBefore + 1);
  });

  it("a cleared choice also bumps the routing epoch", async () => {
    clearPanelChoice.mockResolvedValue({ choices: [] });
    const versionBefore = useAppStore.getState().panelChoiceVersion;

    await clearPanelChoiceAt("Spectrum", "project");

    expect(clearPanelChoice).toHaveBeenCalledWith("Spectrum", "project");
    expect(useAppStore.getState().panelChoiceVersion).toBe(versionBefore + 1);
  });
});
