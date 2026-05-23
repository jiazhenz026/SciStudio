/**
 * ADR-036 audit 2026-05-14 P1 #2 — file-existence probe regression tests.
 *
 * These cover the fix for the "New custom block" / "New note" silent
 * overwrite bug: those flows now call ``probeProjectFileExistence`` before
 * PUT and refuse to clobber an existing file.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "./api";
import type * as ApiModule from "./api";

vi.mock("./api", async () => {
  const actual = await vi.importActual<typeof ApiModule>("./api");
  return {
    ...actual,
    api: {
      ...actual.api,
      getProjectFile: vi.fn(),
    },
  };
});

import { api } from "./api";
import { probeProjectFileExistence } from "./fileExistence";

const getProjectFileMock = vi.mocked(api.getProjectFile);

beforeEach(() => {
  getProjectFileMock.mockReset();
});

afterEach(() => {
  vi.clearAllMocks();
});

describe("probeProjectFileExistence (ADR-036 audit P1 #2)", () => {
  it("returns 'exists' when GET returns 200", async () => {
    getProjectFileMock.mockResolvedValueOnce({
      content: "x = 1\n",
      mtime: 1,
      size: 6,
      encoding: "utf-8",
    });
    const result = await probeProjectFileExistence("p1", "blocks/dup.py");
    expect(result.kind).toBe("exists");
    expect(getProjectFileMock).toHaveBeenCalledWith("p1", "blocks/dup.py");
  });

  it("returns 'missing' when GET returns 404", async () => {
    getProjectFileMock.mockRejectedValueOnce(new ApiError("File not found", 404));
    const result = await probeProjectFileExistence("p1", "blocks/new.py");
    expect(result.kind).toBe("missing");
  });

  it("returns 'unknown' on non-404 ApiError so the caller surfaces it", async () => {
    getProjectFileMock.mockRejectedValueOnce(new ApiError("boom", 500));
    const result = await probeProjectFileExistence("p1", "blocks/x.py");
    expect(result.kind).toBe("unknown");
    if (result.kind !== "unknown") throw new Error("expected unknown");
    expect(result.message).toContain("boom");
  });

  it("returns 'unknown' on a network/Error rejection", async () => {
    getProjectFileMock.mockRejectedValueOnce(new Error("offline"));
    const result = await probeProjectFileExistence("p1", "blocks/x.py");
    expect(result.kind).toBe("unknown");
    if (result.kind !== "unknown") throw new Error("expected unknown");
    expect(result.message).toContain("offline");
  });
});
