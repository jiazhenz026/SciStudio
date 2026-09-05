/**
 * The panel API client — ADR-054 D-020's routes, pinned by path and by key.
 *
 * This file exists because of a defect it would have caught. ADR-054 renamed
 * the subsystem and the backend's `PanelSpecModel`, `PanelChoiceModel` and
 * `PanelChoiceRequest` went from `previewer_id` to `panel_id` with it; the
 * client and the Panels tab did not follow, and nothing failed, because every
 * frontend fixture was hand-written with the *old* key. A rename across a wire
 * is exactly the break neither side can see until runtime, so the request paths
 * and the field names are asserted here rather than assumed.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

import { dataApi } from "../data";

interface Call {
  url: string;
  init?: RequestInit;
}

function mockFetch(body: unknown = {}): Call[] {
  const calls: Call[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init?: RequestInit) => {
      calls.push({ url, init });
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve(body),
      } as unknown as Response);
    }),
  );
  return calls;
}

function sentBody(call: Call): Record<string, unknown> {
  return JSON.parse(String(call.init?.body)) as Record<string, unknown>;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("the per-type choice write (#2049, FR-049)", () => {
  it("names the panel with `panel_id`, the key the route requires", async () => {
    const calls = mockFetch({ choices: [] });

    await dataApi.setPanelChoice("Spectrum", "pkg.spectrum.plot", "user");

    expect(calls[0].url).toContain("/api/panels/choices/Spectrum");
    expect(calls[0].init?.method).toBe("PUT");
    expect(sentBody(calls[0])).toEqual({ panel_id: "pkg.spectrum.plot", scope: "user" });
  });
});

describe("the three editing routes (T-010, FR-024 to FR-029)", () => {
  it("reads a panel's source by id", async () => {
    const calls = mockFetch({ panel_id: "core.plot.basic" });

    await dataApi.readPanelSource("core.plot.basic");

    expect(calls[0].url).toBe("/api/panels/core.plot.basic/source");
    expect(calls[0].init?.method ?? "GET").toBe("GET");
  });

  it("PUTs the document, and asks nothing about where it should land", async () => {
    // FR-025: the system does not ask the person where to save. The body
    // carries the document and nothing that could express a destination.
    const calls = mockFetch({ panel_id: "core.plot.basic", tier: "project", copied: true });

    await dataApi.savePanelSource("core.plot.basic", "<!doctype html>\n");

    expect(calls[0].url).toBe("/api/panels/core.plot.basic/source");
    expect(calls[0].init?.method).toBe("PUT");
    expect(sentBody(calls[0])).toEqual({ source: "<!doctype html>\n", declaration: null });
  });

  it("reverts by deleting the override, not the panel", async () => {
    const calls = mockFetch({ panel_id: "core.plot.basic", restored_tier: "core" });

    await dataApi.revertPanelOverride("core.plot.basic");

    expect(calls[0].url).toBe("/api/panels/core.plot.basic/override");
    expect(calls[0].init?.method).toBe("DELETE");
  });

  it("escapes a panel id rather than pasting it into the path", async () => {
    const calls = mockFetch({});

    await dataApi.readPanelSource("../../etc/passwd");

    expect(calls[0].url).toBe("/api/panels/..%2F..%2Fetc%2Fpasswd/source");
  });
});
