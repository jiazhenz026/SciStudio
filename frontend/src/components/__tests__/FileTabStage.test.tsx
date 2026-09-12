/**
 * #2361 — which file tabs get the split stage, and how the split is closed.
 *
 * `CodeEditor` is stubbed with a textarea: the real one is Monaco, which jsdom
 * cannot mount, and the only thing this suite needs from it is the contract it
 * already has with the store — a keystroke becomes `tab.content`. The harness
 * below plays the part `ProjectWorkspace` plays in the app (hand the content
 * back down), so "the preview follows typing" is tested end to end rather than
 * as a prop the test sets itself.
 */

import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useAppStore } from "../../store";
import type { FileTab } from "../../store/types";
import { resetAppStore } from "../../testUtils";
import { MARKDOWN_PREVIEW_DEBOUNCE_MS } from "../CodeEditor.parts/MarkdownPane";
import { FileTabStage } from "../FileTabStage";

interface StubEditorProps {
  tab: FileTab;
  onContentChange: (content: string) => void;
  onSave: () => void;
}

vi.mock("../CodeEditor", () => ({
  CodeEditor: ({ tab, onContentChange }: StubEditorProps) => (
    <textarea
      data-testid="code-editor"
      onChange={(event) => onContentChange(event.target.value)}
      value={tab.content}
    />
  ),
}));

/*
 * react-resizable-panels measures its group. jsdom has no layout and no
 * ResizeObserver, so it gets an inert one; the panels still render their
 * children, which is all this suite reads.
 */
class NoopResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}

function makeFileTab(overrides: Partial<FileTab> = {}): FileTab {
  return {
    kind: "file",
    id: "file:README.md",
    filePath: "README.md",
    displayName: "README.md",
    language: "markdown",
    content: "# Title\n",
    contentLoadedAt: 0,
    dirty: false,
    readOnly: false,
    ...overrides,
  };
}

/** Stands in for ProjectWorkspace: the editor's content comes back down. */
function Harness({ tab }: { tab: FileTab }) {
  const [content, setContent] = useState(tab.content);
  return <FileTabStage onContentChange={setContent} onSave={vi.fn()} tab={{ ...tab, content }} />;
}

/** Render, then let the first debounce land. */
function renderStage(tab: FileTab) {
  const result = render(<Harness tab={tab} />);
  act(() => {
    vi.advanceTimersByTime(MARKDOWN_PREVIEW_DEBOUNCE_MS + 1);
  });
  return result;
}

beforeEach(() => {
  vi.stubGlobal("ResizeObserver", NoopResizeObserver);
  resetAppStore();
  vi.useFakeTimers();
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
  resetAppStore();
});

describe("FileTabStage", () => {
  it("splits a markdown tab into the editor and the preview", () => {
    renderStage(makeFileTab());
    expect(screen.getByTestId("code-editor")).toBeInTheDocument();
    expect(screen.getByTestId("markdown-preview")).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1, name: "Title" })).toBeInTheDocument();
  });

  it.each([
    ["python", "blocks/sample.py"],
    ["r", "plots/qc/render.R"],
    ["json", "workflow.json"],
    ["plaintext", "notes.txt"],
  ])("leaves a %s tab as the editor alone", (language, filePath) => {
    renderStage(
      makeFileTab({
        id: `file:${filePath}`,
        filePath,
        displayName: filePath,
        language: language as FileTab["language"],
        content: "# not markdown\n",
      }),
    );
    expect(screen.getByTestId("code-editor")).toBeInTheDocument();
    expect(screen.queryByTestId("markdown-preview")).toBeNull();
    expect(screen.queryByTestId("markdown-preview-hide")).toBeNull();
    expect(screen.queryByTestId("markdown-preview-show")).toBeNull();
  });

  it("follows typing in the editor once the debounce lands", () => {
    renderStage(makeFileTab({ content: "# Before\n" }));
    expect(screen.getByTestId("markdown-preview").textContent).toContain("Before");

    fireEvent.change(screen.getByTestId("code-editor"), {
      target: { value: "# After\n\nA new paragraph.\n" },
    });

    // Still the previous render: nothing flickers while the user types.
    act(() => {
      vi.advanceTimersByTime(MARKDOWN_PREVIEW_DEBOUNCE_MS - 1);
    });
    expect(screen.getByTestId("markdown-preview").textContent).toContain("Before");

    act(() => {
      vi.advanceTimersByTime(2);
    });
    const preview = screen.getByTestId("markdown-preview");
    expect(preview.textContent).toContain("After");
    expect(preview.textContent).toContain("A new paragraph.");
    expect(preview.textContent).not.toContain("Before");
  });

  it("hides the preview and offers a way back", () => {
    renderStage(makeFileTab());
    expect(screen.getByTestId("markdown-preview")).toBeInTheDocument();

    act(() => {
      screen.getByTestId("markdown-preview-hide").click();
    });
    expect(screen.queryByTestId("markdown-preview")).toBeNull();
    expect(screen.getByTestId("code-editor")).toBeInTheDocument();

    const show = screen.getByTestId("markdown-preview-show");
    expect(show).toBeInTheDocument();
    act(() => {
      show.click();
      vi.advanceTimersByTime(MARKDOWN_PREVIEW_DEBOUNCE_MS + 1);
    });
    expect(screen.getByTestId("markdown-preview")).toBeInTheDocument();
  });

  it("records the choice in the store, so it outlives the tab", () => {
    expect(useAppStore.getState().markdownPreviewVisible).toBe(true);

    const { unmount } = renderStage(makeFileTab());
    act(() => {
      screen.getByTestId("markdown-preview-hide").click();
    });
    expect(useAppStore.getState().markdownPreviewVisible).toBe(false);

    // Switch to another markdown file: the preview stays closed.
    unmount();
    renderStage(makeFileTab({ id: "file:notes.md", filePath: "notes.md", content: "# Notes\n" }));
    expect(screen.queryByTestId("markdown-preview")).toBeNull();
    expect(screen.getByTestId("markdown-preview-show")).toBeInTheDocument();
  });

  it("persists the choice under the studio-ui key", () => {
    renderStage(makeFileTab());
    act(() => {
      screen.getByTestId("markdown-preview-hide").click();
    });

    const raw = localStorage.getItem("scistudio-studio-ui");
    expect(raw).not.toBeNull();
    expect(JSON.parse(raw as string).state.markdownPreviewVisible).toBe(false);
  });

  it("starts a switched-to markdown file on its own content", () => {
    const { unmount } = renderStage(makeFileTab({ content: "# First file\n" }));
    expect(screen.getByTestId("markdown-preview").textContent).toContain("First file");
    unmount();

    render(
      <Harness
        tab={makeFileTab({
          id: "file:second.md",
          filePath: "second.md",
          content: "# Second file\n",
        })}
      />,
    );
    // Before any timer runs: the new tab's own content, not the old one held
    // over for the length of a debounce.
    const preview = screen.getByTestId("markdown-preview");
    expect(preview.textContent).toContain("Second file");
    expect(preview.textContent).not.toContain("First file");
  });
});
