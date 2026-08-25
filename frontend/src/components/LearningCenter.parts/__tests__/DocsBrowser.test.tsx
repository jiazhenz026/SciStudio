/**
 * #2157 — the Reading tab's documentation reader.
 *
 * The fixture below is the shipped tree's real shape, trimmed: the guide's
 * front page first, the flat guide pages after it, then the two directories
 * MkDocs turns into sections. It is deliberately not invented — the ordering
 * and the titles (including "Index", which the site really does print for the
 * generated reference's front page) are what `GET /api/user-docs/nav` returns,
 * and a reader tested against a tidier tree would be tested against a tree it
 * will never be given.
 */

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { DocsNavResponse, DocsPageResponse } from "../../../lib/api/userDocs";
import { fetchUserDocPage, fetchUserDocsNav } from "../../../lib/api/userDocs";
import { DocsBrowser } from "../DocsBrowser";

vi.mock("../../../lib/api/userDocs", () => ({
  fetchUserDocsNav: vi.fn(),
  fetchUserDocPage: vi.fn(),
}));

const NAV: DocsNavResponse = {
  title: "User guide",
  root: "README.md",
  items: [
    { kind: "page", title: "SciStudio user guide", path: "README.md", children: [] },
    { kind: "page", title: "The AI assistant", path: "ai-assistant.md", children: [] },
    {
      kind: "section",
      title: "Api reference",
      path: null,
      children: [{ kind: "page", title: "Index", path: "api-reference/index.md", children: [] }],
    },
    {
      kind: "section",
      title: "Examples",
      path: null,
      children: [
        { kind: "page", title: "Examples", path: "examples/README.md", children: [] },
        {
          kind: "section",
          title: "App fiji",
          path: null,
          children: [
            {
              kind: "page",
              title: "AppBlock example — run a Fiji macro",
              path: "examples/app-fiji/README.md",
              children: [],
            },
          ],
        },
      ],
    },
  ],
};

const PAGES: Record<string, DocsPageResponse> = {
  "README.md": {
    path: "README.md",
    title: "SciStudio user guide",
    kind: "markdown",
    text: "# SciStudio user guide\n\nWelcome. Ask the [AI assistant](ai-assistant.md).\n",
  },
  "ai-assistant.md": {
    path: "ai-assistant.md",
    title: "The AI assistant",
    kind: "markdown",
    text: "# The AI assistant\n\nWhat it can do for you.\n",
  },
  "examples/README.md": {
    path: "examples/README.md",
    title: "Examples",
    kind: "markdown",
    text: "# Examples\n\nA worked [AppBlock](app-fiji/) example.\n",
  },
  "examples/app-fiji/README.md": {
    path: "examples/app-fiji/README.md",
    title: "AppBlock example — run a Fiji macro",
    kind: "markdown",
    text: "# AppBlock example\n\nThe source is in [block.py](block.py).\n",
  },
  "examples/app-fiji/block.py": {
    path: "examples/app-fiji/block.py",
    title: "block.py",
    kind: "source",
    text: "class FijiBlock(AppBlock):\n    pass\n",
  },
};

const navMock = vi.mocked(fetchUserDocsNav);
const pageMock = vi.mocked(fetchUserDocPage);

beforeEach(() => {
  vi.clearAllMocks();
  navMock.mockResolvedValue(NAV);
  pageMock.mockImplementation(async (path: string) => {
    const page = PAGES[path] ?? PAGES[`${path}README.md`];
    if (!page) throw new Error(`No such documentation page: '${path}'`);
    return page;
  });
});

afterEach(cleanup);

