/**
 * ADR-055 Spec 4 — identity chrome and the update notice (#2322; stories 3
 * and 7, FR-004, FR-007).
 *
 * Every capability is exercised present and absent, and every request is
 * checked at the root mount and under `/user/alice/scistudio`: capability URLs
 * are route paths the frontend resolves under the service prefix exactly as
 * it resolves API calls. Route paths are neutral fixtures.
 */

import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { resetBasePathCacheForTests } from "../../lib/api/base-path";
import { resetCapabilitiesCacheForTests } from "../../lib/capabilities";
import { Toolbar } from "../Toolbar";
import { EnterpriseToolbarControls } from "./EnterpriseToolbarControls";
import { browserNavigation } from "./enterpriseApi";
import { UPDATE_POLL_INTERVAL_MS } from "./useUpdateStatus";

const LOGOUT_URL = "/api/test-edition/session/logout";
const STATUS_URL = "/api/test-edition/update/status";
const RESTART_URL = "/api/test-edition/update/restart";
const MOUNTS = [
  ["the root mount", ""],
  ["a prefixed mount", "/user/alice/scistudio"],
] as const;

const fetchMock = vi.fn();
let assign: ReturnType<typeof vi.spyOn>;

function declare(value: unknown): void {
  if (value === undefined) {
    delete window.__SCISTUDIO_CAPABILITIES__;
  } else {
    window.__SCISTUDIO_CAPABILITIES__ = value;
  }
  resetCapabilitiesCacheForTests();
}

function mountAt(prefix: string): void {
  if (prefix) {
    window.__SCISTUDIO_BASE_PATH__ = prefix;
  } else {
    delete window.__SCISTUDIO_BASE_PATH__;
  }
  resetBasePathCacheForTests();
}

function jsonResponse(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: status === 200 ? "OK" : "Error",
    json: async () => body,
  } as unknown as Response;
}

function statusBody(overrides: Record<string, unknown> = {}) {
  return {
    running_version: "0.3.5",
    installed_version: "0.3.6",
    update_available: true,
    runs_active: false,
    ...overrides,
  };
}

function absolute(location: string): string {
  return new URL(location, window.location.href).href;
}

/** The JSON body of every restart POST, in order. */
function postBodies(): unknown[] {
  return postCalls().map(([, init]) => JSON.parse(String((init as RequestInit).body)));
}

function postCalls(): unknown[][] {
  return fetchMock.mock.calls.filter(
    ([, init]) => (init as RequestInit | undefined)?.method === "POST",
  );
}

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
  assign = vi.spyOn(browserNavigation, "assign").mockImplementation(() => {});
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  declare(undefined);
  mountAt("");
});

