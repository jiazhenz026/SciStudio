/**
 * ADR-053 Learning Center — the reading window (#2084).
 *
 * What must hold: the grid draws one card per step with the tutorial's top
 * sentence above it; opening a card fetches its pages — the fetch IS the
 * progress report, so each page is followed by an evaluate; the last page
 * returns to the grid; and Continue moves the tutorial on exactly when the
 * backend says the current card is done (FR-054a). Step views are mocked —
 * the `pages` field ships with the #2061 vocabulary batch.
 */

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type {
  TutorialCatalogueEntry,
  TutorialCatalogueResponse,
  TutorialSessionResponse,
  TutorialStepOutline,
  TutorialStepView,
} from "../../../lib/api/learningCenter";
import { fetchTutorialPage } from "../../../lib/api/learningCenter";
import { useAppStore } from "../../../store";
import { resetAppStore } from "../../../testUtils";
import { LearningCenter } from "../../LearningCenter";
import { ReadingSurface } from "../ReadingSurface";

vi.mock("../../../lib/api/learningCenter", async (importOriginal) => {
  const original = (await importOriginal()) as Record<string, unknown>;
  return { ...original, fetchTutorialPage: vi.fn() };
});

const fetchPage = vi.mocked(fetchTutorialPage);

function entry(over: Partial<TutorialCatalogueEntry> = {}): TutorialCatalogueEntry {
  return {
    source_kind: "core",
    source_id: "",
    id: "scistudio-at-a-glance",
    title: "SciStudio at a Glance",
    summary: "Your analysis is a workflow of blocks passing typed data.",
    cover_url: null,
    order: 5,
    state: "in_progress",
    unavailable_reason: null,
    project_directory: null,
    reading: true,
    ...over,
  };
}

function stepView(over: Partial<TutorialStepView> & { pages?: string[] } = {}): TutorialStepView {
  return {
    id: "workflow-card",
    index: 0,
    total: 8,
    title: "Workflow",
    say: "The graph you build.",
    highlight: null,
    route_to: null,
    prefill: [],
    awaiting_continue: false,
    satisfied: false,
    pages: ["workflow-what-it-is", "workflow-running"],
    ...over,
  } as TutorialStepView;
}

const CARD_TITLES = [
  "Workflow",
  "Block",
  "Data type",
  "Previewer",
  "Plot card",
  "History",
  "My library",
  "Others",
];

/** The session's read-only step outline, as the backend now always sends it. */
function outline(): TutorialStepOutline[] {
  return CARD_TITLES.map((title, index) => ({
    index,
    id: `${title.toLowerCase().replace(/ /g, "-")}-card`,
    title,
    say: `${title} in one line.`,
    pages:
      index === 0
        ? ["workflow-what-it-is", "workflow-running"]
        : [`${title.toLowerCase().replace(/ /g, "-")}-page`],
  }));
}

function session(over: Partial<TutorialSessionResponse> = {}): TutorialSessionResponse {
  return {
    source_kind: "core",
    source_id: "",
    tutorial_id: "scistudio-at-a-glance",
    title: "SciStudio at a Glance",
    project_id: null,
    project_path: null,
    step: stepView(),
    satisfied_step_ids: [],
    status: "active",
    error: null,
    replay: null,
    steps: outline(),
    ...over,
  };
}

const continueStep = vi.fn(async () => {});
const evaluateStep = vi.fn(async () => {});

beforeEach(() => {
  resetAppStore();
  vi.clearAllMocks();
  fetchPage.mockImplementation(async (_key, page) => `# ${page}\n\nBody of ${page}.`);
  useAppStore.setState({
    continueActiveTutorialStep: continueStep,
    evaluateActiveTutorialStep: evaluateStep,
    leaveActiveTutorial: vi.fn(async () => {}),
    refreshLearningCenter: vi.fn(async () => {}),
  });
});

afterEach(cleanup);

describe("the reading grid", () => {
  it("shows the top sentence and one card per step, in step order", () => {
    render(<ReadingSurface entry={entry()} onClose={() => {}} session={session()} />);

    expect(screen.getByTestId("reading-top-sentence")).toHaveTextContent(
      "Your analysis is a workflow of blocks passing typed data.",
    );
    expect(screen.getByTestId("reading-card-0")).toHaveTextContent("Workflow");
    expect(screen.getByTestId("reading-card-0")).toHaveAttribute("data-reading-state", "current");
    // The outline names every card up front; cards ahead stay unopenable.
    expect(screen.getByTestId("reading-card-7")).toHaveTextContent("Others");
    expect(screen.getByTestId("reading-card-7")).toHaveTextContent("Others in one line.");
    expect(screen.getByTestId("reading-card-7")).toBeDisabled();
    expect(screen.getAllByTestId(/^reading-card-/)).toHaveLength(8);
  });

  it("falls back to placeholders when a session carries no outline", () => {
    render(
      <ReadingSurface entry={entry()} onClose={() => {}} session={session({ steps: undefined })} />,
    );

    expect(screen.getByTestId("reading-card-7")).toHaveTextContent("Card 8");
    expect(screen.getByTestId("reading-card-7")).toBeDisabled();
  });

  it("keeps a passed card's name and lets it be reopened", async () => {
    const user = userEvent.setup();
    const { rerender } = render(
      <ReadingSurface entry={entry()} onClose={() => {}} session={session()} />,
    );
    rerender(
      <ReadingSurface
        entry={entry()}
        onClose={() => {}}
        session={session({
          step: stepView({
            id: "block-card",
            index: 1,
            title: "Block",
            pages: ["block-what-it-is"],
          }),
        })}
      />,
    );

    const passed = screen.getByTestId("reading-card-0");
    expect(passed).toHaveAttribute("data-reading-state", "read");
    expect(passed).toHaveTextContent("Workflow");

    await user.click(passed);
    expect(await screen.findByTestId("reading-page")).toHaveTextContent("Page 1 of 2");
  });
});

