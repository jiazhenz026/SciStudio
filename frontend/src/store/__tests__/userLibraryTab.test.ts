// ADR-053 FR-032 — the user library's own editable tab.
//
// A library file lives outside every project root, so the project-file tab
// path cannot reach it (spec §2.3 / FR-009). Without this tab, choosing the
// library destination in the new-file flow would write a template the user
// could not then edit.

import { beforeEach, describe, expect, it, vi } from "vitest";

import type * as LibApi from "../../lib/api";
import { useAppStore } from "../index";
import { resetAppStore } from "../../testUtils";

const getUserLibraryFile = vi.fn();
const putUserLibraryFile = vi.fn();
const putProjectFile = vi.fn();

vi.mock("../../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof LibApi>();
  return {
    ...actual,
    api: {
      ...actual.api,
      getUserLibraryFile: (...args: unknown[]) => getUserLibraryFile(...args),
      putUserLibraryFile: (...args: unknown[]) => putUserLibraryFile(...args),
      putProjectFile: (...args: unknown[]) => putProjectFile(...args),
    },
  };
});

beforeEach(() => {
  resetAppStore();
  useAppStore.setState({ tabs: [], activeTabId: null });
  vi.clearAllMocks();
  getUserLibraryFile.mockImplementation(async (target: string, filename: string) => ({
    target,
    filename,
    path: `/home/dev/.scistudio/${target}/${filename}`,
    content: "print(1)\n",
    mtime: 42,
    size: 9,
  }));
  putUserLibraryFile.mockImplementation(async (target: string, filename: string) => ({
    target,
    filename,
    path: `/home/dev/.scistudio/${target}/${filename}`,
    mtime: 43,
    size: 9,
    kind: "modified",
    registries_refreshed: true,
  }));
});

describe("openUserLibraryFileTab", () => {
  it("opens an editable tab reading through the library endpoint", async () => {
    useAppStore.getState().openUserLibraryFileTab("blocks", "normalize.py");
    await vi.waitFor(() => {
      const tab = useAppStore.getState().tabs[0];
      expect(tab.kind === "file" && tab.loading).toBe(false);
    });

    const tab = useAppStore.getState().tabs[0];
    expect(tab.kind).toBe("file");
    if (tab.kind !== "file") return;
    expect(getUserLibraryFile).toHaveBeenCalledWith("blocks", "normalize.py");
    expect(tab.userLibraryTarget).toBe("blocks");
    expect(tab.filePath).toBe("/home/dev/.scistudio/blocks/normalize.py");
    expect(tab.content).toBe("print(1)\n");
    // Editable — a library file the user cannot edit would make the library
    // destination strictly worse than the project one.
    expect(tab.readOnly).toBe(false);
    expect(useAppStore.getState().activeTabId).toBe("user-library:blocks:normalize.py");
  });

  it("saves back through the library endpoint, never the project one", async () => {
    useAppStore.getState().openUserLibraryFileTab("types", "spectrum.py");
    await vi.waitFor(() => {
      const tab = useAppStore.getState().tabs[0];
      expect(tab.kind === "file" && tab.loading).toBe(false);
    });
    const id = useAppStore.getState().tabs[0].id;

    useAppStore.getState().updateFileTabContent(id, "edited\n");
    await useAppStore.getState().saveFileTab(id);

    expect(putUserLibraryFile).toHaveBeenCalledWith("types", "spectrum.py", "edited\n", {
      overwrite: true,
    });
    // FR-009 — this spec adds a second door; it does not widen the first.
    expect(putProjectFile).not.toHaveBeenCalled();
  });

  it("is dropped from persistence, like a block-source tab", async () => {
    useAppStore.getState().openUserLibraryFileTab("blocks", "normalize.py");
    await vi.waitFor(() => {
      expect(useAppStore.getState().tabs).toHaveLength(1);
    });
    // The persisted snapshot is the store's own partialize output.
    const persisted = JSON.parse(localStorage.getItem("scistudio-studio-ui") ?? "{}");
    expect(persisted.state?.tabs ?? []).toEqual([]);
  });
});
