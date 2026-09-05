/**
 * ADR-054 spec 4 (T-013) — the kernel list (FR-014's share, FR-015, FR-016).
 *
 * Three properties, and the middle one is the reason this list is not a
 * simpler component:
 *
 *   1. Every live kernel in the project is listed, with its session and its
 *      memory and an end control.
 *   2. The end control **sends the command and nothing else**. The row moves
 *      when the `explore.kernel_state` event arrives, so the test asserts the
 *      row is still there after the response and gone after the event.
 *   3. A retired kernel offers restart — and `ExploreSessionService.kernels()`
 *      never lists one, so that row can only come from the session's own
 *      kernel view.
 */

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { resetAppStore } from "../testUtils";
import { useAppStore } from "../store";
import type {
  ExploreKernelListItem,
  ExploreSessionEventMessage,
  ExploreSessionResponse,
} from "../types/api";

import { KernelList, buildKernelRows, formatMemory } from "./KernelList";

const listExploreKernels = vi.fn();
const endExploreKernel = vi.fn();
const restartExploreSession = vi.fn();
vi.mock("../lib/api/explore", () => ({
  exploreApi: {
    listExploreKernels: (...args: unknown[]) => listExploreKernels(...args),
    endExploreKernel: (...args: unknown[]) => endExploreKernel(...args),
    restartExploreSession: (...args: unknown[]) => restartExploreSession(...args),
  },
}));

function kernel(overrides: Partial<ExploreKernelListItem> = {}): ExploreKernelListItem {
  return {
    session_id: "s1",
    notebook_path: "explore/one.ipynb",
    state: "idle",
    pid: 4242,
    memory_bytes: 512 * 1024 * 1024,
    python_executable: "/usr/bin/python",
    started_at: 1700000000,
    ...overrides,
  };
}

function sessionResponse(sessionId: string, path: string): ExploreSessionResponse {
  return {
    session_id: sessionId,
    notebook_path: path,
    has_kernel: true,
    needs_restart: false,
    current_cell: null,
    notebook_commit: null,
    bound_run: null,
    cells: [],
  };
}

function kernelEvent(
  sessionId: string,
  data: Record<string, unknown>,
  timestamp = "2026-01-01T00:00:01Z",
): ExploreSessionEventMessage {
  return { type: "explore.kernel_state", session_id: sessionId, data, timestamp };
}

beforeEach(() => {
  resetAppStore();
  useAppStore.setState({
    sessions: {},
    sessionPathById: {},
    pendingExploreEvents: {},
    exploreKernels: [],
    tabs: [],
  });
  listExploreKernels.mockReset();
  endExploreKernel.mockReset();
  restartExploreSession.mockReset();
  listExploreKernels.mockResolvedValue({ kernels: [] });
  endExploreKernel.mockResolvedValue({});
  restartExploreSession.mockResolvedValue({});
});

afterEach(cleanup);

describe("every kernel in the project (FR-015)", () => {
  it("lists each with its session and its memory and an end control", async () => {
    listExploreKernels.mockResolvedValue({
      kernels: [
        kernel({ session_id: "s1", notebook_path: "explore/one.ipynb" }),
        kernel({
          session_id: "s2",
          notebook_path: "explore/two.ipynb",
          state: "busy",
          memory_bytes: 2 * 1024 ** 3,
        }),
        kernel({
          session_id: "s3",
          notebook_path: "explore/three.ipynb",
          state: "starting",
          memory_bytes: null,
        }),
      ],
    });
    render(<KernelList />);
    fireEvent.click(screen.getByTestId("explore-kernel-list-toggle"));

    await waitFor(() => expect(listExploreKernels).toHaveBeenCalled());
    await screen.findByTestId("explore-kernel-row-s1");

    expect(screen.getByTestId("explore-kernel-row-s2")).toBeTruthy();
    expect(screen.getByTestId("explore-kernel-row-s3")).toBeTruthy();
    expect(screen.getByTestId("explore-kernel-row-s1").textContent).toContain("one.ipynb");
    // Rows are ordered by notebook path, so `three` sits between `one` and
    // `two`: the list is stable across fetches rather than in service order.
    expect(screen.getAllByTestId("explore-kernel-row-memory").map((el) => el.textContent)).toEqual([
      "512 MB",
      "—",
      "2.0 GB",
    ]);
    expect(screen.getByTestId("explore-kernel-end-s1")).toBeTruthy();
    expect(screen.getByTestId("explore-kernel-end-s2")).toBeTruthy();
  });
});

