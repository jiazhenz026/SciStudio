/**
 * ADR-054 spec 4 (T-012) — the packaging report (FR-028).
 *
 * Two shapes of report and the one decision between them: a clean plan lists
 * the slice and the ports and lets the person confirm, and a refused one names
 * the offending cells and the reads and does not.
 *
 * The check is asserted as *first*, not as one of two requests in some order:
 * FR-028's whole point is that nothing is written before the person has seen
 * what packaging would do, so the test presses the control and asserts that
 * the packaging route was not called.
 */

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { resetAppStore } from "../testUtils";
import { useAppStore } from "../store";
import type { ExplorePackagingCheckResponse, ExploreSessionResponse } from "../types/api";

import { PackagingControl, canConfirmPackaging, refusalsOf } from "./PackagingReport";

const checkExplorePackaging = vi.fn();
const packageExploreSession = vi.fn();
vi.mock("../lib/api/explore", () => ({
  exploreApi: {
    checkExplorePackaging: (...args: unknown[]) => checkExplorePackaging(...args),
    packageExploreSession: (...args: unknown[]) => packageExploreSession(...args),
  },
}));

const PATH = "explore/analysis.ipynb";
const SESSION_ID = "sess-pack";

function sessionResponse(): ExploreSessionResponse {
  return {
    session_id: SESSION_ID,
    notebook_path: PATH,
    has_kernel: true,
    needs_restart: false,
    current_cell: "c2",
    notebook_commit: "abc123",
    bound_run: null,
    cells: [
      { cell_id: "c1", cell_type: "code", source: "df = load()", enabled: true, marks: [] },
      {
        cell_id: "c2",
        cell_type: "code",
        source: "scistudio.output(t=df)",
        enabled: true,
        marks: [],
      },
    ],
  };
}

function cleanReport(): ExplorePackagingCheckResponse {
  return {
    session_id: SESSION_ID,
    is_packageable: true,
    cells: ["c1", "c2"],
    inputs: [
      {
        name: "source",
        direction: "input",
        data_type: "DataFrame",
        extension: ".parquet",
        bound_name: "raw",
      },
    ],
    outputs: [
      {
        name: "t",
        direction: "output",
        data_type: "DataFrame",
        extension: ".parquet",
        bound_name: "df",
      },
    ],
    problems: [],
  };
}

function refusedReport(): ExplorePackagingCheckResponse {
  return {
    session_id: SESSION_ID,
    is_packageable: false,
    cells: [],
    inputs: [],
    outputs: [],
    problems: [
      {
        kind: "unresolved_read",
        message: "The declared-output slice reads names no enabled cell above it changes.",
        cell_ids: ["c2"],
        names: ["helper", "scale"],
        refuses: true,
      },
      {
        kind: "duplicate_output_declaration",
        message: "The port 't' was declared as an output more than once.",
        cell_ids: ["c2"],
        names: ["t"],
        refuses: false,
      },
    ],
  };
}

function session() {
  return useAppStore.getState().sessions[PATH];
}

beforeEach(() => {
  resetAppStore();
  useAppStore.setState({ sessions: {}, sessionPathById: {}, pendingExploreEvents: {}, tabs: [] });
  useAppStore.getState().applyExploreSession(sessionResponse());
  checkExplorePackaging.mockReset();
  packageExploreSession.mockReset();
  packageExploreSession.mockResolvedValue({});
});

afterEach(cleanup);

describe("the check comes first (FR-028)", () => {
  it("requests the check and writes nothing when the control is pressed", async () => {
    checkExplorePackaging.mockResolvedValue(cleanReport());
    render(<PackagingControl session={session()} />);

    fireEvent.click(screen.getByTestId("explore-package-button"));

    await waitFor(() => expect(checkExplorePackaging).toHaveBeenCalledWith(SESSION_ID));
    expect(packageExploreSession).not.toHaveBeenCalled();
  });
});

