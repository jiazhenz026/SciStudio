/**
 * ADR-053 FR-079 (#2057) — the offer that progress drives.
 *
 * FR-079 is the only product behaviour the progress subsystem exists to
 * produce; everything else about progress is display. These tests cover that it
 * fires on the backend's say-so, that it is answered once, that skipping tells
 * the user where the feature went, and that nothing about it gates the
 * capability itself.
 *
 * Nothing here hardcodes a tutorial id. Which tutorial is the milestone is
 * configuration (FR-079) and is currently unset, so these test the endpoint's
 * contract rather than the shipped default.
 */

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type * as LearningCenterModule from "../../lib/api/learningCenter";
import { learningCenterApi } from "../../lib/api/learningCenter";
import { useAppStore } from "../../store";
import { resetAppStore } from "../../testUtils";
import { ENTRY_LABEL } from "../BringInMyWorkDialog.parts/copy";
import {
  OFFER_ACCEPT_LABEL,
  OFFER_SKIP_LABEL,
  OFFER_TITLE,
  WorkImportOffer,
} from "../LearningCenter.parts/WorkImportOffer";
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

beforeEach(() => {
  vi.clearAllMocks();
  resetAppStore();
});

afterEach(cleanup);

describe("the offer appears exactly when the backend says it is owed", () => {
  it("is presented when the unlock reports it pending", async () => {
    vi.mocked(learningCenterApi.getTutorialUnlock).mockResolvedValue({
      work_import_offer_pending: true,
    });

    await useAppStore.getState().checkWorkImportOffer();
    render(<WorkImportOffer />);

    expect(screen.getByTestId("work-import-offer")).toBeInTheDocument();
    expect(screen.getByText(OFFER_TITLE)).toBeInTheDocument();
  });

  it("is not presented when the unlock reports nothing pending", async () => {
    vi.mocked(learningCenterApi.getTutorialUnlock).mockResolvedValue({
      work_import_offer_pending: false,
    });

    await useAppStore.getState().checkWorkImportOffer();
    render(<WorkImportOffer />);

    expect(screen.queryByTestId("work-import-offer")).not.toBeInTheDocument();
  });

  it("stays quiet when the unlock cannot be read", async () => {
    vi.mocked(learningCenterApi.getTutorialUnlock).mockRejectedValue(new Error("offline"));

    await useAppStore.getState().checkWorkImportOffer();
    render(<WorkImportOffer />);

    // An offer the user never asked for is not worth an error banner.
    expect(screen.queryByTestId("work-import-offer")).not.toBeInTheDocument();
    expect(useAppStore.getState().learningCenterError).toBeNull();
  });
});

describe("the offer is answered once (FR-079)", () => {
  beforeEach(() => {
    useAppStore.setState({ learningCenterWorkImportOffer: true });
  });

  it("records the dismissal on the backend when skipped", async () => {
    render(<WorkImportOffer />);

    fireEvent.click(screen.getByRole("button", { name: OFFER_SKIP_LABEL }));

    await waitFor(() => expect(learningCenterApi.dismissTutorialUnlock).toHaveBeenCalledTimes(1));
  });

  it("records the dismissal when taken up, so it is not volunteered again", async () => {
    render(<WorkImportOffer />);

    fireEvent.click(screen.getByRole("button", { name: OFFER_ACCEPT_LABEL }));

    await waitFor(() => expect(learningCenterApi.dismissTutorialUnlock).toHaveBeenCalledTimes(1));
  });

  it("opens the existing Bring in my work dialog rather than a new surface", async () => {
    render(<WorkImportOffer />);

    fireEvent.click(screen.getByRole("button", { name: OFFER_ACCEPT_LABEL }));

    expect(await screen.findByTestId("work-import-dialog")).toBeInTheDocument();
  });

  it("keeps no local record of having been shown — the backend owns that", async () => {
    render(<WorkImportOffer />);
    fireEvent.click(screen.getByRole("button", { name: OFFER_SKIP_LABEL }));
    await waitFor(() => expect(learningCenterApi.dismissTutorialUnlock).toHaveBeenCalled());

    // Asking again is answered by the endpoint, not by a store flag that would
    // be a second copy of the same fact.
    vi.mocked(learningCenterApi.getTutorialUnlock).mockResolvedValue({
      work_import_offer_pending: false,
    });
    await useAppStore.getState().checkWorkImportOffer();

    expect(useAppStore.getState().learningCenterWorkImportOffer).toBe(false);
  });
});

