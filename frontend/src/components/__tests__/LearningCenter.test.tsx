/**
 * ADR-053 Learning Center (#2057) — spec §4.4's frontend row.
 *
 * Asserts grouped rendering, the four entry states, the FR-086 dot appearing
 * and clearing, and that the FR-088 clear confirmation names the directories.
 * The last one is the point of the requirement rather than a detail of it: the
 * action's label describes the user's intent ("clear progress") while its
 * effect is deleting folders, and the two must not diverge silently — so the
 * test reads the directory strings, not the button.
 */

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type * as LearningCenterModule from "../../lib/api/learningCenter";
import {
  learningCenterApi,
  type TutorialCatalogueEntry,
  type TutorialCatalogueResponse,
} from "../../lib/api/learningCenter";
import { useAppStore } from "../../store";
import { resetAppStore } from "../../testUtils";
import { LearningCenter } from "../LearningCenter";
import { Toolbar } from "../Toolbar";

vi.mock("../../lib/api/learningCenter", async (importOriginal) => {
  const actual = await importOriginal<typeof LearningCenterModule>();
  return {
    ...actual,
    learningCenterApi: {
      getTutorialCatalogue: vi.fn(),
      getActiveTutorialSession: vi.fn(),
      startTutorialSession: vi.fn(),
      evaluateActiveTutorialStep: vi.fn(),
      reportTutorialUiEvent: vi.fn(),
      continueActiveTutorialStep: vi.fn(),
      leaveActiveTutorialSession: vi.fn(),
      getTutorialProgress: vi.fn(),
      previewTutorialDataClear: vi.fn(),
      clearTutorialData: vi.fn(),
      getTutorialUnlock: vi.fn(),
      dismissTutorialUnlock: vi.fn(),
    },
  };
});

function entry(overrides: Partial<TutorialCatalogueEntry> = {}): TutorialCatalogueEntry {
  return {
    source_kind: "core",
    source_id: "",
    id: "first-workflow",
    title: "Run your first workflow",
    summary: "Load a dataset, normalise it, and plot the result.",
    cover_url: null,
    order: 0,
    state: "not_started",
    unavailable_reason: null,
    project_directory: null,
    ...overrides,
  };
}

/**
 * A catalogue with a core group and a package group.
 *
 * The package group is deliberately ahead of core on its own count — FR-076
 * reports per group with no aggregate, and FR-080 keeps package progress from
 * driving anything, so a finished package group must not read as progress.
 */
function catalogue(overrides: Partial<TutorialCatalogueResponse> = {}): TutorialCatalogueResponse {
  return {
    groups: [
      {
        source_kind: "package",
        source_id: "scistudio-blocks-imaging",
        label: "Imaging",
        completed: 2,
        total: 2,
        tutorials: [
          entry({
            source_kind: "package",
            source_id: "scistudio-blocks-imaging",
            id: "segmentation",
            title: "Segment cells",
            summary: "Threshold and label an image stack.",
            state: "complete",
          }),
          entry({
            source_kind: "package",
            source_id: "scistudio-blocks-imaging",
            id: "tracking",
            title: "Track objects",
            summary: "Follow labelled objects across frames.",
            state: "complete",
          }),
        ],
      },
      {
        source_kind: "core",
        source_id: "",
        label: "SciStudio",
        completed: 1,
        total: 4,
        tutorials: [
          entry({ id: "first-workflow", title: "Run your first workflow", state: "complete" }),
          entry({
            id: "custom-block",
            title: "Write a custom block",
            state: "in_progress",
            project_directory: "/Users/rosalind/SciStudio Tutorials/custom-block",
          }),
          entry({ id: "history", title: "Recover work from History", state: "not_started" }),
          entry({
            id: "lcms-intro",
            title: "Analyse an LC-MS run",
            state: "unavailable",
            unavailable_reason: "Install the scistudio-blocks-lcms package to run this tutorial.",
          }),
        ],
      },
    ],
    active: null,
    diagnostics: [],
    ...overrides,
  };
}

