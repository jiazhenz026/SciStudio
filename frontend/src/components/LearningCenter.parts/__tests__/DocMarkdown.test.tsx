/**
 * #2157 — the documentation reader renders the guide, not a picture of it.
 *
 * The reason this component exists at all is that the shipped guide contains
 * 158 fenced code blocks and 132 rows of table, and the tutorial reading pane's
 * tiny renderer produces neither. So the assertions below are about those two
 * shapes first, then about the link handling that turns a page into a guide:
 * an in-guide link navigates, an external one leaves, and anything the reader
 * cannot honestly follow is not offered as a link.
 */

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { DocMarkdown } from "../DocMarkdown";

afterEach(cleanup);

function renderDoc(source: string, path = "README.md") {
  const onNavigate = vi.fn();
  const onAnchor = vi.fn();
  const onExternal = vi.fn();
  const { container } = render(
    <DocMarkdown
      onAnchor={onAnchor}
      onExternal={onExternal}
      onNavigate={onNavigate}
      path={path}
      source={source}
    />,
  );
  return { container, onNavigate, onAnchor, onExternal };
}

describe("DocMarkdown — what the guide is written in", () => {
  it("renders a GFM table as a table", () => {
    renderDoc(
      ["| Page | What it covers |", "|---|---|", "| `data-types.md` | The types |"].join("\n"),
    );

    expect(screen.getByRole("table")).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "What it covers" })).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "The types" })).toBeInTheDocument();
  });

  it("renders a fenced block as a code slab, language or not", () => {
    const { container } = render(
      <DocMarkdown
        onAnchor={vi.fn()}
        onExternal={vi.fn()}
        onNavigate={vi.fn()}
        path="README.md"
        source={"```python\nfrom scistudio.blocks.base import InputPort\n```\n\n```\nplain\n```\n"}
      />,
    );

    const slabs = container.querySelectorAll("pre");
    expect(slabs).toHaveLength(2);
    expect(slabs[0].textContent).toContain("from scistudio.blocks.base import InputPort");
    expect(slabs[1].textContent).toContain("plain");
  });

  it("renders an ordered list, which the tutorial renderer cannot", () => {
    const { container } = renderDoc("1. Make a project\n2. Add a block\n");

    expect(container.querySelector("ol")).not.toBeNull();
    expect(container.querySelectorAll("ol > li")).toHaveLength(2);
  });

  it("does not render raw HTML in a document", () => {
    const { container } = renderDoc("<img src=x onerror=alert(1)>\n");

    expect(container.querySelector("img")).toBeNull();
  });

  it("gives a heading the anchor its cross-page links name", () => {
    const { container } = renderDoc("## Previewing data\n");

    expect(container.querySelector("#previewing-data")).not.toBeNull();
  });
});

describe("DocMarkdown — following a link", () => {
  it("navigates an in-guide link instead of leaving the app", () => {
    const { onNavigate } = renderDoc("See [the assistant](ai-assistant.md).");

    fireEvent.click(screen.getByRole("link", { name: "the assistant" }));

    expect(onNavigate).toHaveBeenCalledWith("ai-assistant.md", null);
  });

  it("carries a link's anchor through to the reader", () => {
    const { onNavigate } = renderDoc("See [previewing](using-the-gui.md#previewing-data).");

    fireEvent.click(screen.getByRole("link", { name: "previewing" }));

    expect(onNavigate).toHaveBeenCalledWith("using-the-gui.md", "previewing-data");
  });

  it("resolves a relative link against the page it is written on", () => {
    const { onNavigate } = renderDoc("See [the example](app-fiji/).", "examples/README.md");

    fireEvent.click(screen.getByRole("link", { name: "the example" }));

    expect(onNavigate).toHaveBeenCalledWith("examples/app-fiji/", null);
  });

  it("jumps within the page for a bare fragment", () => {
    const { onAnchor, onNavigate } = renderDoc("See [below](#the-chat-assistant).");

    fireEvent.click(screen.getByRole("link", { name: "below" }));

    expect(onAnchor).toHaveBeenCalledWith("the-chat-assistant");
    expect(onNavigate).not.toHaveBeenCalled();
  });

  it("sends an http link outside", () => {
    const { onExternal } = renderDoc("See [pydantic](https://docs.pydantic.dev/).");

    fireEvent.click(screen.getByRole("link", { name: "pydantic" }));

    expect(onExternal).toHaveBeenCalledWith("https://docs.pydantic.dev/");
  });

  it("renders a link it cannot follow as its own text, not as a dead link", () => {
    renderDoc("Run [this](javascript:alert(1)) now.");

    expect(screen.queryByRole("link")).toBeNull();
    expect(screen.getByText(/this/)).toBeInTheDocument();
  });
});
