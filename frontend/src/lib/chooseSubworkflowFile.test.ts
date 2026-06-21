// ADR-044 FR-011 (US5) + US6 AS2 — shared choose/import-subworkflow flow tests.
//
// The flow:
//   1. native file dialog → first path (empty / cancelled aborts quietly),
//   2. POST /api/workflows/import-subworkflow → { ref_path, resolved_ports },
//   3. setNodeRef(nodeId, ref_path) — top-level config.ref.path repoint,
//   4. setNodeResolvedPorts(nodeId, resolved_ports) — un-break + refresh handles,
//   5. setLastError on failure.

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { ImportSubworkflowResponse } from "../types/api";

const apiMocks = vi.hoisted(() => ({
  openNativeDialog: vi.fn(),
  importSubworkflow: vi.fn(),
}));

vi.mock("./api", () => ({
  api: {
    openNativeDialog: apiMocks.openNativeDialog,
    importSubworkflow: apiMocks.importSubworkflow,
  },
}));

import { chooseSubworkflowFile } from "./chooseSubworkflowFile";

function makeResponse(): ImportSubworkflowResponse {
  return {
    ref_path: "subworkflows/imported.swf.yaml",
    resolved_ports: {
      inputs: [{ name: "raw_in", accepted_types: ["DataObject"] }],
      outputs: [{ name: "report", accepted_types: ["DataObject"] }],
      broken: false,
      ref_path: "subworkflows/imported.swf.yaml",
    },
  };
}

function makeDeps() {
  return {
    setNodeRef: vi.fn(),
    setNodeResolvedPorts: vi.fn(),
    setLastError: vi.fn(),
  };
}

beforeEach(() => {
  apiMocks.openNativeDialog.mockReset();
  apiMocks.importSubworkflow.mockReset();
});

afterEach(() => vi.clearAllMocks());

describe("chooseSubworkflowFile", () => {
  it("imports the picked file and repoints + refreshes the node", async () => {
    const response = makeResponse();
    apiMocks.openNativeDialog.mockResolvedValue({ paths: ["/abs/external/imported.swf.yaml"] });
    apiMocks.importSubworkflow.mockResolvedValue(response);
    const deps = makeDeps();

    const result = await chooseSubworkflowFile("sw1", deps);

    expect(apiMocks.openNativeDialog).toHaveBeenCalledWith("file");
    expect(apiMocks.importSubworkflow).toHaveBeenCalledWith("/abs/external/imported.swf.yaml");
    expect(deps.setNodeRef).toHaveBeenCalledWith("sw1", response.ref_path);
    expect(deps.setNodeResolvedPorts).toHaveBeenCalledWith("sw1", response.resolved_ports);
    expect(deps.setLastError).toHaveBeenCalledWith(null);
    expect(result).toBe(response.ref_path);
  });

  it("aborts quietly when the dialog returns no path (cancelled)", async () => {
    apiMocks.openNativeDialog.mockResolvedValue({ paths: [] });
    const deps = makeDeps();

    const result = await chooseSubworkflowFile("sw1", deps);

    expect(apiMocks.importSubworkflow).not.toHaveBeenCalled();
    expect(deps.setNodeRef).not.toHaveBeenCalled();
    expect(deps.setNodeResolvedPorts).not.toHaveBeenCalled();
    expect(deps.setLastError).not.toHaveBeenCalled();
    expect(result).toBeNull();
  });

  it("surfaces an import failure via setLastError and writes nothing", async () => {
    apiMocks.openNativeDialog.mockResolvedValue({ paths: ["/abs/external/bad.swf.yaml"] });
    apiMocks.importSubworkflow.mockRejectedValue(new Error("copy failed"));
    const deps = makeDeps();

    const result = await chooseSubworkflowFile("sw1", deps);

    expect(deps.setNodeRef).not.toHaveBeenCalled();
    expect(deps.setNodeResolvedPorts).not.toHaveBeenCalled();
    expect(deps.setLastError).toHaveBeenCalledWith("copy failed");
    expect(result).toBeNull();
  });

  it("surfaces a dialog failure via setLastError", async () => {
    apiMocks.openNativeDialog.mockRejectedValue(new Error("dialog unavailable"));
    const deps = makeDeps();

    const result = await chooseSubworkflowFile("sw1", deps);

    expect(apiMocks.importSubworkflow).not.toHaveBeenCalled();
    expect(deps.setLastError).toHaveBeenCalledWith("dialog unavailable");
    expect(result).toBeNull();
  });
});
