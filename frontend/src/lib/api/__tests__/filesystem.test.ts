/**
 * #1915: native file/directory dialogs default to the active project root.
 *
 * The `preferHome` flag is the only per-caller opt-out (create/open project and
 * the diagnostic export). These tests pin the request body the helpers send so
 * the exclusion contract can't silently regress. The fake backend checks that
 * body against the backend's `NativeDialogRequest` too (#2297).
 */
import { afterEach, describe, expect, it } from "vitest";

import { mockBackend, type MockBackend } from "../../../__tests__/contract/mockBackend";
import { filesystemApi } from "../filesystem";

let backend: MockBackend | undefined;

function serveDialog(): MockBackend {
  backend = mockBackend({ "POST /api/filesystem/native-dialog": { paths: [] } });
  return backend;
}

const bodyOf = (b: MockBackend) => b.calls[0]?.body as Record<string, unknown>;

describe("filesystemApi native-dialog prefer_home (#1915)", () => {
  afterEach(() => {
    backend?.restore();
    backend = undefined;
  });

  it("openNativeDialog omits prefer_home by default (project-scope)", async () => {
    const b = serveDialog();
    await filesystemApi.openNativeDialog("directory");
    const body = bodyOf(b);
    expect(body.mode).toBe("directory");
    expect(body.prefer_home).toBeUndefined();
  });

  it("openNativeDialog forwards prefer_home=true for excluded dialogs", async () => {
    const b = serveDialog();
    await filesystemApi.openNativeDialog("directory", undefined, true);
    expect(bodyOf(b).prefer_home).toBe(true);
  });

  it("openNativeSaveDialog forwards prefer_home", async () => {
    const b = serveDialog();
    await filesystemApi.openNativeSaveDialog({ defaultFilename: "x.zip", preferHome: true });
    const body = bodyOf(b);
    expect(body.mode).toBe("save_file");
    expect(body.prefer_home).toBe(true);
  });

  it("openNativeSaveDialog omits prefer_home by default (project-scope)", async () => {
    const b = serveDialog();
    await filesystemApi.openNativeSaveDialog({ defaultFilename: "x.zip" });
    expect(bodyOf(b).prefer_home).toBeUndefined();
  });
});
