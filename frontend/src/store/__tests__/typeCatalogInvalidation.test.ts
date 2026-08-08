// ADR-053 FR-010 / FR-062 — the type catalogue is a cache of runtime truth,
// so it must be dropped whenever the registries it describes are rebuilt.
//
// Reported by an external review of PR #2036: after the first successful fetch
// the loader's early return made the cache permanent unless a caller passed
// `force`, and nothing did except the Data types tab's manual Reload button.
// The `blocks.reloaded` websocket handler bumped only the block counter, and a
// user-library write emitted no type invalidation at all — so saving a type,
// installing a package or switching a branch left the Data types tab and the
// declared canvas colours describing a registry that no longer existed.

import { beforeEach, describe, expect, it, vi } from "vitest";

import type * as Api from "../../lib/api";
import type * as CodeApi from "../../lib/api/code";
import { dispatchWorkflowEvent } from "../../hooks/useWebSocket.parts/dispatchEvent";
import { resetAppStore } from "../../testUtils";
import type { WorkflowEventMessage } from "../../types/api";
import { useAppStore } from "../index";
import {
  invalidateTypeCatalog,
  loadTypeCatalog,
  rescanTypes,
  resetTypeCatalogLoader,
} from "../useTypeCatalog";

const listTypes = vi.fn();
const reloadTypes = vi.fn();
vi.mock("../../lib/api/code", async (importOriginal) => {
  const actual = await importOriginal<typeof CodeApi>();
  return {
    codeApi: {
      ...actual.codeApi,
      listTypes: () => listTypes(),
      reloadTypes: () => reloadTypes(),
    },
  };
});

const putUserLibraryFile = vi.fn();
vi.mock("../../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof Api>();
  return {
    ...actual,
    api: {
      ...actual.api,
      putUserLibraryFile: (...args: unknown[]) => putUserLibraryFile(...args),
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
  resetTypeCatalogLoader();
  listTypes.mockReset();
  listTypes.mockResolvedValue({ types: [] });
  putUserLibraryFile.mockReset();
  putUserLibraryFile.mockResolvedValue({
    path: "/home/dev/.scistudio/types/s.py",
    kind: "created",
  });
});

describe("the type catalogue is invalidated, not cached forever", () => {
  it("does not re-fetch while nothing has invalidated it", async () => {
    await loadTypeCatalog();
    await loadTypeCatalog();
    expect(listTypes).toHaveBeenCalledTimes(1);
  });

  it("re-fetches on the blocks.reloaded registry event", async () => {
    await loadTypeCatalog();
    expect(useAppStore.getState().typesLoaded).toBe(true);

    dispatchWorkflowEvent(event("blocks.reloaded"), DEPS);
    await vi.waitFor(() => expect(listTypes).toHaveBeenCalledTimes(2));
  });

  it("leaves unrelated websocket events alone", async () => {
    await loadTypeCatalog();
    dispatchWorkflowEvent(event("git.head_changed"), DEPS);
    dispatchWorkflowEvent(event("block_pty_closed"), DEPS);
    await Promise.resolve();
    expect(listTypes).toHaveBeenCalledTimes(1);
  });

  it("re-fetches after a user-library write", async () => {
    const { createPromotionIo } = await import("../../components/promotion/promotionIo");
    await loadTypeCatalog();

    await createPromotionIo(null).write("types", "spectrum.py", "x = 1\n", { overwrite: false });

    await vi.waitFor(() => expect(listTypes).toHaveBeenCalledTimes(2));
  });

  it("queues a forced reload behind an in-flight fetch instead of joining it", async () => {
    // The running request may have left the browser before the write that
    // invalidated the cache landed, so joining it would answer the new
    // question with the pre-write listing.
    let release: (() => void) | null = null;
    listTypes.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          release = () => resolve({ types: [] });
        }),
    );

    const first = loadTypeCatalog();
    await vi.waitFor(() => expect(release).not.toBeNull());
    invalidateTypeCatalog();
    release!();
    await first;

    await vi.waitFor(() => expect(listTypes).toHaveBeenCalledTimes(2));
  });
});

describe("rescanTypes — the Reload button (FR-062)", () => {
  it("re-scans the drop-in directories before re-reading the listing", async () => {
    // The order is the whole point. `listTypes` answers from the in-memory
    // registry, so re-fetching without the scan re-reads the same stale answer
    // — which is exactly what the button used to do.
    const calls: string[] = [];
    reloadTypes.mockImplementation(() => {
      calls.push("scan");
      return Promise.resolve({ reloaded: 0, added: [], removed: [] });
    });
    listTypes.mockImplementation(() => {
      calls.push("list");
      return Promise.resolve({ types: [] });
    });

    await rescanTypes();

    expect(calls).toEqual(["scan", "list"]);
  });

  it("still re-reads the listing when the re-scan fails", async () => {
    // A reload that cannot reach the backend should leave the tab showing what
    // it had, not empty it or throw out of the click handler.
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});
    reloadTypes.mockRejectedValue(new Error("offline"));
    listTypes.mockResolvedValue({ types: [] });

    await expect(rescanTypes()).resolves.toBeUndefined();

    expect(listTypes).toHaveBeenCalled();
    expect(consoleError).toHaveBeenCalled();
    consoleError.mockRestore();
  });
});
