/**
 * #2361 — what the live markdown preview is allowed to put on screen.
 *
 * The pane renders a project's own file, so the interesting assertions are the
 * negative ones: no `<img>`, no live element from raw HTML, no anchor on a
 * target that has nowhere to go. Those are the properties that hold the policy
 * in place; the positive ones (a table is a table, a fence is a fence) only say
 * the renderer is wired up at all.
 */

import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  MARKDOWN_PREVIEW_DEBOUNCE_MS,
  MarkdownPane,
  imageLabel,
  linkPolicy,
} from "../CodeEditor.parts/MarkdownPane";

/** Render, then let the first debounce land so the document is on screen. */
function renderPane(source: string, onHide = vi.fn()) {
  const result = render(<MarkdownPane onHide={onHide} source={source} />);
  act(() => {
    vi.advanceTimersByTime(MARKDOWN_PREVIEW_DEBOUNCE_MS + 1);
  });
  return result;
}

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("linkPolicy", () => {
  it.each([
    ["https://example.org/a", "open"],
    ["http://example.org", "open"],
    ["  https://example.org  ", "open"],
    ["mailto:someone@example.org", "open"],
    ["MailTo:someone@example.org", "open"],
  ])("opens %s", (href, kind) => {
    expect(linkPolicy(href).kind).toBe(kind);
  });

  it.each<[string | undefined, string]>([
    ["notes/other.md", "a project-relative path"],
    ["/absolute/path.md", "an absolute path"],
    ["#a-heading", "a bare fragment"],
    ["javascript:alert(1)", "a script URL"],
    ["file:///etc/passwd", "a foreign scheme"],
    ["data:text/html;base64,PHNjcmlwdD4=", "a data URL"],
    [undefined, "a link with no href at all"],
  ])("keeps %s inert (%s)", (href) => {
    expect(linkPolicy(href).kind).toBe("inert");
  });

  it("trims the target it reports for an inert link", () => {
    const policy = linkPolicy("  notes/other.md  ");
    expect(policy).toEqual({ kind: "inert", target: "notes/other.md" });
  });
});

describe("imageLabel", () => {
  it("carries both the alt text and the file name when it has both", () => {
    expect(imageLabel("assets/figure-1.png", "QC summary")).toBe("QC summary — figure-1.png");
  });

  it("falls back to whichever one it has", () => {
    expect(imageLabel("assets/figure-1.png", "")).toBe("figure-1.png");
    expect(imageLabel("", "QC summary")).toBe("QC summary");
    expect(imageLabel(undefined, undefined)).toBe("image");
  });

  it("strips a query and a fragment off the file name", () => {
    expect(imageLabel("assets/figure-1.png?v=2#top", "")).toBe("figure-1.png");
  });
});

