/**
 * #1915: native file/directory dialogs default to the active project root.
 *
 * The `preferHome` flag is the only per-caller opt-out (create/open project and
 * the diagnostic export). These tests pin the request body the helpers send so
 * the exclusion contract can't silently regress.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

import { filesystemApi } from "../filesystem";

function mockFetchOk(): { url: string; init: RequestInit }[] {
  const calls: { url: string; init: RequestInit }[] = [];
  const mock = vi.fn((url: string, init: RequestInit) => {
    calls.push({ url, init });
    return Promise.resolve({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ paths: [] }),
    } as unknown as Response);
  });
  vi.stubGlobal("fetch", mock);
  return calls;
}

const bodyOf = (calls: { init: RequestInit }[]) => JSON.parse(calls[0].init.body as string);

describe("filesystemApi native-dialog prefer_home (#1915)", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("openNativeDialog omits prefer_home by default (project-scope)", async () => {
    const calls = mockFetchOk();
    await filesystemApi.openNativeDialog("directory");
    const body = bodyOf(calls);
    expect(body.mode).toBe("directory");
    expect(body.prefer_home).toBeUndefined();
  });

  it("openNativeDialog forwards prefer_home=true for excluded dialogs", async () => {
    const calls = mockFetchOk();
    await filesystemApi.openNativeDialog("directory", undefined, true);
    expect(bodyOf(calls).prefer_home).toBe(true);
  });

  it("openNativeSaveDialog forwards prefer_home", async () => {
    const calls = mockFetchOk();
    await filesystemApi.openNativeSaveDialog({ defaultFilename: "x.zip", preferHome: true });
    const body = bodyOf(calls);
    expect(body.mode).toBe("save_file");
    expect(body.prefer_home).toBe(true);
  });

  it("openNativeSaveDialog omits prefer_home by default (project-scope)", async () => {
    const calls = mockFetchOk();
    await filesystemApi.openNativeSaveDialog({ defaultFilename: "x.zip" });
    expect(bodyOf(calls).prefer_home).toBeUndefined();
  });
});
