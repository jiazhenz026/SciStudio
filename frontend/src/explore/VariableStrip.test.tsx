/**
 * ADR-054 spec 4 (T-008) — the variable strip (FR-018 to FR-020).
 *
 * Three properties, and the third is the one that carries the design: a click
 * is a **producing** request for the variable's type, answered by the backend's
 * panel catalogue for that type. A strip that mounted whatever panel happens to
 * be first would put a read-only panel over a variable a person is trying to
 * edit from, and the emission path behind it would never be reachable.
 */

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useAppStore } from "../store";
import type { ExploreTab as ExploreTabState } from "../store/types";
import { resetAppStore } from "../testUtils";
import type {
  ExploreBindingsResponse,
  ExplorePackagingCheckResponse,
  ExploreSessionResponse,
} from "../types/api";

import { forgetSlotDescriptors } from "./PanelSlots";
import { VariableStrip } from "./VariableStrip";

const listPanels = vi.fn();
vi.mock("../lib/api/data", () => ({
  dataApi: { listPanels: (...args: unknown[]) => listPanels(...args) },
}));

const getExploreBindings = vi.fn();
vi.mock("../lib/api/explore", () => ({
  exploreApi: { getExploreBindings: (...args: unknown[]) => getExploreBindings(...args) },
}));

const PATH = "explore/analysis.ipynb";
const SESSION_ID = "sess-strip";

function tab(overrides: Partial<ExploreTabState> = {}): ExploreTabState {
  return {
    kind: "explore",
    id: `explore:${PATH}`,
    notebookPath: PATH,
    sessionId: SESSION_ID,
    displayName: "analysis.ipynb",
    mode: "session",
    boundRunId: null,
    pauseNodeId: null,
    notebookVisible: true,
    ...overrides,
  };
}

function sessionResponse(): ExploreSessionResponse {
  return {
    session_id: SESSION_ID,
    notebook_path: PATH,
    has_kernel: true,
    needs_restart: false,
    current_cell: "c1",
    notebook_commit: null,
    bound_run: null,
    cells: [{ cell_id: "c1", cell_type: "code", source: "df = load()", enabled: true, marks: [] }],
  };
}

/** The bindings response is the only authority on which names exist (FR-018). */
function bindings(): ExploreBindingsResponse {
  return {
    session_id: SESSION_ID,
    has_kernel: true,
    bindings: [
      { name: "df", exists_in_kernel: true, type_name: "DataFrame" },
      // The analysis reports it because a cell binds it; the kernel does not
      // hold it, so it is greyed and not openable.
      { name: "model", exists_in_kernel: false, type_name: null },
      { name: "summary", exists_in_kernel: true, type_name: "DataFrame" },
    ],
  };
}

/** A displaying panel listed above a producing one for the same type. */
function catalogue() {
  return {
    panels: [
      {
        panel_id: "core.dataframe.basic",
        capability: "displaying",
        target_type: "DataFrame",
        descriptor: descriptorFor("core.dataframe.basic", "displaying"),
      },
      {
        panel_id: "core.dataframe.editor",
        capability: "producing",
        target_type: "DataFrame",
        descriptor: descriptorFor("core.dataframe.editor", "producing"),
      },
    ],
    diagnostics: [],
  };
}

function descriptorFor(panelId: string, capability: string) {
  return {
    panel_id: panelId,
    display_name: panelId,
    api_version: "1",
    accepted_api_version: "1",
    capability,
    document_url: `/api/panels/assets/${panelId}/index.html`,
    asset_base_url: `/api/panels/assets/${panelId}/`,
    read_limits: { max_rows: 100, max_bytes: 1000 },
  };
}

beforeEach(() => {
  resetAppStore();
  useAppStore.setState({ sessions: {}, sessionPathById: {}, pendingExploreEvents: {}, tabs: [] });
  forgetSlotDescriptors();
  listPanels.mockReset();
  listPanels.mockResolvedValue(catalogue());
  getExploreBindings.mockReset();
  getExploreBindings.mockResolvedValue(bindings());
  useAppStore.getState().applyExploreSession(sessionResponse());
  useAppStore.getState().applyExploreBindings(SESSION_ID, bindings());
});

afterEach(cleanup);

function currentSession() {
  return useAppStore.getState().sessions[PATH];
}

describe("where the strip's names come from (FR-018)", () => {
  it("asks the runtime for the bindings, and again once a run has ended", async () => {
    // Greyed until the bindings response says otherwise: `model` is reported
    // by the analysis and absent from the kernel, and the strip copies that.
    const { rerender } = render(<VariableStrip tab={tab()} session={currentSession()} />);
    await waitFor(() => expect(getExploreBindings).toHaveBeenCalledWith(SESSION_ID));
    expect(getExploreBindings).toHaveBeenCalledTimes(1);

    // A run ended: the kernel now holds `model`, and the strip re-reads rather
    // than deciding for itself that it must be live now.
    getExploreBindings.mockResolvedValue({
      session_id: SESSION_ID,
      has_kernel: true,
      bindings: [{ name: "model", exists_in_kernel: true, type_name: "Model" }],
    });
    useAppStore.getState().applyExploreSessionEvent({
      type: "explore.changed_names",
      session_id: SESSION_ID,
      data: { cell_id: "c1", changed: ["model"], unobservable: [] },
      timestamp: "2026-09-05T12:00:01Z",
    });
    rerender(<VariableStrip tab={tab()} session={currentSession()} />);

    await waitFor(() => expect(getExploreBindings).toHaveBeenCalledTimes(2));
    await waitFor(() =>
      expect(currentSession().bindings.find((entry) => entry.name === "model")?.live).toBe(true),
    );
  });
});

