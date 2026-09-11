/**
 * #2297 — `mockBackend()` checks every mock against the backend OpenAPI contract.
 *
 * These tests use real endpoints from `tests/contracts/openapi.json`
 * (`GET /api/plots` → `PlotListResponse`, `POST /api/plots/run` →
 * `PlotRunRequest`/`PlotRunResponse`, `DELETE /api/plots/{plot_id}`) so they
 * also prove the committed snapshot loads and resolves.
 */
import { afterEach, describe, expect, it } from "vitest";

import { apiFetch } from "../../lib/api/core";
import { ContractViolation, mockBackend, reply, type MockBackend } from "./mockBackend";
import { checkMockBody, loadContract } from "./openapi";

const PLOT_LIST = { count: 0, plots: [], warnings: [] };

const PLOT_RUN = {
  status: "succeeded",
  data_ref: "data-abc123",
  recorded_type: "PlotArtifact",
  type_chain: ["DataObject", "PlotArtifact"],
  cache_key: null,
  artifact_paths: [],
  source: null,
  warnings: [],
  errors: [],
};

function postJson(path: string, body: unknown): Promise<Response> {
  return fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

describe("mockBackend", () => {
  let backend: MockBackend | undefined;

  afterEach(() => {
    backend?.restore();
    backend = undefined;
  });

  it("answers a declared route through the real client with a contract-valid body", async () => {
    backend = mockBackend({ "GET /api/plots": PLOT_LIST });

    await expect(apiFetch("/api/plots")).resolves.toEqual(PLOT_LIST);
    expect(backend.callsTo("GET /api/plots")).toHaveLength(1);
  });

  it("rejects a static mock that is missing a required field when it is declared", () => {
    expect(() => mockBackend({ "GET /api/plots": { plots: [], warnings: [] } })).toThrow(
      /GET \/api\/plots[\s\S]*required property[\s\S]*'count'/,
    );
  });

  it("rejects a static mock whose field has the wrong type", () => {
    expect(() => mockBackend({ "GET /api/plots": { ...PLOT_LIST, count: "zero" } })).toThrow(
      /\/count must be integer/,
    );
  });

  it("rejects a route the backend does not have", () => {
    expect(() => mockBackend({ "GET /api/definitely-not-a-route": {} })).toThrow(
      /not an endpoint of the backend/,
    );
  });

  it("fails a call the test did not declare", async () => {
    backend = mockBackend({ "GET /api/plots": PLOT_LIST });

    await expect(fetch("/api/version")).rejects.toThrow(/unmocked call GET \/api\/version/);
  });

  it("fails a call to an endpoint the backend does not have", async () => {
    backend = mockBackend({ "GET /api/plots": PLOT_LIST });

    await expect(fetch("/api/plots-legacy")).rejects.toThrow(/not an endpoint of the backend/);
  });

  it("rejects a request body the backend would refuse", async () => {
    backend = mockBackend({ "POST /api/plots/run": PLOT_RUN });

    await expect(postJson("/api/plots/run", { run_id: "r1" })).rejects.toThrow(
      /body the backend would reject[\s\S]*required property 'plot_id'/,
    );
    const ok = await postJson("/api/plots/run", { plot_id: "plot-a" });
    expect(ok.status).toBe(200);
    expect(backend.callsTo("POST /api/plots/run")[0]?.body).toEqual({ plot_id: "plot-a" });
  });

  it("checks what a function handler returns on every call", async () => {
    backend = mockBackend({
      "POST /api/plots/run": (req) => ({
        ...PLOT_RUN,
        status: (req.body as { plot_id: string }).plot_id,
      }),
    });

    await expect(postJson("/api/plots/run", { plot_id: "fine" })).resolves.toMatchObject({
      status: 200,
    });
    backend.restore();

    backend = mockBackend({ "POST /api/plots/run": () => ({ ...PLOT_RUN, status: 42 }) });
    await expect(postJson("/api/plots/run", { plot_id: "x" })).rejects.toThrow(
      /\/status must be string/,
    );
  });

  it("matches a path-template route and answers explicit statuses", async () => {
    backend = mockBackend({ "DELETE /api/plots/{plot_id}": reply(204) });

    const response = await fetch("/api/plots/plot%20one", { method: "DELETE" });

    expect(response.status).toBe(204);
    expect(backend.callsTo("DELETE /api/plots/{plot_id}")[0]?.path).toBe("/api/plots/plot%20one");
  });

  it("prefers an exact concrete route over a template route for the same endpoint", async () => {
    backend = mockBackend({
      "DELETE /api/plots/{plot_id}": reply(204),
      "DELETE /api/plots/locked": reply(409, { detail: "locked" }),
    });

    expect((await fetch("/api/plots/locked", { method: "DELETE" })).status).toBe(409);
    expect((await fetch("/api/plots/other", { method: "DELETE" })).status).toBe(204);
  });

  it("records the requested URL with its query and exposes the raw fetch spy", async () => {
    backend = mockBackend({ "GET /api/plots": PLOT_LIST });

    await apiFetch("/api/plots?workflow_id=main");

    expect(backend.fetch).toHaveBeenCalledTimes(1);
    expect(backend.calls[0]?.url).toBe("/api/plots?workflow_id=main");
    expect(backend.calls[0]?.query.get("workflow_id")).toBe("main");
  });

  it("passes error replies through without schema checks so the client sees the status", async () => {
    backend = mockBackend({ "GET /api/plots": reply(404, { detail: "no project open" }) });

    await expect(apiFetch("/api/plots")).rejects.toMatchObject({ status: 404 });
  });

  it("puts the previous fetch back on restore", () => {
    const before = globalThis.fetch;
    const local = mockBackend({ "GET /api/plots": PLOT_LIST });
    expect(globalThis.fetch).not.toBe(before);

    local.restore();

    expect(globalThis.fetch).toBe(before);
  });

  it("names the violation with its own error type", () => {
    let caught: unknown;
    try {
      mockBackend({ "GET /api/plots": {} });
    } catch (error) {
      caught = error;
    }
    expect(caught).toBeInstanceOf(ContractViolation);
  });
});

describe("OpenAPI contract snapshot", () => {
  it("resolves concrete paths to their templates, preferring literal segments", () => {
    const contract = loadContract();

    expect(contract.resolve("DELETE", "/api/plots/plot-a")?.key).toBe(
      "DELETE /api/plots/{plot_id}",
    );
    expect(contract.resolve("POST", "/api/plots/run")?.key).toBe("POST /api/plots/run");
    expect(contract.resolve("GET", "/api/plots?workflow_id=main")?.key).toBe("GET /api/plots");
  });

  it("checks a mock body directly for mocks that do not go through fetch", () => {
    expect(() => checkMockBody("GET /api/plots", PLOT_LIST)).not.toThrow();
    expect(() => checkMockBody("GET /api/plots", { count: 1.5, plots: [] })).toThrow(
      /count must be integer/,
    );
  });
});
