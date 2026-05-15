/**
 * D39-2.4b tests for `ConflictResolveView.tsx` and `parseConflictRegions`
 * (the pure parser in `ConflictMarkerDecoration.ts`).
 */
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("../../../lib/api", async () => {
  const actual = await vi.importActual<typeof import("../../../lib/api")>(
    "../../../lib/api",
  );
  return {
    ...actual,
    api: {
      gitMergeStageFile: vi.fn(),
    },
  };
});

import { ConflictResolveView } from "../ConflictResolveView";
import {
  parseConflictRegions,
  resolveRegionText,
} from "../ConflictMarkerDecoration";
import { api } from "../../../lib/api";

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("parseConflictRegions (pure helper)", () => {
  it("returns [] for empty content", () => {
    expect(parseConflictRegions("")).toEqual([]);
  });

  it("returns [] when no markers are present", () => {
    expect(parseConflictRegions("hello\nworld\n")).toEqual([]);
  });

  it("parses a single 2-way conflict region", () => {
    const content = [
      "line0",
      "<<<<<<< HEAD",
      "ours",
      "=======",
      "theirs",
      ">>>>>>> feature-x",
      "after",
    ].join("\n");
    const regions = parseConflictRegions(content);
    expect(regions).toHaveLength(1);
    expect(regions[0]).toMatchObject({
      startLine: 2,
      currentEndLine: 4,
      baseEndLine: null,
      incomingEndLine: 6,
      currentLabel: "HEAD",
      incomingLabel: "feature-x",
    });
  });

  it("parses two consecutive 2-way regions", () => {
    const content = [
      "<<<<<<< HEAD",
      "a1",
      "=======",
      "a2",
      ">>>>>>> source",
      "middle",
      "<<<<<<< HEAD",
      "b1",
      "=======",
      "b2",
      ">>>>>>> source",
    ].join("\n");
    const regions = parseConflictRegions(content);
    expect(regions).toHaveLength(2);
    expect(regions[0].startLine).toBe(1);
    expect(regions[1].startLine).toBe(7);
  });

  it("parses a diff3-style region (records baseEndLine)", () => {
    const content = [
      "<<<<<<< HEAD",
      "ours",
      "||||||| base",
      "common",
      "=======",
      "theirs",
      ">>>>>>> source",
    ].join("\n");
    const regions = parseConflictRegions(content);
    expect(regions).toHaveLength(1);
    expect(regions[0].currentEndLine).toBe(3);
    expect(regions[0].baseEndLine).toBe(5);
    expect(regions[0].incomingEndLine).toBe(7);
  });

  it("falls back to default labels when marker has no label", () => {
    const content = ["<<<<<<<", "x", "=======", "y", ">>>>>>>", ""].join("\n");
    const regions = parseConflictRegions(content);
    expect(regions[0].currentLabel).toBe("current");
    expect(regions[0].incomingLabel).toBe("incoming");
  });

  it("discards an unclosed region at EOF", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const content = ["<<<<<<< HEAD", "ours", "======="].join("\n");
    expect(parseConflictRegions(content)).toEqual([]);
    warn.mockRestore();
  });

  it("strips trailing CR (Windows CRLF) from labels", () => {
    const content = ["<<<<<<< HEAD\r", "x", "=======", "y", ">>>>>>> src\r"].join(
      "\n",
    );
    const regions = parseConflictRegions(content);
    expect(regions[0].currentLabel).toBe("HEAD");
    expect(regions[0].incomingLabel).toBe("src");
  });
});

describe("resolveRegionText (text splice)", () => {
  const content = [
    "before",
    "<<<<<<< HEAD",
    "ours-1",
    "ours-2",
    "=======",
    "theirs-1",
    ">>>>>>> feature-x",
    "after",
  ].join("\n");
  const region = parseConflictRegions(content)[0];

  it("accept_current → keeps 'ours' section", () => {
    const out = resolveRegionText(content, region, { type: "accept_current" });
    expect(out.split("\n")).toEqual([
      "before",
      "ours-1",
      "ours-2",
      "after",
    ]);
  });

  it("accept_incoming → keeps 'theirs' section", () => {
    const out = resolveRegionText(content, region, { type: "accept_incoming" });
    expect(out.split("\n")).toEqual(["before", "theirs-1", "after"]);
  });

  it("accept_both → concatenates current then incoming", () => {
    const out = resolveRegionText(content, region, { type: "accept_both" });
    expect(out.split("\n")).toEqual([
      "before",
      "ours-1",
      "ours-2",
      "theirs-1",
      "after",
    ]);
  });

  it("manual_edit → returns text unchanged", () => {
    const out = resolveRegionText(content, region, { type: "manual_edit" });
    expect(out).toBe(content);
  });
});