function toolbarProps(): React.ComponentProps<typeof Toolbar> {
  return {
    currentProject: null,
    workflowId: null,
    workflowName: "main",
    workflowDirty: false,
    selectedNodeId: null,
    wsConnected: true,
    sseConnected: true,
    recentProjects: [],
    onNewProject: vi.fn(),
    onOpenProject: vi.fn(),
    onOpenRecent: vi.fn(),
    onCloseProject: vi.fn(),
    onNewWorkflow: vi.fn(),
    onSave: vi.fn(),
    onSaveAs: vi.fn(),
    onImport: vi.fn(),
    onRun: vi.fn(),
    onPause: vi.fn(),
    onResume: vi.fn(),
    onStop: vi.fn(),
    onReset: vi.fn(),
    onDelete: vi.fn(),
    onReloadBlocks: vi.fn(),
    onStartFromSelected: vi.fn(),
    onAddAnnotation: vi.fn(),
    isRunning: false,
  } as React.ComponentProps<typeof Toolbar>;
}

/** Open the panel and wait for the catalogue fetch it fires on open. */
async function renderOpenPanel(response: TutorialCatalogueResponse = catalogue()) {
  vi.mocked(learningCenterApi.getTutorialCatalogue).mockResolvedValue(response);
  useAppStore.setState({ learningCenterOpen: true });
  render(<LearningCenter />);
  await screen.findByTestId("learning-center");
  await waitFor(() => expect(learningCenterApi.getTutorialCatalogue).toHaveBeenCalled());
}

beforeEach(() => {
  vi.clearAllMocks();
  resetAppStore();
});

afterEach(cleanup);

describe("Learning Center — grouped catalogue (FR-084, FR-076)", () => {
  it("lists tutorials grouped by source, each group labelled with its own count", async () => {
    await renderOpenPanel();

    expect(await screen.findByTestId("tutorial-group-core-")).toBeInTheDocument();
    expect(
      screen.getByTestId("tutorial-group-package-scistudio-blocks-imaging"),
    ).toBeInTheDocument();

    // Each group's own count, and no aggregate across them.
    expect(screen.getByText("1 of 4 complete")).toBeInTheDocument();
    expect(screen.getByText("2 of 2 complete")).toBeInTheDocument();
    expect(screen.queryByText("3 of 6 complete")).not.toBeInTheDocument();

    // Group labels name their origin.
    expect(screen.getByText("SciStudio")).toBeInTheDocument();
    expect(screen.getByText("Imaging")).toBeInTheDocument();
  });

  it("puts the core group first even when the backend returns it second", async () => {
    await renderOpenPanel();

    const groups = await screen.findAllByTestId(/^tutorial-group-/);
    expect(groups.map((node) => node.getAttribute("data-testid"))).toEqual([
      "tutorial-group-core-",
      "tutorial-group-package-scistudio-blocks-imaging",
    ]);
  });

  it("states that tutorial projects are temporary (FR-068)", async () => {
    await renderOpenPanel();
    expect(await screen.findByText(/Tutorial projects are temporary/)).toBeInTheDocument();
    expect(screen.getByText(/Do your own work in your own project/)).toBeInTheDocument();
  });
});