describe("a clean report (FR-028)", () => {
  it("lists the slice cells and the inferred ports and enables confirm", async () => {
    checkExplorePackaging.mockResolvedValue(cleanReport());
    const { rerender } = render(<PackagingControl session={session()} />);

    fireEvent.click(screen.getByTestId("explore-package-button"));
    await waitFor(() => expect(checkExplorePackaging).toHaveBeenCalled());
    rerender(<PackagingControl session={session()} />);

    const slice = screen.getAllByTestId("explore-packaging-slice-cell").map((el) => el.textContent);
    expect(slice).toEqual(["c1", "c2"]);

    const ports = screen.getAllByTestId("explore-packaging-port").map((el) => el.textContent);
    expect(ports.some((text) => text?.includes("source") && text.includes("DataFrame"))).toBe(true);
    expect(ports.some((text) => text?.includes("t") && text.includes("df"))).toBe(true);

    // Confirm needs a name as well as a clean plan: `PackageRequest.block_name`
    // is required, so an unnamed block is not a thing the runtime can write.
    const confirm = screen.getByTestId("explore-packaging-confirm") as HTMLButtonElement;
    expect(confirm.disabled).toBe(true);
    fireEvent.change(screen.getByTestId("explore-packaging-name"), {
      target: { value: "Segment Cells" },
    });
    expect((screen.getByTestId("explore-packaging-confirm") as HTMLButtonElement).disabled).toBe(
      false,
    );
  });

  it("confirms through the packaging route and writes no block locally", async () => {
    checkExplorePackaging.mockResolvedValue(cleanReport());
    const { rerender } = render(<PackagingControl session={session()} />);
    fireEvent.click(screen.getByTestId("explore-package-button"));
    await waitFor(() => expect(checkExplorePackaging).toHaveBeenCalled());
    rerender(<PackagingControl session={session()} />);

    fireEvent.change(screen.getByTestId("explore-packaging-name"), {
      target: { value: "Segment Cells" },
    });
    fireEvent.click(screen.getByTestId("explore-packaging-confirm"));

    await waitFor(() =>
      expect(packageExploreSession).toHaveBeenCalledWith(SESSION_ID, {
        block_name: "Segment Cells",
        on_new_input: "replay",
      }),
    );
    // FR-029: the packaged block appears because the runtime published the
    // event, so the confirm leaves the slice's packaged record untouched.
    expect(session().lastPackaged).toBeNull();
  });
});

describe("a refused report (FR-028)", () => {
  it("names the offending cells and reads and disables confirm", async () => {
    checkExplorePackaging.mockResolvedValue(refusedReport());
    const { rerender } = render(<PackagingControl session={session()} />);

    fireEvent.click(screen.getByTestId("explore-package-button"));
    await waitFor(() => expect(checkExplorePackaging).toHaveBeenCalled());
    rerender(<PackagingControl session={session()} />);

    const refusals = screen.getByTestId("explore-packaging-refusals");
    expect(refusals.textContent).toContain("c2");
    expect(refusals.textContent).toContain("helper, scale");

    // Named, but under the notices rather than the refusals: packaging
    // resolves a duplicate declaration instead of rejecting it.
    expect(screen.getByTestId("explore-packaging-notices").textContent).toContain(
      "declared as an output more than once",
    );

    fireEvent.change(screen.getByTestId("explore-packaging-name"), {
      target: { value: "Whatever" },
    });
    expect((screen.getByTestId("explore-packaging-confirm") as HTMLButtonElement).disabled).toBe(
      true,
    );
    expect(screen.queryAllByTestId("explore-packaging-slice-cell")).toHaveLength(0);
  });
});

describe("the confirm predicate", () => {
  it("refuses a report that says packageable while still listing a refusal", () => {
    const disagreeing = { ...refusedReport(), is_packageable: true };
    expect(refusalsOf(disagreeing)).toHaveLength(1);
    expect(canConfirmPackaging(disagreeing, "Name")).toBe(false);
  });

  it("refuses when there is no report at all", () => {
    expect(canConfirmPackaging(null, "Name")).toBe(false);
  });
});