describe("ConflictResolveView (D39-2.4b)", () => {
  const noop = async () => {};
  it("renders the empty-state when no conflicted files", () => {
    render(
      <ConflictResolveView
        conflictedFiles={[]}
        onOpenFile={() => {}}
        onResolveAll={noop}
        onAbort={noop}
      />,
    );
    expect(screen.getByText(/No conflicted files/i)).toBeDefined();
  });

  it("renders each conflicted file with Open + Mark Resolved buttons", () => {
    render(
      <ConflictResolveView
        conflictedFiles={["src/a.py", "src/b.py"]}
        onOpenFile={() => {}}
        onResolveAll={noop}
        onAbort={noop}
      />,
    );
    expect(screen.getByTestId("conflict-row-src/a.py")).toBeDefined();
    expect(screen.getByTestId("conflict-row-src/b.py")).toBeDefined();
    expect(screen.getByTestId("conflict-open-src/a.py")).toBeDefined();
    expect(screen.getByTestId("conflict-mark-resolved-src/b.py")).toBeDefined();
  });

  it("Open in editor button calls onOpenFile with the file path", async () => {
    const user = userEvent.setup();
    const onOpenFile = vi.fn();
    render(
      <ConflictResolveView
        conflictedFiles={["src/a.py"]}
        onOpenFile={onOpenFile}
        onResolveAll={noop}
        onAbort={noop}
      />,
    );
    await user.click(screen.getByTestId("conflict-open-src/a.py"));
    expect(onOpenFile).toHaveBeenCalledWith("src/a.py");
  });

  it("Mark Resolved button calls gitMergeStageFile + flips status badge", async () => {
    const user = userEvent.setup();
    (api.gitMergeStageFile as ReturnType<typeof vi.fn>).mockResolvedValue({
      status: "ok",
    });
    render(
      <ConflictResolveView
        conflictedFiles={["src/a.py"]}
        onOpenFile={() => {}}
        onResolveAll={noop}
        onAbort={noop}
      />,
    );
    expect(screen.getByTestId("conflict-status-badge-src/a.py").textContent).toBe(
      "Unresolved",
    );
    await user.click(screen.getByTestId("conflict-mark-resolved-src/a.py"));
    await waitFor(() => {
      expect(api.gitMergeStageFile).toHaveBeenCalledWith("src/a.py");
    });
    await waitFor(() => {
      expect(
        screen.getByTestId("conflict-status-badge-src/a.py").textContent,
      ).toBe("Resolved");
    });
  });

  it("Complete Merge is disabled until all files resolved", async () => {
    const user = userEvent.setup();
    (api.gitMergeStageFile as ReturnType<typeof vi.fn>).mockResolvedValue({
      status: "ok",
    });
    const onResolveAll = vi.fn().mockResolvedValue(undefined);
    render(
      <ConflictResolveView
        conflictedFiles={["a.py", "b.py"]}
        onOpenFile={() => {}}
        onResolveAll={onResolveAll}
        onAbort={noop}
      />,
    );
    const complete = screen.getByTestId("conflict-complete-button");
    expect(complete.getAttribute("aria-disabled")).toBe("true");
    await user.click(screen.getByTestId("conflict-mark-resolved-a.py"));
    await waitFor(() => {
      expect(
        screen.getByTestId("conflict-status-badge-a.py").textContent,
      ).toBe("Resolved");
    });
    // Still disabled — only one resolved.
    expect(complete.getAttribute("aria-disabled")).toBe("true");
    await user.click(screen.getByTestId("conflict-mark-resolved-b.py"));
    await waitFor(() => {
      expect(
        screen.getByTestId("conflict-status-badge-b.py").textContent,
      ).toBe("Resolved");
    });
    // Now enabled.
    expect(complete.getAttribute("aria-disabled")).toBe("false");
    await user.click(complete);
    expect(onResolveAll).toHaveBeenCalled();
  });

  it("Abort Merge button calls onAbort", async () => {
    const user = userEvent.setup();
    const onAbort = vi.fn().mockResolvedValue(undefined);
    render(
      <ConflictResolveView
        conflictedFiles={["a.py"]}
        onOpenFile={() => {}}
        onResolveAll={noop}
        onAbort={onAbort}
      />,
    );
    await user.click(screen.getByTestId("conflict-abort-button"));
    expect(onAbort).toHaveBeenCalled();
  });
});