describe("Learning Center — entry states (FR-085)", () => {
  it("shows title, summary, and each of the four states", async () => {
    await renderOpenPanel();

    const first = await screen.findByTestId("tutorial-entry-core--first-workflow");
    expect(first).toHaveTextContent("Run your first workflow");
    expect(first).toHaveTextContent("Load a dataset, normalise it, and plot the result.");

    expect(screen.getAllByText("Complete").length).toBeGreaterThan(0);
    expect(screen.getByText("In progress")).toBeInTheDocument();
    expect(screen.getByText("Not started")).toBeInTheDocument();
    expect(screen.getByText("Unavailable")).toBeInTheDocument();
  });

  it("gives the reason on an unavailable entry, and does not let it be started", async () => {
    await renderOpenPanel();

    expect(
      await screen.findByText("Install the scistudio-blocks-lcms package to run this tutorial."),
    ).toBeInTheDocument();
    expect(screen.getByTestId("tutorial-entry-core--lcms-intro")).toBeDisabled();
  });

  it("shows a cover only when the tutorial declared one", async () => {
    await renderOpenPanel(
      catalogue({
        groups: [
          {
            source_kind: "core",
            source_id: "",
            label: "SciStudio",
            completed: 0,
            total: 2,
            tutorials: [
              entry({ id: "with-cover", cover_url: "/api/tutorials/core//with-cover/cover" }),
              entry({ id: "no-cover", cover_url: null }),
            ],
          },
        ],
      }),
    );

    const covers = await screen.findAllByRole("presentation", { hidden: true }).catch(() => []);
    void covers;
    const images = document.querySelectorAll("img");
    expect(images).toHaveLength(1);
    expect(images[0].getAttribute("src")).toBe("/api/tutorials/core//with-cover/cover");
  });

  it("resumes an in-progress tutorial rather than restarting it (FR-087)", async () => {
    await renderOpenPanel();
    vi.mocked(learningCenterApi.startTutorialSession).mockResolvedValue({
      source_kind: "core",
      source_id: "",
      tutorial_id: "custom-block",
      title: "Write a custom block",
      project_id: "p1",
      project_path: "/Users/rosalind/SciStudio Tutorials/custom-block",
      step: null,
      satisfied_step_ids: [],
      status: "active",
      error: null,
      replay: null,
    });

    fireEvent.click(await screen.findByTestId("tutorial-entry-core--custom-block"));

    await waitFor(() =>
      expect(learningCenterApi.startTutorialSession).toHaveBeenCalledWith({
        source_kind: "core",
        source_id: "",
        tutorial_id: "custom-block",
        restart: false,
      }),
    );
  });
});

describe("Learning Center — restarting a completed tutorial (FR-087, FR-066, FR-067)", () => {
  it("names the project directory the restart will delete, and waits for confirmation", async () => {
    await renderOpenPanel(
      catalogue({
        groups: [
          {
            source_kind: "core",
            source_id: "",
            label: "SciStudio",
            completed: 1,
            total: 1,
            tutorials: [
              entry({
                id: "first-workflow",
                state: "complete",
                project_directory: "/Users/rosalind/SciStudio Tutorials/first-workflow",
              }),
            ],
          },
        ],
      }),
    );

    fireEvent.click(await screen.findByTestId("tutorial-entry-core--first-workflow"));

    const confirmation = await screen.findByTestId("learning-center-restart-confirm");
    expect(confirmation).toHaveTextContent("/Users/rosalind/SciStudio Tutorials/first-workflow");
    // Nothing is started until the confirmation is accepted.
    expect(learningCenterApi.startTutorialSession).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Delete it and start over" }));
    await waitFor(() =>
      expect(learningCenterApi.startTutorialSession).toHaveBeenCalledWith(
        expect.objectContaining({ tutorial_id: "first-workflow", restart: true }),
      ),
    );
  });
});