describe("the paged reader", () => {
  it("fetches each page — the fetch is the progress report — and evaluates after it", async () => {
    const user = userEvent.setup();
    render(<ReadingSurface entry={entry()} onClose={() => {}} session={session()} />);

    await user.click(screen.getByTestId("reading-card-0"));

    await waitFor(() =>
      expect(fetchPage).toHaveBeenCalledWith(
        { source_kind: "core", source_id: "", id: "scistudio-at-a-glance" },
        "workflow-what-it-is",
      ),
    );
    expect(await screen.findByText("Body of workflow-what-it-is.")).toBeInTheDocument();
    await waitFor(() => expect(evaluateStep).toHaveBeenCalledTimes(1));

    await user.click(screen.getByTestId("reading-page-next"));
    await waitFor(() =>
      expect(fetchPage).toHaveBeenCalledWith(expect.anything(), "workflow-running"),
    );
    await waitFor(() => expect(evaluateStep).toHaveBeenCalledTimes(2));
  });

  it("returns to the grid from the last page", async () => {
    const user = userEvent.setup();
    render(<ReadingSurface entry={entry()} onClose={() => {}} session={session()} />);

    await user.click(screen.getByTestId("reading-card-0"));
    await screen.findByText("Body of workflow-what-it-is.");
    await user.click(screen.getByTestId("reading-page-next"));
    await screen.findByText("Body of workflow-running.");

    // The last page offers no Next — only the way back to the cards.
    expect(screen.queryByTestId("reading-page-next")).toBeNull();
    await user.click(screen.getByTestId("reading-page-done"));

    expect(screen.queryByTestId("reading-page")).toBeNull();
    expect(screen.getByTestId("reading-card-0")).toBeInTheDocument();
  });

  it("shows the failure when a page cannot be fetched", async () => {
    fetchPage.mockRejectedValue(new Error("HTTP 404"));
    const user = userEvent.setup();
    render(<ReadingSurface entry={entry()} onClose={() => {}} session={session()} />);

    await user.click(screen.getByTestId("reading-card-0"));

    expect(await screen.findByTestId("reading-page-error")).toHaveTextContent("HTTP 404");
    expect(evaluateStep).not.toHaveBeenCalled();
  });
});

describe("advancing", () => {
  it("keeps Continue inert until the backend reports the card done", () => {
    render(<ReadingSurface entry={entry()} onClose={() => {}} session={session()} />);
    expect(screen.getByTestId("reading-continue")).toBeDisabled();
  });

  it("moves on through the normal continue flow once satisfied", async () => {
    const user = userEvent.setup();
    render(
      <ReadingSurface
        entry={entry()}
        onClose={() => {}}
        session={session({ step: stepView({ satisfied: true }) })}
      />,
    );

    const button = screen.getByTestId("reading-continue");
    expect(button).toBeEnabled();
    await user.click(button);
    expect(continueStep).toHaveBeenCalledTimes(1);
  });
});

describe("the Learning Center wiring", () => {
  function catalogueWith(readingEntry: TutorialCatalogueEntry): TutorialCatalogueResponse {
    return {
      groups: [
        {
          source_kind: "core",
          source_id: "",
          label: "Core",
          completed: 0,
          total: 1,
          tutorials: [readingEntry],
        },
      ],
      active: null,
      diagnostics: [],
    };
  }

  it("renders the reading window in place of the catalogue while a reading session runs", () => {
    useAppStore.setState({
      learningCenterOpen: true,
      learningCenterCatalogue: catalogueWith(entry()),
      learningCenterSession: session(),
    });

    render(<LearningCenter />);

    expect(screen.getByTestId("reading-surface")).toBeInTheDocument();
    expect(screen.queryByTestId("learning-center")).toBeNull();
  });

  it("keeps the catalogue for a hands-on session", () => {
    useAppStore.setState({
      learningCenterOpen: true,
      learningCenterCatalogue: catalogueWith(entry({ reading: false })),
      learningCenterSession: session(),
    });

    render(<LearningCenter />);

    expect(screen.queryByTestId("reading-surface")).toBeNull();
    expect(screen.getByTestId("learning-center")).toBeInTheDocument();
  });

  it("reopens the panel once when a reading session starts with it closed", async () => {
    useAppStore.setState({
      learningCenterOpen: false,
      learningCenterCatalogue: catalogueWith(entry()),
      learningCenterSession: session(),
    });

    render(<LearningCenter />);

    await waitFor(() => expect(useAppStore.getState().learningCenterOpen).toBe(true));
    expect(await screen.findByTestId("reading-surface")).toBeInTheDocument();
  });

  it("stays closed after the reader closes the window themselves", async () => {
    const user = userEvent.setup();
    useAppStore.setState({
      learningCenterOpen: false,
      learningCenterCatalogue: catalogueWith(entry()),
      learningCenterSession: session(),
    });

    render(<LearningCenter />);
    await user.click(await screen.findByTestId("reading-close"));

    expect(useAppStore.getState().learningCenterOpen).toBe(false);
    expect(screen.queryByTestId("reading-surface")).toBeNull();
  });
});
