// ADR-053 §8 — the new-file flows (FR-029 – FR-033).
//
// One flow serves "New custom block" and "New data type"; the test drives both
// through the real `useProjectActions` hook and the real destination dialog,
// so what it asserts is the shipped path and not a restatement of it.

import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type * as LibApi from "../../lib/api";
import { ApiError } from "../../lib/api";
import { UserLibraryDialogs } from "../../components/promotion/UserLibraryDialogs";
import { resetDialogChannel } from "../../components/promotion/dialogChannel";
import { useAppStore } from "../../store";
import { resetAppStore } from "../../testUtils";
import type { ProjectResponse } from "../../types/api";
import { useProjectActions, type ProjectActions } from "../useProjectActions";

const getProjectFile = vi.fn();
const getUserLibraryFile = vi.fn();
const putProjectFile = vi.fn();
const putUserLibraryFile = vi.fn();
const getBlockTemplate = vi.fn();
const getTypeTemplate = vi.fn();

vi.mock("../../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof LibApi>();
  return {
    ...actual,
    api: {
      ...actual.api,
      getProjectFile: (...args: unknown[]) => getProjectFile(...args),
      getUserLibraryFile: (...args: unknown[]) => getUserLibraryFile(...args),
      putProjectFile: (...args: unknown[]) => putProjectFile(...args),
      putUserLibraryFile: (...args: unknown[]) => putUserLibraryFile(...args),
      getBlockTemplate: (...args: unknown[]) => getBlockTemplate(...args),
      getTypeTemplate: (...args: unknown[]) => getTypeTemplate(...args),
    },
  };
});

const PROJECT = {
  id: "p1",
  name: "Proj",
  path: "/proj",
  workflows: [],
} as unknown as ProjectResponse;

const BLOCK_TEMPLATE = "from scistudio.core.block import Block\n";
const TYPE_TEMPLATE = [
  "from scistudio.core.types.base import DataObject",
  "",
  "",
  "class MyDataType(DataObject):",
  '    """A data type of my own."""',
  "",
  "    # ui_color = '#4f8ef7'",
  "",
].join("\n");

const openFileTab = vi.fn();
const openUserLibraryFileTab = vi.fn();
/** Every `validate` the flows handed to the prompt, for the FR-033 check. */
const validators: Array<(value: string) => string | null> = [];
/** Every `defaultValue` the flows handed to the prompt, for the FR-011b check. */
const defaults: Array<string | undefined> = [];
let actions: ProjectActions;

function Harness() {
  actions = useProjectActions({
    currentProject: PROJECT,
    setCurrentProject: vi.fn(),
    setWorkflow: vi.fn(),
    resetExecution: vi.fn(),
    openTab: vi.fn(),
    openFileTab,
    closeProjectDialog: vi.fn(),
    setLastError: vi.fn(),
    refreshProjects: vi.fn(async () => undefined),
    refreshBlocks: vi.fn(async () => undefined),
    setBusy: vi.fn(),
    promptInput: vi.fn(async (opts) => {
      if (opts.validate) validators.push(opts.validate);
      defaults.push(opts.defaultValue);
      return "my_thing";
    }),
  });
  return <UserLibraryDialogs />;
}

function missing(): ApiError {
  return new ApiError("File not found", 404);
}

beforeEach(() => {
  resetAppStore();
  resetDialogChannel();
  vi.clearAllMocks();
  validators.length = 0;
  defaults.length = 0;
  useAppStore.setState({ openUserLibraryFileTab });
  // 404 = "safe to create", for both probes.
  getProjectFile.mockRejectedValue(missing());
  getUserLibraryFile.mockRejectedValue(missing());
  putProjectFile.mockResolvedValue({ mtime: 1 });
  putUserLibraryFile.mockResolvedValue({
    path: "/home/dev/.scistudio/blocks/my_thing.py",
    kind: "created",
  });
  getBlockTemplate.mockResolvedValue({
    content: BLOCK_TEMPLATE,
    suggested_filename: "my_block.py",
  });
  getTypeTemplate.mockResolvedValue({
    content: TYPE_TEMPLATE,
    suggested_filename: "my_data_type.py",
  });
});