describe("Learning Center — clearing tutorial data (FR-088)", () => {
  it("names every directory to be deleted before anything is deleted", async () => {
    await renderOpenPanel();
    vi.mocked(learningCenterApi.previewTutorialDataClear).mockResolvedValue({
      directories: [
        "/Users/rosalind/SciStudio Tutorials/first-workflow",
        "/Users/rosalind/SciStudio Tutorials/custom-block",
        "/Users/rosalind/SciStudio Tutorials/.library",
      ],
    });

    fireEvent.click(await screen.findByRole("button", { name: "Clear tutorial data" }));

    const confirmation = await screen.findByTestId("learning-center-clear-confirm");
    expect(confirmation).toHaveTextContent("/Users/rosalind/SciStudio Tutorials/first-workflow");
    expect(confirmation).toHaveTextContent("/Users/rosalind/SciStudio Tutorials/custom-block");
    expect(confirmation).toHaveTextContent("/Users/rosalind/SciStudio Tutorials/.library");
    expect(learningCenterApi.clearTutorialData).not.toHaveBeenCalled();
  });

  it("deletes only once the confirmation is accepted, and reports what went", async () => {
    await renderOpenPanel();
    vi.mocked(learningCenterApi.previewTutorialDataClear).mockResolvedValue({
      directories: ["/Users/rosalind/SciStudio Tutorials/first-workflow"],
    });
    vi.mocked(learningCenterApi.clearTutorialData).mockResolvedValue({
      deleted_directories: ["/Users/rosalind/SciStudio Tutorials/first-workflow"],
    });

    fireEvent.click(await screen.findByRole("button", { name: "Clear tutorial data" }));
    await screen.findByTestId("learning-center-clear-confirm");
    fireEvent.click(screen.getByRole("button", { name: "Delete them and clear progress" }));

    await waitFor(() => expect(learningCenterApi.clearTutorialData).toHaveBeenCalledTimes(1));
    expect(await screen.findByTestId("learning-center-cleared")).toHaveTextContent(
      "1 directory was deleted",
    );
  });

  it("cancelling deletes nothing", async () => {
    await renderOpenPanel();
    vi.mocked(learningCenterApi.previewTutorialDataClear).mockResolvedValue({
      directories: ["/Users/rosalind/SciStudio Tutorials/first-workflow"],
    });

    fireEvent.click(await screen.findByRole("button", { name: "Clear tutorial data" }));
    await screen.findByTestId("learning-center-clear-confirm");
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));

    await waitFor(() =>
      expect(screen.queryByTestId("learning-center-clear-confirm")).not.toBeInTheDocument(),
    );
    expect(learningCenterApi.clearTutorialData).not.toHaveBeenCalled();
  });
});

describe("toolbar entry and its unfinished-work dot (FR-082, FR-086)", () => {
  it("is a permanent entry that opens the Learning Center", () => {
    render(<Toolbar {...toolbarProps()} />);

    const button = screen.getByRole("button", { name: "Learning Center" });
    expect(button).toBeEnabled();

    fireEvent.click(button);
    expect(useAppStore.getState().learningCenterOpen).toBe(true);
  });

  it("shows the dot when core work is unfinished and the landing was dismissed", () => {
    useAppStore.setState({
      learningCenterCatalogue: catalogue(),
      learningCenterFirstRunDismissed: true,
    });
    render(<Toolbar {...toolbarProps()} />);

    expect(screen.getByTestId("toolbar-learning-center-dot")).toBeInTheDocument();
  });

  it("shows no dot before the first-run landing has been dismissed", () => {
    useAppStore.setState({
      learningCenterCatalogue: catalogue(),
      learningCenterFirstRunDismissed: false,
    });
    render(<Toolbar {...toolbarProps()} />);

    expect(screen.queryByTestId("toolbar-learning-center-dot")).not.toBeInTheDocument();
  });

  it("clears the dot once the core group is complete", () => {
    const complete = catalogue();
    const core = complete.groups.find((group) => group.source_kind === "core");
    if (!core) throw new Error("fixture is missing its core group");
    core.completed = core.total;

    useAppStore.setState({
      learningCenterCatalogue: complete,
      learningCenterFirstRunDismissed: true,
    });
    render(<Toolbar {...toolbarProps()} />);

    expect(screen.queryByTestId("toolbar-learning-center-dot")).not.toBeInTheDocument();
  });

  it("a finished package group does not clear a dot core still owes (FR-080)", () => {
    // The fixture's package group is already 2 of 2; core is 1 of 4.
    useAppStore.setState({
      learningCenterCatalogue: catalogue(),
      learningCenterFirstRunDismissed: true,
    });
    render(<Toolbar {...toolbarProps()} />);

    expect(screen.getByTestId("toolbar-learning-center-dot")).toBeInTheDocument();
  });

  it("offers no permanent dismissal of the dot", () => {
    useAppStore.setState({
      learningCenterCatalogue: catalogue(),
      learningCenterFirstRunDismissed: true,
    });
    render(<Toolbar {...toolbarProps()} />);

    // The only affordance on the entry is opening the panel; there is no
    // "dismiss" or "don't show again" beside it. FR-086 forbids one, because a
    // permanently hidden unfinished tutorial reads as a finished one.
    expect(screen.queryByRole("button", { name: /dismiss/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /don't show/i })).not.toBeInTheDocument();
  });
});
