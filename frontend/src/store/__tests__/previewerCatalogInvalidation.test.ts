// #2113 — the previewer catalogue is a cache of runtime truth, so it must be
// dropped when the previewers it describes change. #2465: the panel service
// says when (`blocks.reloaded` with `registry: "panels"` and
// `preview_candidates_changed`, or `panel.choices_changed`); any other
// registry reload leaves the listing and every open preview alone.

import { beforeEach, describe, expect, it, vi } from "vitest";

import type * as DataApi from "../../lib/api/data";
import { dispatchWorkflowEvent } from "../../hooks/useWebSocket.parts/dispatchEvent";
import { resetAppStore } from "../../testUtils";
import type { WorkflowEventMessage } from "../../types/api";
import * as panelEvents from "../../panels/panelEvents";
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
  upsertInteractivePrompt: vi.fn(),
  setWorkflow: vi.fn(),
};

function event(type: string, data: Record<string, unknown> = {}): WorkflowEventMessage {
  return { type, data, timestamp: "2026-08-08T00:00:00Z" } as WorkflowEventMessage;
}

function panelCatalog(data: Record<string, unknown>): WorkflowEventMessage {
  return event("blocks.reloaded", {
    added: [],
    removed: [],
    reloaded: [],
    registry: "panels",
    panels: { added: [], removed: [], changed: [] },
    miniapps_changed: false,
    preview_candidates_changed: false,
    preview_types: [],
    legacy_reloaded: false,
    ...data,
  });
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

  it("re-fetches when the panel service says the preview candidates changed", async () => {
    await loadPreviewerCatalog();
    expect(useAppStore.getState().previewersLoaded).toBe(true);

    dispatchWorkflowEvent(
      panelCatalog({ preview_candidates_changed: true, preview_types: ["Image"] }),
      DEPS,
    );
    await vi.waitFor(() => expect(listPreviewers).toHaveBeenCalledTimes(2));
    await vi.waitFor(() => expect(listPreviewerChoices).toHaveBeenCalledTimes(2));
  });

  it("does not re-fetch or re-route on a block reload or a MiniApp-only change (#2465 D12)", async () => {
    await loadPreviewerCatalog();
    const reroutes: unknown[] = [];
    const stop = panelEvents.subscribePreviewReroute((signal) => reroutes.push(signal));
    const blocksBefore = useAppStore.getState().blockCatalogRefreshCounter;

    dispatchWorkflowEvent(
      event("blocks.reloaded", { added: ["x"], removed: [], reloaded: ["x"] }),
      DEPS,
    );
    dispatchWorkflowEvent(
      panelCatalog({ miniapps_changed: true, panels: { added: ["app"] } }),
      DEPS,
    );
    await Promise.resolve();

    expect(listPreviewers).toHaveBeenCalledTimes(1);
    expect(reroutes).toEqual([]);
    // The block catalog and, through it, the MiniApp list (#2459) still re-read.
    expect(useAppStore.getState().blockCatalogRefreshCounter).toBe(blocksBefore + 2);
    stop();
  });

  it("re-routes only the previews the changed claims concern", async () => {
    const reroutes: panelEvents.PreviewRerouteSignal[] = [];
    const stop = panelEvents.subscribePreviewReroute((signal) => reroutes.push(signal));

    dispatchWorkflowEvent(
      panelCatalog({
        preview_candidates_changed: true,
        preview_types: ["Collection[Image]"],
        legacy_reloaded: true,
      }),
      DEPS,
    );

    expect(reroutes).toEqual([{ types: ["Collection[Image]"], legacy: true }]);
    stop();
  });

  it("re-routes the previews of one type on panel.choices_changed", async () => {
    const reroutes: panelEvents.PreviewRerouteSignal[] = [];
    const stop = panelEvents.subscribePreviewReroute((signal) => reroutes.push(signal));

    dispatchWorkflowEvent(event("panel.choices_changed", { type: "Spectrum" }), DEPS);

    expect(reroutes).toEqual([{ choiceType: "Spectrum" }]);
    await vi.waitFor(() => expect(listPreviewerChoices).toHaveBeenCalledTimes(1));
    stop();
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

describe("choice mutations (#2049 / #2113)", () => {
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

  it("a written choice applies the returned choices", async () => {
    const choice = {
      target_type: "Spectrum",
      previewer_id: "user.spectrum.view",
      scope: "user",
      available: true,
    };
    setPreviewerChoice.mockResolvedValue({ choices: [choice] });

    await choosePreviewer("Spectrum", "user.spectrum.view", "user");

    expect(setPreviewerChoice).toHaveBeenCalledWith("Spectrum", "user.spectrum.view", "user");
    expect(useAppStore.getState().previewerChoices).toEqual([choice]);
  });

  it("a cleared choice applies the returned choices", async () => {
    clearPreviewerChoice.mockResolvedValue({ choices: [] });

    await clearPreviewerChoiceAt("Spectrum", "project");

    expect(clearPreviewerChoice).toHaveBeenCalledWith("Spectrum", "project");
    expect(useAppStore.getState().previewerChoices).toEqual([]);
  });
});
