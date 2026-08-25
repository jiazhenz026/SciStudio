/**
 * #2157 — the documentation reader's navigation arithmetic.
 *
 * Link resolution is the part of the reader that is easy to get subtly wrong
 * and impossible to notice: a relative link resolved against the guide's root
 * instead of the open page's directory lands on the right-looking page for the
 * eleven links written at the top level and on nothing for the ones written
 * inside `examples/`. So the cases below are the shapes the shipped guide
 * actually contains, plus the ones that must not resolve at all.
 */

import { describe, expect, it } from "vitest";

import type { DocsNavItem } from "../../../lib/api/userDocs";
import {
  docsNavItems,
  docsNavPathOf,
  docsPages,
  docsTitleOf,
  headingSlug,
  resolveDocsLink,
} from "../docsNav";

function page(title: string, path: string): DocsNavItem {
  return { kind: "page", title, path, children: [] };
}

function section(title: string, children: DocsNavItem[]): DocsNavItem {
  return { kind: "section", title, path: null, children };
}

/** The shape the backend returns, trimmed to the rows these tests need. */
const TREE: DocsNavItem[] = [
  page("SciStudio user guide", "README.md"),
  page("The AI assistant", "ai-assistant.md"),
  page("Using the canvas: build, run, preview", "using-the-gui.md"),
  section("Api reference", [page("Index", "api-reference/index.md")]),
  section("Examples", [
    page("Examples", "examples/README.md"),
    section("App fiji", [
      page("AppBlock example — run a Fiji macro", "examples/app-fiji/README.md"),
    ]),
  ]),
];

describe("docsPages", () => {
  it("flattens every page row and keeps display order", () => {
    expect(docsPages(TREE).map((row) => row.path)).toEqual([
      "README.md",
      "ai-assistant.md",
      "using-the-gui.md",
      "api-reference/index.md",
      "examples/README.md",
      "examples/app-fiji/README.md",
    ]);
  });

  it("does not treat a section as a page", () => {
    expect(docsPages(TREE).some((row) => row.title === "Api reference")).toBe(false);
  });

  it("treats a row without children as a leaf rather than throwing", () => {
    const malformed = [{ kind: "section", title: "Api reference", path: null }] as DocsNavItem[];
    expect(docsPages(malformed)).toEqual([]);
  });
});

describe("docsNavItems", () => {
  it("treats a body without its rows as empty, not as a crash", () => {
    expect(docsNavItems(undefined)).toEqual([]);
    expect(docsNavItems(null)).toEqual([]);
    expect(docsNavItems({} as unknown as DocsNavItem[])).toEqual([]);
  });
});

describe("docsTitleOf", () => {
  it("finds a page nested inside a section", () => {
    expect(docsTitleOf(TREE, "api-reference/index.md")).toBe("Index");
  });

  it("returns null for a path the tree does not list", () => {
    expect(docsTitleOf(TREE, "examples/app-fiji/block.py")).toBeNull();
  });
});

describe("resolveDocsLink", () => {
  it("resolves a sibling link from a top-level page", () => {
    expect(resolveDocsLink("getting-started.md", "ai-assistant.md")).toEqual({
      kind: "page",
      path: "ai-assistant.md",
      anchor: null,
    });
  });

  it("resolves against the open page's directory, not the guide's root", () => {
    // `examples/README.md` links to its example directories by bare name.
    expect(resolveDocsLink("examples/README.md", "app-fiji/")).toEqual({
      kind: "page",
      path: "examples/app-fiji/",
      anchor: null,
    });
  });

  it("keeps a directory link a directory, for the backend to index", () => {
    expect(resolveDocsLink("README.md", "examples/")).toEqual({
      kind: "page",
      path: "examples/",
      anchor: null,
    });
  });

  it("carries the anchor of a cross-page link", () => {
    expect(resolveDocsLink("writing-plots.md", "using-the-gui.md#previewing-data")).toEqual({
      kind: "page",
      path: "using-the-gui.md",
      anchor: "previewing-data",
    });
  });

  it("treats a bare fragment as a jump within the open page", () => {
    expect(resolveDocsLink("ai-assistant.md", "#kimi-code-works-in-chat")).toEqual({
      kind: "anchor",
      anchor: "kimi-code-works-in-chat",
    });
  });

  it("climbs out of a subdirectory", () => {
    expect(resolveDocsLink("examples/app-fiji/README.md", "../../writing-blocks.md")).toEqual({
      kind: "page",
      path: "writing-blocks.md",
      anchor: null,
    });
  });

  it("offers an http link to the world outside", () => {
    expect(resolveDocsLink("data-types.md", "https://docs.pydantic.dev/")).toEqual({
      kind: "external",
      href: "https://docs.pydantic.dev/",
    });
  });

  it.each([
    ["a link that climbs out of the guide", "../../../../pyproject.toml"],
    ["an absolute path", "/etc/passwd"],
    ["a script url", "javascript:alert(1)"],
    ["a data url", "data:text/html,<script>alert(1)</script>"],
    ["an empty href", "   "],
  ])("refuses %s", (_what, href) => {
    expect(resolveDocsLink("README.md", href)).toEqual({ kind: "none" });
  });
});

describe("docsNavPathOf", () => {
  it("marks the page itself when the tree lists it", () => {
    expect(docsNavPathOf(TREE, "ai-assistant.md")).toBe("ai-assistant.md");
  });

  it("marks a directory's index row when the reader followed a directory link", () => {
    expect(docsNavPathOf(TREE, "examples/")).toBe("examples/README.md");
  });

  it("marks nothing for a file the menu does not list", () => {
    // `block.py` is reachable by link and absent from the menu, exactly as on
    // the published site.
    expect(docsNavPathOf(TREE, "examples/app-fiji/block.py")).toBeNull();
  });
});

describe("headingSlug", () => {
  it("matches the anchor the guide's own cross-page links were written against", () => {
    expect(headingSlug("Previewing data")).toBe("previewing-data");
  });

  it("drops punctuation the way Python-Markdown's toc does", () => {
    expect(headingSlug("Before you start: install a provider")).toBe(
      "before-you-start-install-a-provider",
    );
  });
});
