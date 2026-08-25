// #2113 — the previewer catalogue is a cache of runtime truth, so it must be
// dropped whenever the registries it describes are rebuilt. Mirrors
// `typeCatalogInvalidation.test.ts` (ADR-053 FR-062) one tier over: every
// emitter of `blocks.reloaded` reaches `refresh_all_registries()`, which has
// rebuilt the previewer registry alongside types and blocks since #2021, so
// the Previewers tab's listing and choices get the same invalidation.

import { beforeEach, describe, expect, it, vi } from "vitest";

import type * as DataApi from "../../lib/api/data";
import { dispatchWorkflowEvent } from "../../hooks/useWebSocket.parts/dispatchEvent";
import { resetAppStore } from "../../testUtils";
import type { WorkflowEventMessage } from "../../types/api";
import { useAppStore } from "../index";
import {
  choosePreviewer,
  clearPreviewerChoiceAt,
  loadPreviewerCatalog,
  rescanPreviewers,
  resetPreviewerCatalogLoader,
} from "../usePreviewerCatalog";

const listPreviewers = vi.fn();
const listPreviewerChoices = vi.fn();
const reloadPreviewers = vi.fn();
const setPreviewerChoice = vi.fn();
const clearPreviewerChoice = vi.fn();
vi.mock("../../lib/api/data", async (importOriginal) => {
  const actual = await importOriginal<typeof DataApi>();
  return {
    ...actual,
    dataApi: {
      ...actual.dataApi,
      listPreviewers: () => listPreviewers(),
      listPreviewerChoices: () => listPreviewerChoices(),
      reloadPreviewers: () => reloadPreviewers(),
      setPreviewerChoice: (...args: unknown[]) => setPreviewerChoice(...args),
      clearPreviewerChoice: (...args: unknown[]) => clearPreviewerChoice(...args),
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
  resetPreviewerCatalogLoader();
  listPreviewers.mockReset();
  listPreviewers.mockResolvedValue({ previewers: [], diagnostics: [] });
  listPreviewerChoices.mockReset();
  listPreviewerChoices.mockResolvedValue({ choices: [] });
  reloadPreviewers.mockReset();
  reloadPreviewers.mockResolvedValue({ reloaded: 0, added: [], removed: [], diagnostics: [] });
  setPreviewerChoice.mockReset();
  clearPreviewerChoice.mockReset();
});

describe("the previewer catalogue is invalidated, not cached forever", () => {
  it("does not re-fetch while nothing has invalidated it", async () => {
    await loadPreviewerCatalog();
    await loadPreviewerCatalog();
    expect(listPreviewers).toHaveBeenCalledTimes(1);
    expect(listPreviewerChoices).toHaveBeenCalledTimes(1);
  });

  it("re-fetches on the blocks.reloaded registry event", async () => {
    await loadPreviewerCatalog();
    expect(useAppStore.getState().previewersLoaded).toBe(true);

    dispatchWorkflowEvent(event("blocks.reloaded"), DEPS);
    await vi.waitFor(() => expect(listPreviewers).toHaveBeenCalledTimes(2));
    await vi.waitFor(() => expect(listPreviewerChoices).toHaveBeenCalledTimes(2));
  });

  it("re-routes previews that are already open when the registries change", async () => {
    // A previewer registered while a preview is on screen has to reach that
    // preview. `PreviewHost` re-creates its session on target or routing-epoch
    // change and on nothing else, so without the bump the panel kept rendering
    // through the old routing — a project's own Image stayed in the core Array
    // number table until the person clicked to empty canvas and back.
    await loadPreviewerCatalog();
    const before = useAppStore.getState().previewerChoiceVersion;

    dispatchWorkflowEvent(event("blocks.reloaded"), DEPS);

    await vi.waitFor(() => expect(useAppStore.getState().previewerChoiceVersion).toBe(before + 1));
  });

  it("leaves unrelated websocket events alone", async () => {
    await loadPreviewerCatalog();
    dispatchWorkflowEvent(event("git.head_changed"), DEPS);
    dispatchWorkflowEvent(event("block_pty_closed"), DEPS);
    await Promise.resolve();
    expect(listPreviewers).toHaveBeenCalledTimes(1);
  });
});

describe("rescanPreviewers — the Reload button", () => {
  it("re-scans the drop-in directories before re-reading the listing", async () => {
    // The order is the whole point: the listing answers from the in-memory
    // registry, so re-fetching without the scan re-reads the stale answer.
    const calls: string[] = [];
    reloadPreviewers.mockImplementation(() => {
      calls.push("scan");
      return Promise.resolve({ reloaded: 0, added: [], removed: [], diagnostics: [] });
    });
    listPreviewers.mockImplementation(() => {
      calls.push("list");
      return Promise.resolve({ previewers: [], diagnostics: [] });
    });

    await rescanPreviewers();

    expect(calls).toEqual(["scan", "list"]);
  });

  it("still re-reads the listing when the re-scan fails", async () => {
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});
    reloadPreviewers.mockRejectedValue(new Error("offline"));

    await expect(rescanPreviewers()).resolves.toBeUndefined();

    expect(listPreviewers).toHaveBeenCalled();
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
    listPreviewerChoices.mockImplementation(
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
    setPreviewerChoice.mockResolvedValue({ choices: [written] });

    const fetch = loadPreviewerCatalog({ force: true });
    await vi.waitFor(() => expect(listPreviewerChoices).toHaveBeenCalledTimes(1));
    await choosePreviewer("Spectrum", "user.spectrum.view", "user");
    expect(useAppStore.getState().previewerChoices).toEqual([written]);

    // The pre-write listing lands late; the epoch guard drops it.
    resolveChoices({ choices: [] });
    await fetch;
    expect(useAppStore.getState().previewerChoices).toEqual([written]);
  });

  it("a written choice applies the returned choices and bumps the routing epoch", async () => {
    const choice = {
      target_type: "Spectrum",
      previewer_id: "user.spectrum.view",
      scope: "user",
      available: true,
    };
    setPreviewerChoice.mockResolvedValue({ choices: [choice] });
    const versionBefore = useAppStore.getState().previewerChoiceVersion;

    await choosePreviewer("Spectrum", "user.spectrum.view", "user");

    expect(setPreviewerChoice).toHaveBeenCalledWith("Spectrum", "user.spectrum.view", "user");
    expect(useAppStore.getState().previewerChoices).toEqual([choice]);
    expect(useAppStore.getState().previewerChoiceVersion).toBe(versionBefore + 1);
  });

  it("a cleared choice also bumps the routing epoch", async () => {
    clearPreviewerChoice.mockResolvedValue({ choices: [] });
    const versionBefore = useAppStore.getState().previewerChoiceVersion;

    await clearPreviewerChoiceAt("Spectrum", "project");

    expect(clearPreviewerChoice).toHaveBeenCalledWith("Spectrum", "project");
    expect(useAppStore.getState().previewerChoiceVersion).toBe(versionBefore + 1);
  });
});