describe("skipping says where the feature went (FR-081, User Story 5)", () => {
  it("names the permanent toolbar entry", async () => {
    useAppStore.setState({ learningCenterWorkImportOffer: true });
    render(<WorkImportOffer />);

    fireEvent.click(screen.getByRole("button", { name: OFFER_SKIP_LABEL }));

    const message = await screen.findByTestId("work-import-offer-skipped");
    // The exact label the toolbar uses, imported rather than retyped, so the
    // guidance cannot start pointing at words that are not on screen.
    expect(message).toHaveTextContent(ENTRY_LABEL);
    expect(message).toHaveTextContent(/permanently/i);
  });

  it("says so on the close button too, not only the skip button", async () => {
    useAppStore.setState({ learningCenterWorkImportOffer: true });
    render(<WorkImportOffer />);

    fireEvent.click(screen.getByRole("button", { name: "Close" }));

    expect(await screen.findByTestId("work-import-offer-skipped")).toHaveTextContent(ENTRY_LABEL);
  });
});

describe("the offer is triggered by a tutorial completing", () => {
  const emptyCatalogue = { groups: [], active: null, diagnostics: [] };

  function completedSession(tutorialId: string) {
    return {
      source_kind: "core" as const,
      source_id: "",
      tutorial_id: tutorialId,
      title: "A tutorial",
      project_id: "p1",
      project_path: "/tmp/p1",
      step: null,
      satisfied_step_ids: [],
      status: "complete" as const,
      error: null,
      replay: null,
    };
  }

  it("asks the unlock endpoint when the session reports complete", async () => {
    vi.mocked(learningCenterApi.getTutorialCatalogue).mockResolvedValue(emptyCatalogue);
    vi.mocked(learningCenterApi.getTutorialUnlock).mockResolvedValue({
      work_import_offer_pending: true,
    });
    const { useLearningCenter } = await import("../../App.parts/useLearningCenter");

    function Harness() {
      useLearningCenter({
        closeProject: vi.fn(),
        wsConnected: true,
        setLeftTab: vi.fn(),
        openProject: vi.fn(),
      });
      return <WorkImportOffer />;
    }

    useAppStore.setState({ learningCenterSession: completedSession("welcome") });
    render(<Harness />);

    expect(await screen.findByTestId("work-import-offer")).toBeInTheDocument();
    expect(learningCenterApi.getTutorialUnlock).toHaveBeenCalledTimes(1);
  });

  it("does not ask while a tutorial is still running", async () => {
    vi.mocked(learningCenterApi.getTutorialCatalogue).mockResolvedValue(emptyCatalogue);
    const { useLearningCenter } = await import("../../App.parts/useLearningCenter");

    function Harness() {
      useLearningCenter({
        closeProject: vi.fn(),
        wsConnected: true,
        setLeftTab: vi.fn(),
        openProject: vi.fn(),
      });
      return <WorkImportOffer />;
    }

    useAppStore.setState({
      learningCenterSession: { ...completedSession("welcome"), status: "active" },
    });
    render(<Harness />);

    await waitFor(() => expect(learningCenterApi.getTutorialCatalogue).toHaveBeenCalled());
    expect(learningCenterApi.getTutorialUnlock).not.toHaveBeenCalled();
  });
});

describe("nothing is gated on progress (FR-081, SC-011)", () => {
  it("offers the toolbar entry with no tutorials completed at all", () => {
    // The store is freshly reset: no catalogue, no progress, no session.
    render(<Toolbar {...toolbarProps()} />);

    // FR-081 — the unlock decides when the product VOLUNTEERS the capability,
    // never whether it can be reached. A later refactor that "tidies up" by
    // gating this entry on progress is exactly what this pins.
    expect(screen.getByRole("button", { name: ENTRY_LABEL })).toBeInTheDocument();
  });

  it("offers it with a catalogue showing zero complete", () => {
    useAppStore.setState({
      learningCenterCatalogue: {
        groups: [
          {
            source_kind: "core",
            source_id: "",
            label: "SciStudio",
            completed: 0,
            total: 4,
            tutorials: [],
          },
        ],
        active: null,
        diagnostics: [],
      },
    });

    render(<Toolbar {...toolbarProps()} />);

    expect(screen.getByRole("button", { name: ENTRY_LABEL })).toBeInTheDocument();
  });
});
