import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { mockBackend, reply, type MockBackend } from "../../../__tests__/contract/mockBackend";
import { canEditBlockSource, openBlockEditor } from "../blockSourceEditor";

const state = vi.hoisted(() => ({
  currentProject: { id: "project", path: "/project" } as { id: string; path: string } | null,
  openFileTab: vi.fn(),
  openUserLibraryFileTab: vi.fn(),
  openBlockSourceTab: vi.fn(),
}));
const sourceReply = vi.fn();
const libraryReply = vi.fn();
let backend: MockBackend;
const source = (path: string, origin = "project") => ({
  block_type: "actual_block",
  path,
  source: "pass",
  language: "python",
  origin,
});
const library = (path: string) => ({
  target: "blocks",
  filename: "real.py",
  path,
  content: "pass",
  encoding: "utf-8",
  mtime: 1,
  size: 4,
});
vi.mock("../../../store", () => ({ useAppStore: { getState: () => state } }));
const summary = { type_name: "actual_block", origin: "project" } as Parameters<
  typeof openBlockEditor
>[0];

beforeEach(() => {
  vi.resetAllMocks();
  state.currentProject = { id: "project", path: "/project" };
  vi.spyOn(window, "alert").mockImplementation(() => {});
  backend = mockBackend({
    "GET /api/blocks/{block_type}/source": () => sourceReply(),
    "GET /api/user-library/file": () => libraryReply(),
  });
});

afterEach(() => backend.restore());

describe("canvas source editor routing", () => {
  it("opens the registered project source, never a filename guessed from the block type", async () => {
    sourceReply.mockReturnValue(source("/project/blocks/custom_name.py"));
    await openBlockEditor(summary);
    expect(backend.calls[0]?.path).toBe("/api/blocks/actual_block/source");
    expect(state.openFileTab).toHaveBeenCalledWith("blocks/custom_name.py");
  });
  it("opens user source only after the library route confirms the exact file", async () => {
    sourceReply.mockReturnValue(source("/user/blocks/real.py", "user"));
    libraryReply.mockReturnValue(library("/user/blocks/real.py"));
    await openBlockEditor({ ...summary, origin: "user" });
    expect(state.openUserLibraryFileTab).toHaveBeenCalledWith("blocks", "real.py");
  });
  it.each(["builtin", "package", "custom"] as const)(
    "keeps %s sources readonly",
    async (origin) => {
      expect(canEditBlockSource({ ...summary, origin })).toBe(false);
      await openBlockEditor({ ...summary, origin });
      expect(state.openBlockSourceTab).toHaveBeenCalledWith("actual_block");
      expect(sourceReply).not.toHaveBeenCalled();
      expect(state.openFileTab).not.toHaveBeenCalled();
    },
  );
  it("does not substitute another file with the same basename in My Library", async () => {
    sourceReply.mockReturnValue(source("/user/blocks/nested/real.py", "user"));
    libraryReply.mockReturnValue(library("/user/blocks/real.py"));
    await openBlockEditor({ ...summary, origin: "user" });
    expect(state.openUserLibraryFileTab).not.toHaveBeenCalled();
    expect(window.alert).toHaveBeenCalledWith(expect.stringContaining("not the editable file"));
  });
  it("does not open missing source or a response from a departed project", async () => {
    sourceReply.mockReturnValueOnce(reply(404, { detail: "source missing" }));
    await openBlockEditor(summary);
    expect(state.openFileTab).not.toHaveBeenCalled();
    sourceReply.mockImplementationOnce(() => {
      state.currentProject = { id: "other", path: "/other" };
      return source("/project/blocks/real.py");
    });
    await openBlockEditor(summary);
    expect(state.openFileTab).not.toHaveBeenCalled();
    expect(window.alert).toHaveBeenLastCalledWith(expect.stringContaining("project changed"));
  });
  it("rejects a project-prefix lookalike and path traversal", async () => {
    for (const path of ["/project-other/blocks/real.py", "/project/../other.py"]) {
      sourceReply.mockReturnValueOnce(source(path));
      await openBlockEditor(summary);
    }
    expect(state.openFileTab).not.toHaveBeenCalled();
  });
});