afterEach(() => {
  cleanup();
});

/** Start a flow and answer the FR-029 destination question. */
async function run(start: () => Promise<void>, destination: "library" | "project"): Promise<void> {
  const pending = start();
  await screen.findByTestId("file-destination-dialog");
  fireEvent.click(screen.getByTestId(`file-destination-${destination}`));
  await act(async () => {
    await pending;
  });
}

describe("FR-029 — the new-file flow asks where the file goes (E4)", () => {
  it("asks before anything is written, and names both real directories", async () => {
    render(<Harness />);
    const pending = actions.createNewCustomBlock();
    const dialog = await screen.findByTestId("file-destination-dialog");

    expect(dialog).toHaveTextContent("~/.scistudio/blocks/");
    expect(dialog).toHaveTextContent("Proj");
    // Nothing has been probed or written while the question is open.
    expect(getProjectFile).not.toHaveBeenCalled();
    expect(putProjectFile).not.toHaveBeenCalled();

    fireEvent.click(screen.getByTestId("file-destination-cancel"));
    await act(async () => {
      await pending;
    });
    expect(putProjectFile).not.toHaveBeenCalled();
    expect(putUserLibraryFile).not.toHaveBeenCalled();
  });
});

describe("FR-030 / FR-031 — the choice routes the probe and the write", () => {
  it("project: probes the project endpoint and keeps putProjectFile", async () => {
    render(<Harness />);
    await run(() => actions.createNewCustomBlock(), "project");

    expect(getProjectFile).toHaveBeenCalledWith("p1", "blocks/my_thing.py");
    expect(getUserLibraryFile).not.toHaveBeenCalled();
    expect(putProjectFile).toHaveBeenCalledWith("p1", "blocks/my_thing.py", BLOCK_TEMPLATE, {
      createParentDirs: true,
    });
    expect(putUserLibraryFile).not.toHaveBeenCalled();
    expect(openFileTab).toHaveBeenCalledWith("blocks/my_thing.py");
  });

  it("library: probes the library endpoint and writes through it", async () => {
    render(<Harness />);
    await run(() => actions.createNewCustomBlock(), "library");

    expect(getUserLibraryFile).toHaveBeenCalledWith("blocks", "my_thing.py");
    expect(getProjectFile).not.toHaveBeenCalled();
    expect(putUserLibraryFile).toHaveBeenCalledWith("blocks", "my_thing.py", BLOCK_TEMPLATE, {
      overwrite: false,
    });
    expect(putProjectFile).not.toHaveBeenCalled();
    // FR-032 — the file opens for editing at whichever destination it landed.
    expect(openUserLibraryFileTab).toHaveBeenCalledWith("blocks", "my_thing.py");
  });

  it("refuses to create over an existing file at the chosen destination", async () => {
    const alert = vi.spyOn(window, "alert").mockImplementation(() => undefined);
    getUserLibraryFile.mockResolvedValue({ content: "existing" });
    render(<Harness />);
    await run(() => actions.createNewCustomBlock(), "library");

    expect(putUserLibraryFile).not.toHaveBeenCalled();
    expect(alert).toHaveBeenCalledWith(expect.stringContaining("already exists in your library"));
    alert.mockRestore();
  });
});