describe("MarkdownPane", () => {
  it("says an empty document is empty rather than rendering nothing", () => {
    vi.useFakeTimers();
    renderPane("   \n  \n");
    expect(screen.getByTestId("markdown-preview-empty")).toBeInTheDocument();
  });

  it("renders headings, emphasis, and a fenced block", () => {
    vi.useFakeTimers();
    const { container } = renderPane("# Title\n\nSome **bold** prose.\n\n```py\nx = 1\n```\n");
    expect(screen.getByRole("heading", { level: 1, name: "Title" })).toBeInTheDocument();
    expect(container.querySelector("strong")).toHaveTextContent("bold");
    expect(container.querySelector("pre code")).toHaveTextContent("x = 1");
  });

  it("renders a GFM table as a real table", () => {
    vi.useFakeTimers();
    const { container } = renderPane(
      ["| Sample | Reads |", "| --- | --- |", "| A | 12 |", "| B | 44 |", ""].join("\n"),
    );
    const table = container.querySelector("table");
    expect(table).not.toBeNull();
    expect(table?.querySelectorAll("thead th")).toHaveLength(2);
    expect(table?.querySelectorAll("tbody tr")).toHaveLength(2);
    expect(screen.getByText("Reads")).toBeInTheDocument();
  });

  it("renders a GFM task list with its checkbox state", () => {
    vi.useFakeTimers();
    const { container } = renderPane("- [x] normalised\n- [ ] clustered\n");
    const boxes = container.querySelectorAll("input[type='checkbox']");
    expect(boxes).toHaveLength(2);
    expect((boxes[0] as HTMLInputElement).checked).toBe(true);
    expect((boxes[1] as HTMLInputElement).checked).toBe(false);
  });

  it("opens an http(s) link outside the app with noopener,noreferrer", async () => {
    vi.useFakeTimers();
    const open = vi.fn();
    vi.stubGlobal("open", open);
    const { container } = renderPane("See [the paper](https://example.org/paper).\n");

    const anchor = container.querySelector("a[data-md-link='open']") as HTMLAnchorElement;
    expect(anchor).not.toBeNull();
    expect(anchor).toHaveTextContent("the paper");

    act(() => {
      anchor.click();
    });
    expect(open).toHaveBeenCalledWith("https://example.org/paper", "_blank", "noopener,noreferrer");
  });

  it("renders a relative link as its own text, with no anchor and no navigation", () => {
    vi.useFakeTimers();
    const { container } = renderPane("See [the notes](notes/other.md).\n");

    expect(container.querySelector("a")).toBeNull();
    const inert = container.querySelector("[data-md-link='inert']") as HTMLElement;
    expect(inert).toHaveTextContent("the notes");
    expect(inert).toHaveAttribute("title", "notes/other.md");
  });

  it("keeps a javascript: link inert too", () => {
    vi.useFakeTimers();
    const { container } = renderPane("[click](javascript:alert%281%29)\n");
    expect(container.querySelector("a")).toBeNull();
    expect(container.querySelector("[data-md-link='inert']")).toHaveTextContent("click");
  });

  it("renders an image as a marker naming the file, never as an <img>", () => {
    vi.useFakeTimers();
    const { container } = renderPane("![QC summary](assets/figure-1.png)\n");

    expect(container.querySelector("img")).toBeNull();
    const marker = container.querySelector("[data-md-image='marker']") as HTMLElement;
    expect(marker).not.toBeNull();
    expect(marker.textContent).toContain("figure-1.png");
    expect(marker.textContent).toContain("QC summary");
    expect(marker).toHaveAttribute("title", "assets/figure-1.png");
  });

  it("does not fetch a remote image either", () => {
    vi.useFakeTimers();
    const { container } = renderPane("![remote](https://example.org/tracker.png)\n");
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("[data-md-image='marker']")).toHaveAttribute(
      "title",
      "https://example.org/tracker.png",
    );
  });

  it("never turns raw HTML in the document into a live element", () => {
    vi.useFakeTimers();
    const source = [
      "<script>alert(1)</script>",
      "",
      '<img src="x" onerror="alert(2)">',
      "",
      '<div onclick="alert(3)">hello</div>',
      "",
      '<a href="https://example.org">raw anchor</a>',
      "",
    ].join("\n");
    const { container } = renderPane(source);

    expect(container.querySelector("script")).toBeNull();
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("div[onclick]")).toBeNull();
    expect(container.querySelector("a")).toBeNull();
    // The markup survives as text, so nothing the file says is lost.
    expect(container.textContent).toContain("alert(1)");
  });

  it("holds the previous render on screen until the debounce lands", () => {
    vi.useFakeTimers();
    const { rerender, container } = renderPane("# First\n");
    expect(container.textContent).toContain("First");

    rerender(<MarkdownPane onHide={vi.fn()} source={"# Second\n"} />);
    act(() => {
      vi.advanceTimersByTime(MARKDOWN_PREVIEW_DEBOUNCE_MS - 1);
    });
    expect(container.textContent).toContain("First");
    expect(container.textContent).not.toContain("Second");

    act(() => {
      vi.advanceTimersByTime(2);
    });
    expect(container.textContent).toContain("Second");
    expect(container.textContent).not.toContain("First");
  });

  it("reparses once for a burst of keystrokes", () => {
    vi.useFakeTimers();
    const { rerender, container } = renderPane("a");
    for (const source of ["ab", "abc", "abcd", "abcde"]) {
      rerender(<MarkdownPane onHide={vi.fn()} source={source} />);
      act(() => {
        vi.advanceTimersByTime(10);
      });
    }
    // Still the first render: none of the intermediate values ever settled.
    expect(container.textContent).toContain("a");
    expect(container.textContent).not.toContain("abcde");

    act(() => {
      vi.advanceTimersByTime(MARKDOWN_PREVIEW_DEBOUNCE_MS + 1);
    });
    expect(container.textContent).toContain("abcde");
  });

  it("calls onHide from the Hide control", () => {
    vi.useFakeTimers();
    const onHide = vi.fn();
    renderPane("# Title\n", onHide);
    act(() => {
      screen.getByTestId("markdown-preview-hide").click();
    });
    expect(onHide).toHaveBeenCalledTimes(1);
  });
});