describe("the end control (FR-015, FR-034)", () => {
  it("sends the command and moves the list only when the event arrives", async () => {
    useAppStore.getState().applyExploreSession(sessionResponse("s1", "explore/one.ipynb"));
    listExploreKernels.mockResolvedValue({ kernels: [kernel({ session_id: "s1" })] });
    render(<KernelList />);
    fireEvent.click(screen.getByTestId("explore-kernel-list-toggle"));
    await screen.findByTestId("explore-kernel-row-s1");

    fireEvent.click(screen.getByTestId("explore-kernel-end-s1"));
    await waitFor(() => expect(endExploreKernel).toHaveBeenCalledWith("s1"));

    // The command has returned and the row is still there: nothing local was
    // written, and the list has not been re-fetched behind the person's back.
    expect(listExploreKernels).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId("explore-kernel-row-s1")).toBeTruthy();

    // The runtime says the kernel is gone; now the row goes.
    useAppStore
      .getState()
      .applyExploreSessionEvent(kernelEvent("s1", { state: "not-started", pid: null }));
    await waitFor(() => expect(screen.queryByTestId("explore-kernel-row-s1")).toBeNull());
    expect(screen.getByTestId("explore-kernel-list-empty")).toBeTruthy();
  });

  it("shows the state the event reports rather than the one the list fetched", async () => {
    useAppStore.getState().applyExploreSession(sessionResponse("s1", "explore/one.ipynb"));
    listExploreKernels.mockResolvedValue({
      kernels: [kernel({ session_id: "s1", state: "idle", memory_bytes: 1024 })],
    });
    render(<KernelList />);
    fireEvent.click(screen.getByTestId("explore-kernel-list-toggle"));
    await screen.findByTestId("explore-kernel-row-s1");

    useAppStore
      .getState()
      .applyExploreSessionEvent(
        kernelEvent("s1", { state: "busy", pid: 99, memory_bytes: 3 * 1024 * 1024 }),
      );

    await waitFor(() =>
      expect(screen.getByTestId("explore-kernel-row-s1").getAttribute("data-kernel-state")).toBe(
        "busy",
      ),
    );
    expect(screen.getByTestId("explore-kernel-row-memory").textContent).toBe("3 MB");
  });
});

describe("a retired kernel (FR-016)", () => {
  it("is offered a restart even though the kernel list never carries it", async () => {
    useAppStore.getState().applyExploreSession(sessionResponse("s1", "explore/one.ipynb"));
    // What `retire_kernels` publishes: dead, and needing a restart. The list
    // response is empty because `kernels()` keeps only starting/idle/busy.
    useAppStore
      .getState()
      .applyExploreSessionEvent(kernelEvent("s1", { state: "dead", needs_restart: true }));
    listExploreKernels.mockResolvedValue({ kernels: [] });

    render(<KernelList />);
    fireEvent.click(screen.getByTestId("explore-kernel-list-toggle"));

    const row = await screen.findByTestId("explore-kernel-row-s1");
    expect(row.getAttribute("data-needs-restart")).toBe("true");
    expect(screen.queryByTestId("explore-kernel-end-s1")).toBeNull();

    fireEvent.click(screen.getByTestId("explore-kernel-restart-s1"));
    await waitFor(() => expect(restartExploreSession).toHaveBeenCalledWith("s1"));
  });
});

describe("the merge rules", () => {
  it("keeps a listed kernel whose session has had no event applied", () => {
    const sessions = useAppStore.getState().sessions;
    expect(buildKernelRows([kernel({ session_id: "s1" })], sessions)).toHaveLength(1);
  });

  it("formats what the runtime reported and says so when it reported nothing", () => {
    expect(formatMemory(null)).toBe("—");
    expect(formatMemory(900)).toBe("900 B");
    expect(formatMemory(4096)).toBe("4 KB");
  });
});