describe("FR-032 — New data type", () => {
  it("fetches the type template and lands a DataObject skeleton in the project", async () => {
    render(<Harness />);
    await run(() => actions.createNewDataType(), "project");

    expect(getTypeTemplate).toHaveBeenCalledWith("basic");
    expect(getBlockTemplate).not.toHaveBeenCalled();
    expect(putProjectFile).toHaveBeenCalledWith("p1", "types/my_thing.py", TYPE_TEMPLATE, {
      createParentDirs: true,
    });
    const written = putProjectFile.mock.calls[0][2] as string;
    expect(written).toContain("DataObject");
    expect(written).toContain("class ");
    expect(openFileTab).toHaveBeenCalledWith("types/my_thing.py");
  });

  it("lands in the user library's types directory when that is chosen", async () => {
    render(<Harness />);
    await run(() => actions.createNewDataType(), "library");

    expect(putUserLibraryFile).toHaveBeenCalledWith("types", "my_thing.py", TYPE_TEMPLATE, {
      overwrite: false,
    });
    expect(openUserLibraryFileTab).toHaveBeenCalledWith("types", "my_thing.py");
  });
});

describe("FR-033 — the two flows share their steps", () => {
  it("runs the same prompt, probe, write and open sequence for both kinds", async () => {
    render(<Harness />);
    await run(() => actions.createNewCustomBlock(), "project");
    const blockCalls = {
      probe: getProjectFile.mock.calls.length,
      write: putProjectFile.mock.calls.length,
      open: openFileTab.mock.calls.length,
    };

    await run(() => actions.createNewDataType(), "project");
    expect({
      probe: getProjectFile.mock.calls.length - blockCalls.probe,
      write: putProjectFile.mock.calls.length - blockCalls.write,
      open: openFileTab.mock.calls.length - blockCalls.open,
    }).toEqual(blockCalls);

    // Only the target subdirectory and the template kind differ.
    expect(getProjectFile.mock.calls.map((call) => call[1])).toEqual([
      "blocks/my_thing.py",
      "types/my_thing.py",
    ]);
    expect(putProjectFile.mock.calls.map((call) => call[2])).toEqual([
      BLOCK_TEMPLATE,
      TYPE_TEMPLATE,
    ]);
  });

  it("shares one Python-identifier validator, not two copies", async () => {
    render(<Harness />);
    await run(() => actions.createNewCustomBlock(), "project");
    await run(() => actions.createNewDataType(), "project");

    expect(validators).toHaveLength(2);
    for (const validate of validators) {
      expect(validate("")).toMatch(/must not be empty/);
      expect(validate("2bad")).toMatch(/Python identifier/);
      expect(validate("good_name")).toBeNull();
    }
    // The same function object — two copies could drift.
    expect(validators[0]).toBe(validators[1]);
  });
});

describe("ADR-053 FR-011b — a tutorial step seeds the filename", () => {
  /** A session parked on a step that prefills the New custom block dialog. */
  function sessionSeeding(filename: string): void {
    useAppStore.setState({
      learningCenterSession: {
        source_kind: "core",
        source_id: "",
        tutorial_id: "welcome-to-scistudio",
        title: "Welcome to SciStudio",
        project_id: "p1",
        project_path: "/proj",
        step: {
          id: "create-the-block",
          index: 4,
          total: 15,
          title: null,
          say: "Press New, choose New custom block.",
          highlight: null,
          route_to: "canvas",
          prefill: [{ target: "new_custom_block", args: { filename } }],
          awaiting_continue: false,
          satisfied: false,
        },
        satisfied_step_ids: [],
        status: "active",
        error: null,
        replay: null,
      },
    });
  }

  it("opens the dialog holding the name the step named", async () => {
    sessionSeeding("normalize_fluorescence");
    render(<Harness />);

    await run(() => actions.createNewCustomBlock(), "project");

    expect(defaults).toEqual(["normalize_fluorescence"]);
  });

  it("leaves the product default alone when no tutorial is running", async () => {
    render(<Harness />);

    await run(() => actions.createNewCustomBlock(), "project");

    expect(defaults).toEqual(["my_block"]);
  });

  it("seeds only the dialog it names, so the type flow keeps its own default", async () => {
    sessionSeeding("normalize_fluorescence");
    render(<Harness />);

    await run(() => actions.createNewDataType(), "project");

    expect(defaults).toEqual(["my_data_type"]);
  });
});
