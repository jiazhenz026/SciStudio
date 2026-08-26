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

import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type * as LearningCenterModule from "../../lib/api/learningCenter";
import { learningCenterApi } from "../../lib/api/learningCenter";
import { useAppStore } from "../../store";
import { resetAppStore } from "../../testUtils";
import { ENTRY_LABEL } from "../BringInMyWorkDialog.parts/copy";
import {
  PROVIDER_INTRO_CHECKING,
  PROVIDER_INTRO_CONTINUE_LABEL,
  PROVIDER_INTRO_TITLE,
} from "../LearningCenter.parts/ProviderIntro";
import {
  OFFER_ACCEPT_LABEL,
  OFFER_SKIP_LABEL,
  OFFER_TITLE,
  WorkImportOffer,
} from "../LearningCenter.parts/WorkImportOffer";
import { Toolbar } from "../Toolbar";

/**
 * #2083 — the intro's availability probe is a live backend call; the tests
 * feed it a fixed report (or leave it hanging where the static rendering is
 * the point — the card must be complete before the probe answers).
 *
 * #2083 — the page moved from `GET /api/ai/availability` to `GET /api/ai/status`.
 * The graded report makes a live call through each provider's CLI, fifteen
 * seconds of timeout apiece, to tell "signed in but failing" from "ready";
 * this page only asks whether one is installed, and status answers that from
 * a two-second probe. So the fixture is `fetch`, and by default it hangs —
 * which is the state several cases below are about.
 */
const hangingProbe = () => new Promise<never>(() => {});

function stubProviderStatus(providers: unknown[] | null): void {
  vi.stubGlobal(
    "fetch",
    providers === null
      ? vi.fn(hangingProbe)
      : vi.fn(async () => ({ ok: true, json: async () => ({ providers }) })),
  );
}

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

/** #2083 — the offer now opens on the provider introduction; step past it. */
function continueThroughIntro(): void {
  fireEvent.click(screen.getByRole("button", { name: PROVIDER_INTRO_CONTINUE_LABEL }));
}

