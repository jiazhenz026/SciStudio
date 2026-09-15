/**
 * #2385 — booting from the `open_gui` project deep link.
 *
 * `?project=<path>&workflow=<id>` must land on the project the backend already
 * has open, without the welcome page and without re-opening the project (which
 * would reset the user's desktop session). A mismatch reports an error and
 * leaves the session alone; no params keep the ordinary welcome boot.
 */
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "./App";
import { ATTACHED_PROJECT_HEADER, setAttachedProjectBinding } from "./lib/api/core";
import { useAppStore } from "./store";
import { resetAppStore } from "./testUtils";

const PROJECT_PATH = "/Users/me/My Projects/细胞 Demo";

const PROJECT = {
  id: "project-abc123",
  name: "Demo",
  description: "",
  path: PROJECT_PATH,
  last_opened: null,
  workflow_count: 2,
  workflows: ["main", "qc"],
  current_workflow_id: "main",
};

interface FetchCall {
  url: string;
  method: string;
  attachedProject: string | null;
}

function jsonResponse(data: unknown) {
  return Promise.resolve({ ok: true, status: 200, json: async () => data });
}

function installFetch(
  active: {
    project: typeof PROJECT | null;
    active_workflow_id: string | null;
  },
  { refuseWorkflowRead = false }: { refuseWorkflowRead?: boolean } = {},
) {
  const calls: FetchCall[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      calls.push({
        url,
        method: (init?.method ?? "GET").toUpperCase(),
        attachedProject: new Headers(init?.headers).get(ATTACHED_PROJECT_HEADER),
      });
      if (url.endsWith("/api/projects/")) return jsonResponse([PROJECT]);
      if (url.endsWith("/api/projects/active")) return jsonResponse(active);
      if (url.endsWith("/api/tutorials/catalogue")) {
        return jsonResponse({ groups: [], active: null, diagnostics: [] });
      }
      if (url.endsWith("/api/tutorials/sessions/active")) return jsonResponse(null);
      if (url.endsWith("/api/blocks/")) return jsonResponse({ blocks: [] });
      const workflowMatch = url.match(/\/api\/workflows\/([^/?]+)$/);
      if (workflowMatch && refuseWorkflowRead) {
        // The backend's answer once the user switched projects (#2385).
        return Promise.resolve({
          ok: false,
          status: 409,
          statusText: "Conflict",
          json: async () => ({
            detail: { error: "attached_project_changed", message: "switched" },
          }),
        });
      }
      if (workflowMatch) {
        const id = decodeURIComponent(workflowMatch[1]);
        return jsonResponse({
          id,
          version: "1.0.0",
          description: "",
          nodes: [],
          edges: [],
          metadata: {},
          state_version: 1,
        });
      }
      return jsonResponse({});
    }),
  );
  return calls;
}

function setSearch(search: string) {
  window.history.replaceState(null, "", `/${search}`);
}

function deepLink(project: string, workflow?: string) {
  const params = new URLSearchParams({ project });
  if (workflow) params.set("workflow", workflow);
  return `?${params.toString()}`;
}

/**
 * Any call that would re-open a project or publish editor context.
 *
 * `POST /api/blocks/reload` is left out: the block palette issues it on every
 * mount (#2151), in the desktop window too, and it only re-scans block sources.
 */
function sessionMutations(calls: FetchCall[]): FetchCall[] {
  return calls.filter(
    (call) =>
      (call.method !== "GET" && !call.url.endsWith("/api/blocks/reload")) ||
      (/\/api\/projects\/[^/]+$/.test(call.url) && !call.url.endsWith("/api/projects/active")),
  );
}

class NoopResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}

class NoopEventSource {
  onmessage: unknown = null;
  onerror: unknown = null;
  onopen: unknown = null;
  addEventListener() {}
  removeEventListener() {}
  close() {}
}

describe("App project deep link (#2385)", () => {
  beforeEach(() => {
    resetAppStore();
    // The project workspace needs ResizeObserver and EventSource, which jsdom lacks.
    vi.stubGlobal("ResizeObserver", NoopResizeObserver);
    vi.stubGlobal("EventSource", NoopEventSource);
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    setAttachedProjectBinding(null);
    setSearch("");
  });

  it("attaches to the open project and workflow without the welcome page", async () => {
    const calls = installFetch({ project: PROJECT, active_workflow_id: "main" });
    setSearch(deepLink(PROJECT_PATH, "qc"));

    render(<App />);

    await waitFor(() => expect(useAppStore.getState().currentProject?.id).toBe(PROJECT.id));
    await waitFor(() => expect(useAppStore.getState().workflowId).toBe("qc"));
    expect(screen.queryByText("New Project")).toBeNull();
    expect(useAppStore.getState().lastError).toBeNull();
    // Attach is read-only: no project re-open, no active-context publish.
    expect(sessionMutations(calls)).toEqual([]);
    // Once attached, requests are bound to the verified project.
    const workflowRead = calls.find((call) => call.url.endsWith("/api/workflows/qc"));
    expect(workflowRead?.attachedProject).toBe(PROJECT.id);
  });

  it("detaches when the backend refuses a bound request after a project switch", async () => {
    const calls = installFetch(
      { project: PROJECT, active_workflow_id: "main" },
      { refuseWorkflowRead: true },
    );
    setSearch(deepLink(PROJECT_PATH, "qc"));

    render(<App />);

    const banner = await screen.findByTestId("app-error-banner");
    expect(banner.textContent).toContain("no longer has");
    expect(useAppStore.getState().currentProject).toBeNull();
    expect(useAppStore.getState().tabs).toEqual([]);
    expect(sessionMutations(calls)).toEqual([]);
    // Later requests stay bound, so none of them can reach the new project.
    const afterDetach = calls.filter((call) => call.url.endsWith("/api/workflows/qc"));
    expect(afterDetach.every((call) => call.attachedProject === PROJECT.id)).toBe(true);
  });

  it("falls back to the backend's active workflow when the link names none", async () => {
    installFetch({ project: PROJECT, active_workflow_id: "qc" });
    setSearch(deepLink(`${PROJECT_PATH}/`));

    render(<App />);

    await waitFor(() => expect(useAppStore.getState().workflowId).toBe("qc"));
    expect(useAppStore.getState().currentProject?.path).toBe(PROJECT_PATH);
  });

  it("reports a mismatch and leaves the session unchanged", async () => {
    const calls = installFetch({ project: PROJECT, active_workflow_id: "main" });
    setSearch(deepLink("/Users/me/Other Project", "main"));

    render(<App />);

    const banner = await screen.findByTestId("app-error-banner");
    expect(banner.textContent).toContain("/Users/me/Other Project");
    expect(banner.textContent).toContain("left unchanged");
    expect(useAppStore.getState().currentProject).toBeNull();
    expect(sessionMutations(calls)).toEqual([]);
  });

  it("reports when the backend has no project open", async () => {
    installFetch({ project: null, active_workflow_id: null });
    setSearch(deepLink(PROJECT_PATH));

    render(<App />);

    const banner = await screen.findByTestId("app-error-banner");
    expect(banner.textContent).toContain("no project open");
    expect(useAppStore.getState().currentProject).toBeNull();
  });

  it("boots to the welcome page as before when there is no deep link", async () => {
    const calls = installFetch({ project: PROJECT, active_workflow_id: "main" });
    setSearch("");

    render(<App />);

    expect(await screen.findByText("New Project")).toBeInTheDocument();
    expect(calls.some((call) => call.url.endsWith("/api/projects/active"))).toBe(false);
    expect(useAppStore.getState().currentProject).toBeNull();
  });
});
