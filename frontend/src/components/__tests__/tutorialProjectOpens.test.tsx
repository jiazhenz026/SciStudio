/**
 * ADR-053 FR-062/FR-063 (#2057) — the tutorial's project is actually opened.
 *
 * These exist because the product shipped without them and the gap reached a
 * live session. A tutorial declaring `bootstrap` gets a project created and
 * registered on the backend, and the session names it — but nothing on the
 * backend can move the user's window. Starting the first tutorial therefore
 * created the project, populated it, advanced to step one, and left the user
 * looking at the welcome pane with no project open. The tutorial read as
 * frozen while being entirely healthy.
 *
 * The whole frontend suite was green at the time. Every test here and in
 * `LearningCenter.test.tsx` asserted something true about one side of a seam:
 * the backend returns `project_id`, the frontend knows how to open a project.
 * Nobody asserted that one calls the other. That is the shape of bug these
 * cover, so they are written against the *seam* rather than against either
 * side of it.
 */

import { cleanup, render, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type * as LearningCenterModule from "../../lib/api/learningCenter";
import { learningCenterApi } from "../../lib/api/learningCenter";
import { useAppStore } from "../../store";
import { resetAppStore } from "../../testUtils";

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

const EMPTY_CATALOGUE = { groups: [], active: null, diagnostics: [] };

function activeSession(overrides: Record<string, unknown> = {}) {
  return {
    source_kind: "core" as const,
    source_id: "",
    tutorial_id: "welcome-to-scistudio",
    title: "Welcome to SciStudio",
    project_id: "project-37f0822e",
    project_path: "/Users/someone/SciStudio Tutorials/welcome-to-scistudio",
    step: {
      id: "drag-load",
      index: 1,
      total: 13,
      title: null,
      say: "Find the Load block in the palette and drag it onto the canvas.",
      highlight: null,
      route_to: null,
      prefill: [],
      awaiting_continue: false,
      satisfied: false,
    },
    satisfied_step_ids: ["welcome"],
    status: "active" as const,
    error: null,
    replay: null,
    ...overrides,
  };
}

async function renderHarness(
  openProject: () => Promise<void> | void,
  closeProject: () => void = vi.fn(),
) {
  const { useLearningCenter } = await import("../../App.parts/useLearningCenter");

  function Harness() {
    useLearningCenter({ wsConnected: true, setLeftTab: vi.fn(), openProject, closeProject });
    return null;
  }

  return render(<Harness />);
}

describe("the project a tutorial session names is opened", () => {
  beforeEach(() => {
    resetAppStore();
    vi.mocked(learningCenterApi.getTutorialCatalogue).mockResolvedValue(EMPTY_CATALOGUE);
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("opens it when a session becomes active", async () => {
    const openProject = vi.fn();
    await renderHarness(openProject);

    useAppStore.setState({ learningCenterSession: activeSession() });

    await waitFor(() => expect(openProject).toHaveBeenCalledWith("project-37f0822e"));
  });

  it("opens it when a half-finished tutorial is resumed", async () => {
    // User Story 2: reopening puts the user back on the same step *in the same
    // project*. The session is already in the store before the hook mounts,
    // which is what resuming looks like from here.
    useAppStore.setState({
      learningCenterSession: activeSession({
        step: {
          id: "run-it",
          index: 7,
          total: 13,
          title: null,
          say: "Press Run.",
          highlight: null,
          route_to: null,
          prefill: [],
          awaiting_continue: false,
          satisfied: false,
        },
      }),
    });

    const openProject = vi.fn();
    await renderHarness(openProject);

    await waitFor(() => expect(openProject).toHaveBeenCalledWith("project-37f0822e"));
  });

  it("leaves the project alone when it is already the open one", async () => {
    useAppStore.setState({
      currentProject: { id: "project-37f0822e" } as never,
      learningCenterSession: activeSession(),
    });

    const openProject = vi.fn();
    await renderHarness(openProject);

    await waitFor(() => expect(learningCenterApi.getTutorialCatalogue).toHaveBeenCalled());
    expect(openProject).not.toHaveBeenCalled();
  });

  it("opens it once, not once per re-render", async () => {
    // Opening a project refreshes the project list and the block catalogue,
    // which re-renders this hook's host before `currentProject` has caught up.
    // Without the in-flight guard that is an open-project loop.
    const openProject = vi.fn();
    await renderHarness(openProject);

    useAppStore.setState({ learningCenterSession: activeSession() });
    await waitFor(() => expect(openProject).toHaveBeenCalledTimes(1));

    useAppStore.setState({ learningCenterError: "an unrelated change" });
    useAppStore.setState({ learningCenterLoading: true });

    await waitFor(() => expect(learningCenterApi.getTutorialCatalogue).toHaveBeenCalled());
    expect(openProject).toHaveBeenCalledTimes(1);
  });

  it("does nothing for a tutorial that declares no bootstrap", async () => {
    // FR-009: a tutorial omitting `bootstrap` runs without a project, so the
    // session carries no project id and there is nothing to open.
    const openProject = vi.fn();
    await renderHarness(openProject);

    useAppStore.setState({
      learningCenterSession: activeSession({ project_id: null, project_path: null }),
    });

    await waitFor(() => expect(learningCenterApi.getTutorialCatalogue).toHaveBeenCalled());
    expect(openProject).not.toHaveBeenCalled();
  });
});

describe("starting a tutorial gets the catalogue out of the way", () => {
  beforeEach(() => {
    resetAppStore();
    vi.mocked(learningCenterApi.getTutorialCatalogue).mockResolvedValue(EMPTY_CATALOGUE);
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("closes the panel once the session is running", async () => {
    /*
     * FR-089: the active step must be shown in a surface that does not occlude
     * the canvas element it refers to. Step one asks the user to drag a block
     * onto the canvas, and the catalogue is a modal over it — so a panel left
     * open is a step the user cannot perform.
     */
    vi.mocked(learningCenterApi.startTutorialSession).mockResolvedValue(activeSession() as never);
    useAppStore.setState({ learningCenterOpen: true });

    await useAppStore.getState().startTutorial({
      source_kind: "core",
      source_id: "",
      tutorial_id: "welcome-to-scistudio",
      restart: false,
    } as never);

    expect(useAppStore.getState().learningCenterOpen).toBe(false);
  });
});

describe("clearing tutorial data lets go of a deleted project", () => {
  beforeEach(() => {
    resetAppStore();
    vi.mocked(learningCenterApi.getTutorialCatalogue).mockResolvedValue(EMPTY_CATALOGUE);
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("drops the open project when clearing deleted it", async () => {
    /*
     * FR-073 deletes the tutorial projects, and clearing is reachable from
     * inside a running tutorial — so the project the user is looking at can be
     * one of them. The backend stops treating it as active, every later call
     * answers 409, and a frontend still holding it renders a project whose
     * directory is gone.
     */
    const projectPath = "/Users/someone/SciStudio Tutorials/welcome-to-scistudio";
    vi.mocked(learningCenterApi.clearTutorialData).mockResolvedValue({
      deleted_directories: [projectPath, "/Users/someone/SciStudio Tutorials/.library"],
    } as never);
    useAppStore.setState({
      currentProject: { id: "project-37f0822e", path: projectPath } as never,
    });

    await useAppStore.getState().clearTutorialData();

    expect(useAppStore.getState().currentProject).toBeNull();
  });

  it("keeps a project clearing did not touch", async () => {
    vi.mocked(learningCenterApi.clearTutorialData).mockResolvedValue({
      deleted_directories: ["/Users/someone/SciStudio Tutorials/welcome-to-scistudio"],
    } as never);
    const mine = { id: "project-mine", path: "/Users/someone/work/my-analysis" };
    useAppStore.setState({ currentProject: mine as never });

    await useAppStore.getState().clearTutorialData();

    expect(useAppStore.getState().currentProject).toEqual(mine);
  });

  it("does not mistake a sibling whose path merely starts the same", async () => {
    vi.mocked(learningCenterApi.clearTutorialData).mockResolvedValue({
      deleted_directories: ["/Users/someone/SciStudio Tutorials/welcome"],
    } as never);
    const sibling = {
      id: "project-sibling",
      path: "/Users/someone/SciStudio Tutorials/welcome-to-scistudio",
    };
    useAppStore.setState({ currentProject: sibling as never });

    await useAppStore.getState().clearTutorialData();

    expect(useAppStore.getState().currentProject).toEqual(sibling);
  });
});
describe("finishing a tutorial lands in the Learning Center", () => {
  beforeEach(() => {
    resetAppStore();
    vi.mocked(learningCenterApi.getTutorialCatalogue).mockResolvedValue(EMPTY_CATALOGUE);
    vi.mocked(learningCenterApi.getTutorialUnlock).mockResolvedValue({
      work_import_offer_pending: false,
    });
    // FR-083's first-run landing opens the catalogue on its own for a user with
    // no recorded progress. Dismissed here so what these two assert is the
    // completion, and not that.
    useAppStore.setState({ learningCenterFirstRunDismissed: true });
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("closes the tutorial's project when the session completes", async () => {
    /*
     * A tutorial project looks like any other workspace once the card is gone,
     * and restarting the tutorial deletes it (FR-066). Leaving it open invites
     * the reader to keep working somewhere their work will not survive.
     *
     * The session is seen running before it completes: a finish the app run
     * never witnessed is history, not news (#2079), so the transition is what
     * these tests model.
     */
    const closeProject = vi.fn();
    const openProject = vi.fn();
    await renderHarness(openProject, closeProject);

    useAppStore.setState({ learningCenterSession: activeSession() });
    await waitFor(() => expect(openProject).toHaveBeenCalled());
    useAppStore.setState({
      learningCenterSession: activeSession({ status: "complete", step: null }),
    });

    await waitFor(() => expect(closeProject).toHaveBeenCalled());
  });

  it("opens the catalogue when the session completes", async () => {
    // The last step used to leave a "Tutorial complete." card in the corner and
    // a workspace with nothing to do next. The catalogue is where the next
    // tutorial is, so that is where finishing one goes.
    const openProject = vi.fn();
    await renderHarness(openProject);
    expect(useAppStore.getState().learningCenterOpen).toBe(false);

    useAppStore.setState({ learningCenterSession: activeSession() });
    await waitFor(() => expect(openProject).toHaveBeenCalled());
    useAppStore.setState({
      learningCenterSession: activeSession({ status: "complete", step: null }),
    });

    await waitFor(() => expect(useAppStore.getState().learningCenterOpen).toBe(true));
  });

  it("leaves it closed while the tutorial is still running", async () => {
    await renderHarness(vi.fn());

    useAppStore.setState({ learningCenterSession: activeSession() });

    await waitFor(() => expect(useAppStore.getState().learningCenterSession).not.toBeNull());
    expect(useAppStore.getState().learningCenterOpen).toBe(false);
  });
});

describe("a session adopted already-complete at start-up is history, not news (#2079)", () => {
  const STALE_CATALOGUE = {
    ...EMPTY_CATALOGUE,
    active: activeSession({ status: "complete", step: null }),
  };

  beforeEach(() => {
    resetAppStore();
    vi.mocked(learningCenterApi.getTutorialCatalogue).mockResolvedValue(STALE_CATALOGUE as never);
    // Both start-up reads see the kept record, as the backend answers both.
    vi.mocked(learningCenterApi.getActiveTutorialSession).mockResolvedValue(
      STALE_CATALOGUE.active as never,
    );
    vi.mocked(learningCenterApi.getTutorialUnlock).mockResolvedValue({
      work_import_offer_pending: false,
    });
    // FR-083's first-run landing is dismissed so what these assert is the
    // completion reaction, and not that.
    useAppStore.setState({ learningCenterFirstRunDismissed: true });
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("does not open the Learning Center on every restart", async () => {
    /*
     * The backend keeps an ended session as the active record with status
     * `complete`, so every launch adopted the last finished tutorial and the
     * completion reaction fired again: the catalogue opened, the open project
     * closed, and the unlock endpoint was asked — every single restart.
     */
    const closeProject = vi.fn();
    const openProject = vi.fn();
    await renderHarness(openProject, closeProject);

    await waitFor(() =>
      expect(useAppStore.getState().learningCenterSession?.status).toBe("complete"),
    );
    expect(useAppStore.getState().learningCenterOpen).toBe(false);
    expect(closeProject).not.toHaveBeenCalled();
    expect(learningCenterApi.getTutorialUnlock).not.toHaveBeenCalled();
  });

  it("does not resurrect the finished tutorial's project", async () => {
    // A stale session carries the project the lesson ran in; only a live
    // session may move the window to it.
    const openProject = vi.fn();
    await renderHarness(openProject);

    await waitFor(() =>
      expect(useAppStore.getState().learningCenterSession?.status).toBe("complete"),
    );
    expect(openProject).not.toHaveBeenCalled();
  });

  it("still lands a genuine re-run of the same tutorial in the catalogue", async () => {
    /*
     * The stale record must not suppress a real finish either: the user
     * restarts the same tutorial (FR-066) and completes it again in this app
     * run, and that completion is witnessed, so it lands like any other.
     */
    const openProject = vi.fn();
    await renderHarness(openProject);
    await waitFor(() =>
      expect(useAppStore.getState().learningCenterSession?.status).toBe("complete"),
    );
    expect(useAppStore.getState().learningCenterOpen).toBe(false);

    useAppStore.setState({ learningCenterSession: activeSession() });
    await waitFor(() => expect(openProject).toHaveBeenCalled());
    useAppStore.setState({
      learningCenterSession: activeSession({ status: "complete", step: null }),
    });

    await waitFor(() => expect(useAppStore.getState().learningCenterOpen).toBe(true));
  });
});