describe("the offer appears exactly when the backend says it is owed", () => {
  it("is presented when the unlock reports it pending", async () => {
    vi.mocked(learningCenterApi.getTutorialUnlock).mockResolvedValue({
      work_import_offer_pending: true,
    });

    await useAppStore.getState().checkWorkImportOffer();
    render(<WorkImportOffer />);

    expect(screen.getByTestId("work-import-offer")).toBeInTheDocument();
    // #2083 — the provider introduction is the first page; the import
    // question is behind its Continue.
    expect(screen.getByText(PROVIDER_INTRO_TITLE)).toBeInTheDocument();
    expect(screen.queryByText(OFFER_TITLE)).not.toBeInTheDocument();
    continueThroughIntro();
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

    continueThroughIntro();
    fireEvent.click(screen.getByRole("button", { name: OFFER_SKIP_LABEL }));

    await waitFor(() => expect(learningCenterApi.dismissTutorialUnlock).toHaveBeenCalledTimes(1));
  });

  it("records the dismissal when taken up, so it is not volunteered again", async () => {
    render(<WorkImportOffer />);

    continueThroughIntro();
    fireEvent.click(screen.getByRole("button", { name: OFFER_ACCEPT_LABEL }));

    await waitFor(() => expect(learningCenterApi.dismissTutorialUnlock).toHaveBeenCalledTimes(1));
  });

  it("asks for a project to import into, then opens the existing dialog", async () => {
    /*
     * #2083 — the importer imports into the *open* project, and this offer
     * arrives with none: it waited for the tutorial's project to close so the
     * reader's real codebase would not be filed inside a throwaway. So "Yes"
     * asks for a project first, named and placed by them, and the importer
     * follows once one exists.
     *
     * The importer is still the product's own dialog, which is what this test
     * was originally guarding: no second import surface exists.
     */
    render(<WorkImportOffer />);

    continueThroughIntro();
    fireEvent.click(screen.getByRole("button", { name: OFFER_ACCEPT_LABEL }));

    expect(useAppStore.getState().projectDialogOpen).toBe(true);
    expect(screen.queryByTestId("work-import-dialog")).not.toBeInTheDocument();

    act(() => {
      useAppStore.setState({
        currentProject: { id: "mine", name: "My Work", path: "/tmp/mine" } as never,
      });
    });

    expect(await screen.findByTestId("work-import-dialog")).toBeInTheDocument();
  });

  it("goes straight to the importer if a project got opened while the offer was up", async () => {
    /*
     * The offer only ever appears with no project open, but it does not vanish
     * if one is opened underneath it — a reader can reach the card, open
     * something from the toolbar, and come back. There is somewhere for the
     * work to land now, so asking for another project would be a step that
     * does nothing.
     */
    render(<WorkImportOffer />);
    continueThroughIntro();

    act(() => {
      useAppStore.setState({
        currentProject: { id: "p1", name: "Existing", path: "/tmp/p1" } as never,
      });
    });
    fireEvent.click(screen.getByRole("button", { name: OFFER_ACCEPT_LABEL }));

    expect(await screen.findByTestId("work-import-dialog")).toBeInTheDocument();
    expect(useAppStore.getState().projectDialogOpen).toBe(false);
  });

  it("keeps no local record of having been shown — the backend owns that", async () => {
    render(<WorkImportOffer />);
    continueThroughIntro();
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

    continueThroughIntro();
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

    // This is the intro page's close: bailing out before the question is the
    // same once-only skip, and it still says where the feature lives.
    fireEvent.click(screen.getByRole("button", { name: "Close" }));

    expect(await screen.findByTestId("work-import-offer-skipped")).toHaveTextContent(ENTRY_LABEL);
    await waitFor(() => expect(learningCenterApi.dismissTutorialUnlock).toHaveBeenCalledTimes(1));
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
      replays: [],
    };
  }

  it("asks the unlock endpoint when the session reports complete", async () => {
    vi.mocked(learningCenterApi.getTutorialCatalogue).mockResolvedValue(emptyCatalogue);
    vi.mocked(learningCenterApi.getTutorialUnlock).mockResolvedValue({
      work_import_offer_pending: true,
    });
    const { useLearningCenter } = await import("../../App.parts/useLearningCenter");

    const openProject = vi.fn();

    function Harness() {
      useLearningCenter({
        closeProject: vi.fn(),
        wsConnected: true,
        setLeftTab: vi.fn(),
        openProject,
      });
      return <WorkImportOffer />;
    }

    render(<Harness />);
    // Let the mount-time session refetch settle first: its answer (no active
    // session here) must land before the test drives the store, or it would
    // clobber the session the test is about to adopt.
    await act(async () => {});
    // A completion the app run never witnessed is history, not news (#2079):
    // the session is seen running before it completes, as in a real finish.
    // The wait is on the project-opening effect rather than on store state
    // alone, so the hook's effects have actually flushed for the active
    // session before the completion lands — store writes are synchronous,
    // effects are not.
    useAppStore.setState({
      learningCenterSession: { ...completedSession("welcome"), status: "active" },
    });
    await waitFor(() => expect(openProject).toHaveBeenCalledWith("p1"));
    useAppStore.setState({ learningCenterSession: completedSession("welcome") });

    expect(await screen.findByTestId("work-import-offer")).toBeInTheDocument();
    /*
     * Twice, not once: #2083 added a start-up ask, because an offer owed to a
     * reader who finished and then reloaded was never asked for again. The
     * count is not the contract — the backend owns "once" and answers false
     * after a dismissal — so what is pinned is that finishing still asks.
     */
    expect(learningCenterApi.getTutorialUnlock).toHaveBeenCalled();
  });

  it("asks at start-up for an offer owed to a finish this app run never saw", async () => {
    /*
     * #2083 — the offer used to fire only on the transition into complete,
     * watched by the running app. Everything else lost it for good: a reload,
     * a restart, "Keep exploring", or following a link out of the tutorial.
     * `work_import_offer_pending` stays true until the offer is *shown*, so
     * the only thing missing was somebody asking.
     */
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

    // A tutorial finished before this app run started: the session is already
    // complete when the page first looks at it.
    useAppStore.setState({ learningCenterSession: completedSession("welcome") });
    render(<Harness />);

    expect(await screen.findByTestId("work-import-offer")).toBeInTheDocument();
  });

  it("waits for a closed project, so imported work does not land in the tutorial's", async () => {
    /*
     * #2083 — "Bring in my work" imports into whatever project is open. Asked
     * while the tutorial's own project is still open — which is exactly where
     * the reader is when they press "Keep exploring" — it would file their
     * real codebase inside a throwaway. The offer stays owed until the backend
     * is told it was shown, so waiting costs nothing.
     */
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

    useAppStore.setState({
      learningCenterSession: completedSession("welcome"),
      currentProject: { id: "p1", name: "What AI Can Do", path: "/tmp/p1" } as never,
    });
    render(<Harness />);

    await waitFor(() => expect(learningCenterApi.getTutorialUnlock).toHaveBeenCalled());
    expect(screen.queryByTestId("work-import-offer")).not.toBeInTheDocument();

    // Close the project and the question is finally a fair one to ask.
    act(() => {
      useAppStore.setState({ currentProject: null });
    });
    expect(await screen.findByTestId("work-import-offer")).toBeInTheDocument();
  });

  it("start-up asking does not close the reader's project", async () => {
    /*
     * The other half of #2079, and the reason only the *ask* moved to
     * start-up. Finishing a tutorial opens the Learning Center and closes the
     * project; doing that on every launch, off a session that was already
     * complete before the page loaded, is the bug the "seen running" guard
     * fixed. Asking the backend a question is not that.
     */
    vi.mocked(learningCenterApi.getTutorialCatalogue).mockResolvedValue(emptyCatalogue);
    vi.mocked(learningCenterApi.getTutorialUnlock).mockResolvedValue({
      work_import_offer_pending: true,
    });
    const { useLearningCenter } = await import("../../App.parts/useLearningCenter");

    const closeProject = vi.fn();

    function Harness() {
      useLearningCenter({
        closeProject,
        wsConnected: true,
        setLeftTab: vi.fn(),
        openProject: vi.fn(),
      });
      return <WorkImportOffer />;
    }

    useAppStore.setState({ learningCenterSession: completedSession("welcome") });
    render(<Harness />);

    expect(await screen.findByTestId("work-import-offer")).toBeInTheDocument();
    expect(closeProject).not.toHaveBeenCalled();
    /*
     * Deliberately no assertion about `learningCenterOpen`: the first-run
     * landing opens it whenever the catalogue shows no recorded progress,
     * which this harness's empty catalogue does. That is a different feature
     * and it would make this test pass or fail for the wrong reason.
     */
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

describe("the provider introduction (#2083)", () => {
  beforeEach(() => {
    useAppStore.setState({ learningCenterWorkImportOffer: true });
  });

  it("renders complete before the probe answers, and hides the question behind it", () => {
    render(<WorkImportOffer />);

    // The probe (mocked to hang) must not block the card: the intro's prose
    // and its checking note are up immediately (FR-035's rule, inherited).
    expect(screen.getByText(PROVIDER_INTRO_TITLE)).toBeInTheDocument();
    expect(screen.getByTestId("provider-intro-checking")).toHaveTextContent(
      PROVIDER_INTRO_CHECKING,
    );
    expect(screen.queryByText(OFFER_TITLE)).not.toBeInTheDocument();
  });

  it("lists every provider the backend reports — greyed when not set up, never hidden", async () => {
    // The rows come whole from the availability report (ADR-034 FR-020a/b:
    // no hand-maintained key or label list in the frontend), so the fixture
    // is the report, and a sixth provider would appear with no code change.
    stubProviderStatus([
      { name: "provider-a", label: "Provider A", available: true, logged_in: true },
      { name: "provider-b", label: "Provider B", available: false, logged_in: false },
    ]);

    render(<WorkImportOffer />);

    await waitFor(() =>
      expect(screen.getByTestId("provider-intro-provider-a")).toHaveTextContent("Provider A"),
    );
    expect(screen.getByTestId("provider-intro-provider-a")).toHaveTextContent("ready");

    const other = screen.getByTestId("provider-intro-provider-b");
    // Greyed, never hidden — the same rule as the work-import dropdown.
    expect(other).toBeInTheDocument();
    expect(other.className).toContain("opacity-60");
    expect(other).toHaveTextContent("not installed");
    /*
     * No per-provider install command any more: that was `next_step` from the
     * graded report, and the page no longer waits fifteen seconds a provider
     * to get it. The installation guide link beside the list is what carries
     * the "how" now.
     */
    expect(screen.getByTestId("provider-intro-install-guide")).toBeInTheDocument();
  });

  it("continue leads to the import question; the offer is not yet answered", () => {
    render(<WorkImportOffer />);

    continueThroughIntro();

    expect(screen.getByText(OFFER_TITLE)).toBeInTheDocument();
    expect(learningCenterApi.dismissTutorialUnlock).not.toHaveBeenCalled();
  });
});