describe("with no capability declared", () => {
  it("renders no enterprise control and sends no request", () => {
    declare(undefined);
    const { container } = render(<EnterpriseToolbarControls projectOpen />);
    expect(container).toBeEmptyDOMElement();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("renders nothing for capabilities that gate no toolbar control", () => {
    declare({ version: 1, aiChatDisabled: true });
    const { container } = render(<EnterpriseToolbarControls projectOpen />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe("identity chrome", () => {
  it("shows the user name and Logout", () => {
    declare({ version: 1, identity: { user: "alice", logoutUrl: LOGOUT_URL } });
    render(<EnterpriseToolbarControls projectOpen />);
    expect(screen.getByTestId("enterprise-identity-user")).toHaveTextContent("alice");
    expect(screen.getByRole("button", { name: /logout/i })).toBeInTheDocument();
  });

  it("shows the user name without Logout when no logout route was given", () => {
    declare({ version: 1, identity: { user: "alice" } });
    render(<EnterpriseToolbarControls projectOpen />);
    expect(screen.getByTestId("enterprise-identity-user")).toHaveTextContent("alice");
    expect(screen.queryByRole("button", { name: /logout/i })).toBeNull();
  });

  it.each(MOUNTS)(
    "logs out with a same-origin POST under %s, then follows the location",
    async (_mount, prefix) => {
      mountAt(prefix);
      declare({ version: 1, identity: { user: "alice", logoutUrl: LOGOUT_URL } });
      fetchMock.mockResolvedValue(jsonResponse({ location: "/hub/logout" }));
      render(<EnterpriseToolbarControls projectOpen />);

      fireEvent.click(screen.getByRole("button", { name: /logout/i }));

      await waitFor(() => expect(assign).toHaveBeenCalledWith(absolute("/hub/logout")));
      expect(fetchMock).toHaveBeenCalledTimes(1);
      const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
      expect(url).toBe(`${prefix}${LOGOUT_URL}`);
      expect(init.method).toBe("POST");
      expect(init.credentials).toBe("same-origin");
    },
  );

  it("refuses to follow a location that is not http(s)", async () => {
    declare({ version: 1, identity: { user: "alice", logoutUrl: LOGOUT_URL } });
    fetchMock.mockResolvedValue(jsonResponse({ location: "javascript:alert(1)" }));
    render(<EnterpriseToolbarControls projectOpen />);

    fireEvent.click(screen.getByRole("button", { name: /logout/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/logout failed/i);
    expect(assign).not.toHaveBeenCalled();
  });

  it("reports a refused logout and stays on the page", async () => {
    declare({ version: 1, identity: { user: "alice", logoutUrl: LOGOUT_URL } });
    fetchMock.mockResolvedValue(jsonResponse({ detail: "session already ended" }, 403));
    render(<EnterpriseToolbarControls projectOpen />);

    fireEvent.click(screen.getByRole("button", { name: /logout/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent("session already ended");
    expect(assign).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: /logout/i })).toBeEnabled();
  });

  it("sits in the toolbar", () => {
    vi.unstubAllGlobals();
    declare({ version: 1, identity: { user: "alice", logoutUrl: LOGOUT_URL } });
    render(
      <Toolbar
        activeTabKind="workflow"
        currentProject={null}
        isRunning={false}
        onAddAnnotation={vi.fn()}
        onCloseProject={vi.fn()}
        onDelete={vi.fn()}
        onImport={vi.fn()}
        onNewProject={vi.fn()}
        onNewWorkflow={vi.fn()}
        onOpenProject={vi.fn()}
        onOpenRecent={vi.fn()}
        onPause={vi.fn()}
        onReloadBlocks={vi.fn()}
        onReset={vi.fn()}
        onResume={vi.fn()}
        onRun={vi.fn()}
        onSave={vi.fn()}
        onSaveAs={vi.fn()}
        onStartFromSelected={vi.fn()}
        onStop={vi.fn()}
        recentProjects={[]}
        selectedNodeId={null}
        sseConnected
        workflowDirty={false}
        workflowId={null}
        workflowName=""
        wsConnected
      />,
    );
    expect(screen.getByTestId("enterprise-identity-user")).toHaveTextContent("alice");
  });
});

describe("update notice", () => {
  const UPDATE = { statusUrl: STATUS_URL, restartUrl: RESTART_URL };

  function serveStatus(body: Record<string, unknown>) {
    fetchMock.mockImplementation(async (_url: string, init?: RequestInit) =>
      init?.method === "POST"
        ? jsonResponse({ location: "/hub/spawn-pending/alice" })
        : jsonResponse(body),
    );
  }

  it("shows nothing while no update is available", async () => {
    declare({ version: 1, update: UPDATE });
    serveStatus(statusBody({ update_available: false }));
    render(<EnterpriseToolbarControls projectOpen />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(screen.queryByTestId("enterprise-update-notice")).toBeNull();
  });

  it("shows nothing for a status answer that is not the contract's shape", async () => {
    declare({ version: 1, update: UPDATE });
    serveStatus({ update_available: "yes" });
    render(<EnterpriseToolbarControls projectOpen />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(screen.queryByTestId("enterprise-update-notice")).toBeNull();
  });

  it.each(MOUNTS)(
    "polls the status route under %s every 60 s and on window focus",
    async (_mount, prefix) => {
      vi.useFakeTimers({ toFake: ["setInterval", "clearInterval"] });
      mountAt(prefix);
      declare({ version: 1, update: UPDATE });
      serveStatus(statusBody());
      render(<EnterpriseToolbarControls projectOpen />);

      expect(await screen.findByTestId("enterprise-update-notice")).toHaveTextContent("0.3.6");
      expect(fetchMock).toHaveBeenCalledTimes(1);
      expect(fetchMock.mock.calls[0][0]).toBe(`${prefix}${STATUS_URL}`);

      act(() => {
        vi.advanceTimersByTime(UPDATE_POLL_INTERVAL_MS);
      });
      await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));

      act(() => {
        window.dispatchEvent(new Event("focus"));
      });
      await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
      expect(fetchMock.mock.calls.every(([url]) => url === `${prefix}${STATUS_URL}`)).toBe(true);
      // Polling never restarts or navigates on its own.
      expect(postCalls()).toHaveLength(0);
      expect(assign).not.toHaveBeenCalled();
    },
  );

  it("never takes focus from what the user is doing", async () => {
    declare({ version: 1, update: UPDATE });
    serveStatus(statusBody());
    render(
      <div>
        <textarea data-testid="editor" />
        <EnterpriseToolbarControls projectOpen />
      </div>,
    );
    const editor = screen.getByTestId("editor");
    editor.focus();
    const notice = await screen.findByTestId("enterprise-update-notice");
    expect(notice).toHaveAttribute("role", "status");
    expect(document.activeElement).toBe(editor);
  });

  it.each(MOUNTS)(
    "restarts under %s only after confirmation, then follows the location",
    async (_mount, prefix) => {
      mountAt(prefix);
      declare({ version: 1, update: UPDATE });
      serveStatus(statusBody());
      render(<EnterpriseToolbarControls projectOpen />);

      fireEvent.click(await screen.findByTestId("enterprise-update-restart"));
      expect(await screen.findByTestId("enterprise-restart-dialog")).toBeInTheDocument();
      const confirm = screen.getByTestId("enterprise-restart-confirm");
      await waitFor(() => expect(confirm).toBeEnabled());
      expect(screen.queryByTestId("enterprise-restart-runs-warning")).toBeNull();
      expect(postCalls()).toHaveLength(0);

      fireEvent.click(confirm);

      await waitFor(() =>
        expect(assign).toHaveBeenCalledWith(absolute("/hub/spawn-pending/alice")),
      );
      expect(postCalls()).toHaveLength(1);
      expect(postCalls()[0][0]).toBe(`${prefix}${RESTART_URL}`);
      // No runs were active, so nothing was confirmed on the user's behalf.
      expect(postBodies()).toEqual([{ confirm_active_runs: false }]);
    },
  );

  it("sends the runs-active confirmation only after the warning was accepted", async () => {
    declare({ version: 1, update: UPDATE });
    serveStatus(statusBody({ runs_active: true }));
    render(<EnterpriseToolbarControls projectOpen />);

    fireEvent.click(await screen.findByTestId("enterprise-update-restart"));
    expect(await screen.findByTestId("enterprise-restart-runs-warning")).toBeInTheDocument();
    const confirm = screen.getByTestId("enterprise-restart-confirm");
    await waitFor(() => expect(confirm).toBeEnabled());
    expect(postCalls()).toHaveLength(0);

    fireEvent.click(confirm);

    await waitFor(() => expect(assign).toHaveBeenCalledWith(absolute("/hub/spawn-pending/alice")));
    expect(postBodies()).toEqual([{ confirm_active_runs: true }]);
  });

  it("warns before restarting while runs are active, and Cancel does nothing", async () => {
    declare({ version: 1, update: UPDATE });
    serveStatus(statusBody({ runs_active: true }));
    render(<EnterpriseToolbarControls projectOpen />);

    fireEvent.click(await screen.findByTestId("enterprise-update-restart"));
    expect(await screen.findByTestId("enterprise-restart-runs-warning")).toHaveTextContent(
      /runs are still active/i,
    );

    fireEvent.click(screen.getByTestId("enterprise-restart-cancel"));
    expect(screen.queryByTestId("enterprise-restart-dialog")).toBeNull();
    expect(postCalls()).toHaveLength(0);
    expect(assign).not.toHaveBeenCalled();
  });

  it("reports a refused restart and stays on the page", async () => {
    declare({ version: 1, update: UPDATE });
    fetchMock.mockImplementation(async (_url: string, init?: RequestInit) =>
      init?.method === "POST"
        ? jsonResponse({ detail: "restart is not allowed right now" }, 403)
        : jsonResponse(statusBody()),
    );
    render(<EnterpriseToolbarControls projectOpen />);

    fireEvent.click(await screen.findByTestId("enterprise-update-restart"));
    const confirm = await screen.findByTestId("enterprise-restart-confirm");
    await waitFor(() => expect(confirm).toBeEnabled());
    fireEvent.click(confirm);

    expect(await screen.findByRole("alert")).toHaveTextContent("restart is not allowed right now");
    expect(assign).not.toHaveBeenCalled();
  });

  it("keeps Confirm disabled until the status read on opening arrives", async () => {
    declare({ version: 1, update: UPDATE });
    let releaseOpeningRead: (() => void) | null = null;
    let reads = 0;
    fetchMock.mockImplementation(async (_url: string, init?: RequestInit) => {
      if (init?.method === "POST") return jsonResponse({ location: "/hub/spawn-pending/alice" });
      reads += 1;
      if (reads === 2) {
        // The read the dialog makes on opening: held until the test releases it.
        await new Promise<void>((resolve) => {
          releaseOpeningRead = resolve;
        });
      }
      return jsonResponse(statusBody());
    });
    render(<EnterpriseToolbarControls projectOpen />);

    fireEvent.click(await screen.findByTestId("enterprise-update-restart"));
    expect(await screen.findByTestId("enterprise-restart-checking")).toBeInTheDocument();
    expect(screen.getByTestId("enterprise-restart-confirm")).toBeDisabled();

    await waitFor(() => expect(releaseOpeningRead).not.toBeNull());
    act(() => {
      releaseOpeningRead?.();
    });
    await waitFor(() => expect(screen.getByTestId("enterprise-restart-confirm")).toBeEnabled());
    expect(screen.queryByTestId("enterprise-restart-checking")).toBeNull();
  });

  it("asks again when runs start between opening the dialog and confirming", async () => {
    declare({ version: 1, update: UPDATE });
    // Poll and opening read: no runs. Every later read: runs are active.
    let reads = 0;
    fetchMock.mockImplementation(async (_url: string, init?: RequestInit) => {
      if (init?.method === "POST") return jsonResponse({ location: "/hub/spawn-pending/alice" });
      reads += 1;
      return jsonResponse(statusBody({ runs_active: reads > 2 }));
    });
    render(<EnterpriseToolbarControls projectOpen />);

    fireEvent.click(await screen.findByTestId("enterprise-update-restart"));
    const confirm = await screen.findByTestId("enterprise-restart-confirm");
    await waitFor(() => expect(confirm).toBeEnabled());
    expect(screen.queryByTestId("enterprise-restart-runs-warning")).toBeNull();

    // Runs started meanwhile: the first click shows the warning and sends nothing.
    fireEvent.click(confirm);
    expect(await screen.findByTestId("enterprise-restart-runs-warning")).toBeInTheDocument();
    await waitFor(() => expect(confirm).toBeEnabled());
    expect(postCalls()).toHaveLength(0);
    expect(assign).not.toHaveBeenCalled();

    // Confirming again, with the warning shown, restarts and says so.
    fireEvent.click(confirm);
    await waitFor(() => expect(assign).toHaveBeenCalledWith(absolute("/hub/spawn-pending/alice")));
    expect(postBodies()).toEqual([{ confirm_active_runs: true }]);
  });

  it("names the runs a 409 reports, asks again, and retries with the confirmation", async () => {
    declare({ version: 1, update: UPDATE });
    // Every status read says no runs; the backend knows better on the first POST.
    let posts = 0;
    fetchMock.mockImplementation(async (_url: string, init?: RequestInit) => {
      if (init?.method !== "POST") return jsonResponse(statusBody());
      posts += 1;
      return posts === 1
        ? jsonResponse({ active_runs: ["segment-cells", "export-table"] }, 409)
        : jsonResponse({ location: "/hub/spawn-pending/alice" });
    });
    render(<EnterpriseToolbarControls projectOpen />);

    fireEvent.click(await screen.findByTestId("enterprise-update-restart"));
    const confirm = await screen.findByTestId("enterprise-restart-confirm");
    await waitFor(() => expect(confirm).toBeEnabled());
    expect(screen.queryByTestId("enterprise-restart-runs-warning")).toBeNull();

    fireEvent.click(confirm);
    const warning = await screen.findByTestId("enterprise-restart-runs-warning");
    expect(warning).toHaveTextContent("segment-cells, export-table");
    await waitFor(() => expect(confirm).toBeEnabled());
    expect(assign).not.toHaveBeenCalled();

    fireEvent.click(confirm);
    await waitFor(() => expect(assign).toHaveBeenCalledWith(absolute("/hub/spawn-pending/alice")));
    expect(postBodies()).toEqual([{ confirm_active_runs: false }, { confirm_active_runs: true }]);
  });

  it("does not enable Confirm when the status cannot be read", async () => {
    declare({ version: 1, update: UPDATE });
    let reads = 0;
    fetchMock.mockImplementation(async () => {
      reads += 1;
      return reads === 1 ? jsonResponse(statusBody()) : jsonResponse({ detail: "down" }, 503);
    });
    render(<EnterpriseToolbarControls projectOpen />);

    fireEvent.click(await screen.findByTestId("enterprise-update-restart"));
    expect(await screen.findByRole("alert")).toHaveTextContent(/could not check/i);
    expect(screen.getByTestId("enterprise-restart-confirm")).toBeDisabled();
    expect(postCalls()).toHaveLength(0);
  });
});
