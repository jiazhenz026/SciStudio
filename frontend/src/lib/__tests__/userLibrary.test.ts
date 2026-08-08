// ADR-053 §4 — the user library client and its FR-031 existence probe.

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "../api";
import { probeUserLibraryFileExistence } from "../fileExistence";

const fetchMock = vi.fn();

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function ok(body: unknown) {
  return {
    ok: true,
    status: 200,
    json: async () => body,
  } as unknown as Response;
}

function err(status: number, detail: string) {
  return {
    ok: false,
    status,
    statusText: detail,
    json: async () => ({ detail }),
  } as unknown as Response;
}

describe("putUserLibraryFile", () => {
  it("names the target and filename in the query and defaults overwrite to false", async () => {
    fetchMock.mockResolvedValue(ok({ target: "blocks", filename: "n.py", kind: "created" }));
    await api.putUserLibraryFile("blocks", "n.py", "print(1)\n");

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/user-library/file?target=blocks&filename=n.py");
    expect(init.method).toBe("PUT");
    // FR-008: overwriting is an explicit opt-in, never a client default.
    // FR-017: so is consuming a project file — a caller naming no source is
    // creating a file rather than promoting one, and nothing is removed.
    expect(JSON.parse(init.body as string)).toEqual({
      content: "print(1)\n",
      overwrite: false,
      move_from: null,
    });
  });

  it("names the project file to consume when promoting (FR-017)", async () => {
    fetchMock.mockResolvedValue(ok({ target: "types", filename: "s.py", kind: "created" }));
    await api.putUserLibraryFile("types", "s.py", "x", {
      moveFrom: { projectId: "proj-1", path: "types/s.py" },
    });

    const [, init] = fetchMock.mock.calls[0];
    // Snake case on the wire, because that is the request model's shape.
    expect(JSON.parse(init.body as string).move_from).toEqual({
      project_id: "proj-1",
      path: "types/s.py",
    });
  });

  it("passes overwrite through when the user opted in", async () => {
    fetchMock.mockResolvedValue(ok({ target: "types", filename: "t.py", kind: "modified" }));
    await api.putUserLibraryFile("types", "t.py", "x", { overwrite: true });
    expect(JSON.parse(fetchMock.mock.calls[0][1].body as string).overwrite).toBe(true);
  });

  it("surfaces the 409 collision with the server's own detail", async () => {
    fetchMock.mockResolvedValue(
      err(409, "n.py already exists in the user library blocks directory."),
    );
    await expect(api.putUserLibraryFile("blocks", "n.py", "x")).rejects.toMatchObject({
      status: 409,
      message: expect.stringContaining("already exists"),
    });
  });
});

describe("probeUserLibraryFileExistence — FR-031", () => {
  it("reads 200 as exists", async () => {
    fetchMock.mockResolvedValue(ok({ content: "x" }));
    await expect(probeUserLibraryFileExistence("blocks", "n.py")).resolves.toEqual({
      kind: "exists",
    });
    expect(fetchMock.mock.calls[0][0]).toBe("/api/user-library/file?target=blocks&filename=n.py");
  });

  it("reads 404 as missing — the only status that means safe to create", async () => {
    fetchMock.mockResolvedValue(err(404, "File not found"));
    await expect(probeUserLibraryFileExistence("types", "t.py")).resolves.toEqual({
      kind: "missing",
    });
  });

  it.each([403, 415, 500])("reads %d as unknown rather than guessing", async (status) => {
    fetchMock.mockResolvedValue(err(status, "nope"));
    const result = await probeUserLibraryFileExistence("blocks", "n.py");
    expect(result.kind).toBe("unknown");
  });
});