describe("what the strip lists (FR-018)", () => {
  it("lists every binding with its type name", () => {
    render(<VariableStrip tab={tab()} session={currentSession()} />);
    expect(screen.getByTestId("explore-variable-df").getAttribute("data-type-name")).toBe(
      "DataFrame",
    );
    expect(screen.getByTestId("explore-variable-model")).toBeTruthy();
    expect(screen.getByTestId("explore-variable-summary")).toBeTruthy();
  });

  it("greys a name the kernel does not hold, and will not open it", () => {
    render(<VariableStrip tab={tab()} session={currentSession()} />);
    const greyed = screen.getByTestId("explore-variable-model");
    expect(greyed.getAttribute("data-live")).toBe("false");
    expect(greyed).toBeDisabled();

    fireEvent.click(greyed);
    expect(listPanels).not.toHaveBeenCalled();
    expect(currentSession().panels).toHaveLength(0);
  });

  it("puts pinned names first, keeping the runtime's order inside each group", () => {
    useAppStore.getState().noteExplorePanelOpened(SESSION_ID, {
      panelId: "summary::core.dataframe.editor",
      boundName: "summary",
      pinned: true,
      frozen: false,
    });
    render(<VariableStrip tab={tab()} session={currentSession()} />);
    const names = screen
      .getAllByRole("button")
      .map((node) => node.getAttribute("data-testid"))
      .filter((id): id is string => Boolean(id?.startsWith("explore-variable-")));
    expect(names).toEqual([
      "explore-variable-summary",
      "explore-variable-df",
      "explore-variable-model",
    ]);
  });
});

describe("a click is a producing request (FR-019)", () => {
  it("asks the backend for this variable's type and mounts the producing panel", async () => {
    render(<VariableStrip tab={tab()} session={currentSession()} />);
    fireEvent.click(screen.getByTestId("explore-variable-df"));

    await waitFor(() => expect(listPanels).toHaveBeenCalledWith("DataFrame"));
    await waitFor(() => expect(currentSession().panels).toHaveLength(1));

    const [slot] = currentSession().panels;
    expect(slot.boundName).toBe("df");
    // The producing panel, not the displaying one the catalogue listed first:
    // FR-048 filters the candidates to those that can serve the request before
    // anything else applies.
    expect(slot.panelId).toBe("df::core.dataframe.editor");
    expect(slot.pinned).toBe(false);
  });

  it("falls back to a displaying panel when no panel produces for the type", async () => {
    listPanels.mockResolvedValue({
      panels: [
        {
          panel_id: "core.dataframe.basic",
          capability: "displaying",
          target_type: "DataFrame",
          descriptor: descriptorFor("core.dataframe.basic", "displaying"),
        },
      ],
      diagnostics: [],
    });
    render(<VariableStrip tab={tab()} session={currentSession()} />);
    fireEvent.click(screen.getByTestId("explore-variable-df"));

    // FR-049: the request is answered with the displaying resolution, and the
    // descriptor it carries grants no outbound path.
    await waitFor(() => expect(currentSession().panels).toHaveLength(1));
    expect(currentSession().panels[0].panelId).toBe("df::core.dataframe.basic");
  });

  it("closes an unpinned panel on a second click and leaves a pinned one open", async () => {
    render(<VariableStrip tab={tab()} session={currentSession()} />);
    fireEvent.click(screen.getByTestId("explore-variable-df"));
    await waitFor(() => expect(currentSession().panels).toHaveLength(1));

    cleanup();
    render(<VariableStrip tab={tab()} session={currentSession()} />);
    fireEvent.click(screen.getByTestId("explore-variable-df"));
    expect(currentSession().panels).toHaveLength(0);

    // Pinned: the same click leaves it where it is (FR-020).
    useAppStore.getState().noteExplorePanelOpened(SESSION_ID, {
      panelId: "df::core.dataframe.editor",
      boundName: "df",
      pinned: true,
      frozen: false,
    });
    cleanup();
    render(<VariableStrip tab={tab()} session={currentSession()} />);
    fireEvent.click(screen.getByTestId("explore-variable-df"));
    expect(currentSession().panels).toHaveLength(1);
  });
});

describe("declared outputs pin themselves (FR-020)", () => {
  it("opens and pins a declared output once the kernel holds it", async () => {
    const report: ExplorePackagingCheckResponse = {
      session_id: SESSION_ID,
      is_packageable: true,
      cells: ["c1"],
      inputs: [],
      outputs: [
        {
          name: "table",
          direction: "output",
          data_type: "DataFrame",
          extension: ".csv",
          bound_name: "summary",
        },
      ],
      problems: [],
    };
    useAppStore.getState().applyExplorePackagingReport(SESSION_ID, report);

    render(<VariableStrip tab={tab()} session={currentSession()} />);

    await waitFor(() => expect(currentSession().panels).toHaveLength(1));
    const [slot] = currentSession().panels;
    expect(slot.boundName).toBe("summary");
    expect(slot.pinned).toBe(true);
    expect(currentSession().pinnedNames).toContain("summary");
  });

  it("does not open a declared output the kernel does not hold yet", async () => {
    useAppStore.getState().applyExplorePackagingReport(SESSION_ID, {
      session_id: SESSION_ID,
      is_packageable: false,
      cells: [],
      inputs: [],
      outputs: [
        {
          name: "fit",
          direction: "output",
          data_type: "Model",
          extension: ".pkl",
          bound_name: "model",
        },
      ],
      problems: [],
    });
    render(<VariableStrip tab={tab()} session={currentSession()} />);
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(currentSession().panels).toHaveLength(0);
  });
});
