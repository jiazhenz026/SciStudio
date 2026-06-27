import { afterEach, describe, expect, it, vi } from "vitest";

import { exportDiagnosticBundle, getLogBuffer, logger } from "../logger";

describe("frontend logger (#1741)", () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("buffers emitted records in the ring buffer", () => {
    logger.info("hello world", { a: 1 });
    const buffer = getLogBuffer();
    const match = buffer.find((r) => r.message === "hello world");
    expect(match).toBeDefined();
    expect(match?.level).toBe("info");
    expect(match?.context).toEqual({ a: 1 });
  });

  it("does not reflux debug/info below the threshold", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true });
    vi.stubGlobal("fetch", fetchMock);
    vi.useFakeTimers();
    logger.debug("quiet");
    logger.info("also quiet");
    await vi.advanceTimersByTimeAsync(5000);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("refluxes warn+ to the backend client-logs endpoint", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true });
    vi.stubGlobal("fetch", fetchMock);
    vi.useFakeTimers();
    logger.error("boom");
    await vi.advanceTimersByTimeAsync(5000);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/client-logs");
    expect(init.method).toBe("POST");
    const body = JSON.parse(init.body as string);
    expect(body.records.some((r: { message: string }) => r.message === "boom")).toBe(true);
  });

  // #1760 bug2: native-dialog-first export. fetch is routed by URL so a test can
  // configure the native save dialog and the bundle endpoint independently.
  function routedFetch(handlers: { dialog?: unknown; bundle?: unknown }) {
    const calls: { url: string; init?: { body?: string } }[] = [];
    const mock = vi.fn((url: string, init?: { body?: string }) => {
      calls.push({ url, init });
      if (url.includes("/api/filesystem/native-dialog")) {
        return handlers.dialog ?? Promise.reject(new Error("no dialog handler"));
      }
      if (url.includes("/api/diagnostics/bundle")) {
        return handlers.bundle ?? Promise.reject(new Error("no bundle handler"));
      }
      return Promise.resolve({ ok: true });
    });
    return { mock, calls };
  }

  function trackDownloads(): string[] {
    const downloads: string[] = [];
    vi.stubGlobal("URL", { createObjectURL: vi.fn(() => "blob:mock"), revokeObjectURL: vi.fn() });
    const realCreate = document.createElement.bind(document);
    vi.spyOn(document, "createElement").mockImplementation((tag: string) => {
      const el = realCreate(tag);
      if (tag === "a") {
        (el as HTMLAnchorElement).click = () => downloads.push((el as HTMLAnchorElement).download);
      }
      return el;
    });
    return downloads;
  }

  it("writes the bundle to the native-dialog-chosen path without a browser download", async () => {
    logger.error("record");
    const { mock, calls } = routedFetch({
      dialog: Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ paths: ["/home/u/report.zip"], available: true }),
      }),
      bundle: Promise.resolve({ ok: true, json: () => Promise.resolve({ status: "written" }) }),
    });
    vi.stubGlobal("fetch", mock);
    const downloads = trackDownloads();

    await exportDiagnosticBundle();

    // Native save dialog is requested FIRST, then the bundle is written to the path.
    expect(calls[0].url).toContain("/api/filesystem/native-dialog");
    const bundleCall = calls.find((c) => c.url.includes("/api/diagnostics/bundle"));
    expect(bundleCall).toBeDefined();
    expect(JSON.parse(bundleCall!.init!.body as string).path).toBe("/home/u/report.zip");
    // No browser download when the native dialog handled the save.
    expect(downloads).toEqual([]);
  });

  it("does nothing extra when the user cancels the native save dialog", async () => {
    logger.error("record");
    const { mock, calls } = routedFetch({
      // available:true + empty paths == user cancelled.
      dialog: Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ paths: [], available: true }),
      }),
    });
    vi.stubGlobal("fetch", mock);
    const downloads = trackDownloads();

    await exportDiagnosticBundle();

    // No bundle request and no browser download — the cancel is respected.
    expect(calls.some((c) => c.url.includes("/api/diagnostics/bundle"))).toBe(false);
    expect(downloads).toEqual([]);
  });

  it("falls back to a single browser zip download when the native dialog is unavailable", async () => {
    const zipBlob = new Blob(["PK"], { type: "application/zip" });
    const { mock } = routedFetch({
      // available:false == platform native dialog could not run (browser context).
      dialog: Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ paths: [], available: false }),
      }),
      bundle: Promise.resolve({ ok: true, blob: () => Promise.resolve(zipBlob) }),
    });
    vi.stubGlobal("fetch", mock);
    const downloads = trackDownloads();

    await exportDiagnosticBundle();

    expect(downloads).toEqual(["scistudio-diagnostics.zip"]);
  });

  it("dumps the ring buffer as a .log when the dialog and backend are unreachable", async () => {
    // Frontend-only records must still reach the tester when everything is offline.
    logger.error("ring-only record");
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));
    const downloads = trackDownloads();

    await exportDiagnosticBundle();

    expect(downloads).toContain("scistudio-frontend-logs.log");
  });
});
