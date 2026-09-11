// ADR-053 §4 — the user library client and its FR-031 existence probe.
// The fake backend checks every body against the backend contract (#2297).

import { afterEach, describe, expect, it } from "vitest";

import {
  mockBackend,
  reply,
  type MockBackend,
  type MockHandler,
} from "../../__tests__/contract/mockBackend";
import { api } from "../api";
import { probeUserLibraryFileExistence } from "../fileExistence";

const FILE_ROUTE = "/api/user-library/file";

let backend: MockBackend | undefined;

function serve(method: "GET" | "PUT", handler: MockHandler): MockBackend {
  backend = mockBackend({ [`${method} ${FILE_ROUTE}`]: handler });
  return backend;
}

afterEach(() => {
  backend?.restore();
  backend = undefined;
});

function written(target: string, filename: string, kind: "created" | "modified") {
  return {
    target,
    filename,
    path: `/home/ana/.scistudio/library/${target}/${filename}`,
    mtime: 1_760_000_000.5,
    size: 9,
    kind,
    registries_refreshed: true,
    moved_from: null,
    move_error: null,
  };
}

const EXISTING_FILE = {
  target: "blocks",
  filename: "n.py",
  path: "/home/ana/.scistudio/library/blocks/n.py",
  content: "x",
  encoding: "utf-8",
  mtime: 1_760_000_000.5,
  size: 1,
};

describe("putUserLibraryFile", () => {
  it("names the target and filename in the query and defaults overwrite to false", async () => {
    const b = serve("PUT", written("blocks", "n.py", "created"));
    await api.putUserLibraryFile("blocks", "n.py", "print(1)\n");

    expect(b.calls[0]?.url).toBe("/api/user-library/file?target=blocks&filename=n.py");
    expect(b.calls[0]?.method).toBe("PUT");
    // FR-008: overwriting is an explicit opt-in, never a client default.
    // FR-017: so is consuming a project file — a caller naming no source is
    // creating a file rather than promoting one, and nothing is removed.
    expect(b.calls[0]?.body).toEqual({
      content: "print(1)\n",
      overwrite: false,
      move_from: null,
    });
  });

  it("names the project file to consume when promoting (FR-017)", async () => {
    const b = serve("PUT", written("types", "s.py", "created"));
    await api.putUserLibraryFile("types", "s.py", "x", {
      moveFrom: { projectId: "proj-1", path: "types/s.py" },
    });

    // Snake case on the wire, because that is the request model's shape.
    expect((b.calls[0]?.body as { move_from: unknown }).move_from).toEqual({
      project_id: "proj-1",
      path: "types/s.py",
    });
  });

  it("passes overwrite through when the user opted in", async () => {
    const b = serve("PUT", written("types", "t.py", "modified"));
    await api.putUserLibraryFile("types", "t.py", "x", { overwrite: true });
    expect((b.calls[0]?.body as { overwrite: boolean }).overwrite).toBe(true);
  });

  it("surfaces the 409 collision with the server's own detail", async () => {
    serve(
      "PUT",
      reply(409, { detail: "n.py already exists in the user library blocks directory." }),
    );
    await expect(api.putUserLibraryFile("blocks", "n.py", "x")).rejects.toMatchObject({
      status: 409,
      message: expect.stringContaining("already exists"),
    });
  });
});

describe("probeUserLibraryFileExistence — FR-031", () => {
  it("reads 200 as exists", async () => {
    const b = serve("GET", EXISTING_FILE);
    await expect(probeUserLibraryFileExistence("blocks", "n.py")).resolves.toEqual({
      kind: "exists",
    });
    expect(b.calls[0]?.url).toBe("/api/user-library/file?target=blocks&filename=n.py");
  });

  it("reads 404 as missing — the only status that means safe to create", async () => {
    serve("GET", reply(404, { detail: "File not found" }));
    await expect(probeUserLibraryFileExistence("types", "t.py")).resolves.toEqual({
      kind: "missing",
    });
  });

  it.each([403, 415, 500])("reads %d as unknown rather than guessing", async (status) => {
    serve("GET", reply(status, { detail: "nope" }));
    const result = await probeUserLibraryFileExistence("blocks", "n.py");
    expect(result.kind).toBe("unknown");
  });
});