describe("DocsBrowser — the menu", () => {
  it("opens on the user guide's front page", async () => {
    render(<DocsBrowser />);

    expect(await screen.findByText("Welcome.", { exact: false })).toBeInTheDocument();
    expect(pageMock).toHaveBeenCalledWith("README.md");
  });

  it("lists the tree in the order the site lists it, sections and all", async () => {
    render(<DocsBrowser />);
    await screen.findByTestId("docs-browser");

    const rows = screen.getAllByRole("listitem").map((node) => node.textContent?.split("\n")[0]);
    expect(rows[0]).toContain("SciStudio user guide");
    expect(screen.getByTestId("docs-nav-section-Api reference")).toBeInTheDocument();
    expect(screen.getByTestId("docs-nav-page-api-reference/index.md")).toHaveTextContent("Index");
  });

  it("marks the open page, and moves the mark when another is chosen", async () => {
    render(<DocsBrowser />);

    const front = await screen.findByTestId("docs-nav-page-README.md");
    expect(front).toHaveAttribute("aria-current", "page");

    fireEvent.click(screen.getByTestId("docs-nav-page-ai-assistant.md"));

    await waitFor(() =>
      expect(screen.getByTestId("docs-nav-page-ai-assistant.md")).toHaveAttribute(
        "aria-current",
        "page",
      ),
    );
    expect(screen.getByTestId("docs-nav-page-README.md")).not.toHaveAttribute("aria-current");
  });

  it("gives a section no button of its own, because the site gives it no link", async () => {
    render(<DocsBrowser />);
    await screen.findByTestId("docs-browser");

    expect(screen.getByTestId("docs-nav-section-Examples").tagName).toBe("P");
  });
});

describe("DocsBrowser — reading", () => {
  it("follows a link inside a page", async () => {
    render(<DocsBrowser />);

    fireEvent.click(await screen.findByRole("link", { name: "AI assistant" }));

    expect(await screen.findByText("What it can do for you.")).toBeInTheDocument();
  });

  it("resolves a directory link to that directory's index page", async () => {
    render(<DocsBrowser />);
    await screen.findByTestId("docs-browser");

    fireEvent.click(screen.getByTestId("docs-nav-page-examples/README.md"));
    fireEvent.click(await screen.findByRole("link", { name: "AppBlock" }));

    expect(await screen.findByText("The source is in", { exact: false })).toBeInTheDocument();
    // A directory path highlights that directory's index row, as the site does.
    expect(pageMock).toHaveBeenCalledWith("examples/app-fiji/");
  });

  it("shows a linked source file verbatim, the way the site serves it", async () => {
    render(<DocsBrowser />);
    await screen.findByTestId("docs-browser");

    fireEvent.click(screen.getByTestId("docs-nav-page-examples/app-fiji/README.md"));
    fireEvent.click(await screen.findByRole("link", { name: "block.py" }));

    const source = await screen.findByTestId("docs-source");
    expect(source).toHaveTextContent("class FijiBlock(AppBlock)");
  });

  it("offers a way back once a link has been followed", async () => {
    render(<DocsBrowser />);
    await screen.findByTestId("docs-browser");

    expect(screen.queryByTestId("docs-back")).toBeNull();

    fireEvent.click(await screen.findByRole("link", { name: "AI assistant" }));
    await screen.findByText("What it can do for you.");
    fireEvent.click(screen.getByTestId("docs-back"));

    expect(await screen.findByText("Welcome.", { exact: false })).toBeInTheDocument();
  });

  it("reports a page that will not load rather than showing an empty pane", async () => {
    render(<DocsBrowser />);
    await screen.findByTestId("docs-browser");
    pageMock.mockRejectedValueOnce(new Error("No such documentation page: 'ai-assistant.md'"));

    fireEvent.click(screen.getByTestId("docs-nav-page-ai-assistant.md"));

    expect(await screen.findByTestId("docs-page-error")).toHaveTextContent(
      "No such documentation page",
    );
  });

  /*
   * Found by the frontend CI mirror, not by design: with no catalogue the
   * Reading tab is the *only* tab, so it is what the Learning Center opens on
   * — and a tree that arrived without its `items` threw inside a render, which
   * is not a caught error but a blank application. `App.test.tsx` went down
   * whole.
   */
  it("survives a tree that arrives without its rows", async () => {
    navMock.mockResolvedValueOnce({ title: "User guide", root: "" } as DocsNavResponse);
    render(<DocsBrowser />);

    expect(await screen.findByTestId("docs-browser")).toBeInTheDocument();
    expect(screen.queryByTestId("docs-nav-page-README.md")).toBeNull();
  });

  it("reports a tree that will not load rather than an empty menu", async () => {
    navMock.mockRejectedValueOnce(new Error("documentation unavailable"));
    render(<DocsBrowser />);

    expect(await screen.findByTestId("docs-nav-error")).toHaveTextContent(
      "documentation unavailable",
    );
  });
});
