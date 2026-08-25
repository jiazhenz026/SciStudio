/**
 * The documentation reader's navigation arithmetic (#2157).
 *
 * Two questions, both pure, both testable without a DOM: which nav row is the
 * open page, and where does a link inside a page go.
 *
 * The second is the one that makes the reader a reader rather than a viewer of
 * one file. The guide is written as a web of relative links — `ai-assistant.md`
 * appears eleven times, `examples/` twice, `using-the-gui.md#previewing-data`
 * once — and on the published site every one of them is a click. Here they
 * resolve against the open page's own directory, exactly as a browser resolves
 * them, and come back as a target the reader can open.
 */

import type { DocsNavItem } from "../../lib/api/userDocs";

/** Where a link in a page goes. */
export type DocsLinkTarget =
  | { kind: "page"; path: string; anchor: string | null }
  | { kind: "anchor"; anchor: string }
  | { kind: "external"; href: string }
  /** A link this reader cannot follow — rendered as text rather than as a lie. */
  | { kind: "none" };

/**
 * Python-Markdown's `toc` slug: strip everything that is not a word character,
 * whitespace or a dash; lowercase; collapse runs of whitespace and dashes.
 *
 * The guide's cross-page anchors — `using-the-gui.md#previewing-data` — were
 * written against the published site, so matching that slug is what makes them
 * land on the heading they name.
 */
export function headingSlug(text: string): string {
  return text
    .normalize("NFKD")
    .replace(/[^\w\s-]/g, "")
    .trim()
    .toLowerCase()
    .replace(/[-\s]+/g, "-");
}

/** Every page row of the tree, in display order. */
export function docsPages(items: DocsNavItem[]): DocsNavItem[] {
  const pages: DocsNavItem[] = [];
  for (const item of items) {
    if (item.kind === "page" && item.path) pages.push(item);
    if (Array.isArray(item.children)) pages.push(...docsPages(item.children));
  }
  return pages;
}

/** The title of the page at `path`, or null when the tree has no such row. */
export function docsTitleOf(items: DocsNavItem[], path: string): string | null {
  return docsPages(items).find((page) => page.path === path)?.title ?? null;
}

/**
 * Resolve one `[text](href)` against the page it appears on.
 *
 * `from` is the tree-relative path of the open page, so its directory is what a
 * relative href resolves against — a link to `ai-assistant.md` inside
 * `examples/README.md` means `examples/ai-assistant.md`, not the guide page of
 * that name, and getting this wrong is invisible until a reader in a
 * subdirectory follows a link.
 *
 * A directory href (`examples/`) stays a directory: the backend resolves it to
 * that directory's index page, which is what the site does with it too.
 */
export function resolveDocsLink(from: string, href: string): DocsLinkTarget {
  const trimmed = href.trim();
  if (trimmed.length === 0) return { kind: "none" };
  if (trimmed.startsWith("#")) return { kind: "anchor", anchor: trimmed.slice(1) };
  if (/^[a-z][a-z0-9+.-]*:/i.test(trimmed)) {
    // A scheme of any kind is somewhere else. Only the web ones are offered;
    // `javascript:` and friends are refused rather than handed to the browser.
    return /^https?:$/i.test(trimmed.slice(0, trimmed.indexOf(":") + 1))
      ? { kind: "external", href: trimmed }
      : { kind: "none" };
  }
  if (trimmed.startsWith("/")) {
    // The reader is rooted at the user guide; an absolute path is not a path
    // within it, so there is nothing honest to open.
    return { kind: "none" };
  }

  const hash = trimmed.indexOf("#");
  const target = hash === -1 ? trimmed : trimmed.slice(0, hash);
  const anchor = hash === -1 ? null : trimmed.slice(hash + 1) || null;
  if (target.length === 0) return anchor === null ? { kind: "none" } : { kind: "anchor", anchor };

  const base = from.includes("/") ? from.slice(0, from.lastIndexOf("/")) : "";
  const segments: string[] = [];
  for (const segment of `${base}/${target}`.split("/")) {
    if (segment === "" || segment === ".") continue;
    if (segment === "..") {
      // Climbing above the guide's root leaves the documentation set; there is
      // no page there to open.
      if (segments.length === 0) return { kind: "none" };
      segments.pop();
      continue;
    }
    segments.push(segment);
  }
  if (segments.length === 0) return { kind: "none" };

  // A trailing slash survives the split, so a directory link is rebuilt as one.
  const path = target.endsWith("/") ? `${segments.join("/")}/` : segments.join("/");
  return { kind: "page", path, anchor };
}

/**
 * The nav path an open page should highlight.
 *
 * A directory path (`examples/`) is the row for that directory's index page,
 * which is the row the site marks current when you land there.
 */
export function docsNavPathOf(items: DocsNavItem[], path: string): string | null {
  if (docsTitleOf(items, path) !== null) return path;
  if (!path.endsWith("/")) return null;
  const pages = docsPages(items);
  for (const stem of ["README.md", "index.md"]) {
    const candidate = `${path}${stem}`;
    if (pages.some((page) => page.path === candidate)) return candidate;
  }
  return null;
}
