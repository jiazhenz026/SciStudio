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

  it("dumps the ring buffer on export even when the backend is unreachable", async () => {
    // Codex P2: frontend-only records must reach the download when the backend
    // bundle cannot be fetched.
    logger.error("ring-only record");
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));
    vi.stubGlobal("URL", {
      createObjectURL: vi.fn(() => "blob:mock"),
      revokeObjectURL: vi.fn(),
    });
    const downloads: string[] = [];
    const realCreate = document.createElement.bind(document);
    vi.spyOn(document, "createElement").mockImplementation((tag: string) => {
      const el = realCreate(tag);
      if (tag === "a") {
        (el as HTMLAnchorElement).click = () => {
          downloads.push((el as HTMLAnchorElement).download);
        };
      }
      return el;
    });

    await exportDiagnosticBundle();

    expect(downloads).toContain("scistudio-frontend-logs.json");
  });
});
