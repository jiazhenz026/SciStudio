/**
 * Client for `/api/user-docs` — the shipped user documentation (#2157).
 *
 * The wire shapes are `scistudio/api/routes/user_docs.py`'s response models.
 * Nothing here interprets them: the navigation tree arrives already ordered and
 * titled the way the published site orders and titles it, because the backend
 * reproduces MkDocs' rules rather than re-listing the documentation by hand.
 *
 * Types live beside the client, following `learningCenter.ts` and the
 * work-import module, so the contract and the calls that depend on it move
 * together.
 */

import { apiFetch } from "./core";

/**
 * One row of the navigation tree.
 *
 * A `page` row carries the `path` it opens. A `section` row carries none: on
 * the published site a section is a directory MkDocs turned into a heading, and
 * a heading has nothing to open.
 */
export interface DocsNavItem {
  kind: "page" | "section";
  title: string;
  path: string | null;
  children: DocsNavItem[];
}

/** The navigation tree, and the page the reader starts on. */
export interface DocsNavResponse {
  /** The caption the published sidebar prints above this group. */
  title: string;
  /** The entry page — the user guide's front page. */
  root: string;
  items: DocsNavItem[];
}

/** One documentation file, as text. */
export interface DocsPageResponse {
  path: string;
  title: string;
  /**
   * `markdown` for a guide page; `source` for a file a page links to as a
   * worked example (`block.py`, `accucor.R`) — the site serves those verbatim
   * beside the page that links them, and so does the reader.
   */
  kind: "markdown" | "source";
  text: string;
}

/** The navigation tree. */
export async function fetchUserDocsNav(): Promise<DocsNavResponse> {
  return apiFetch<DocsNavResponse>("/api/user-docs/nav");
}

/**
 * One documentation file.
 *
 * The path is tree-relative and its segments are encoded, because a page name
 * becomes a URL segment. `%2F` would be encoded away by encoding the whole
 * path, so each segment is encoded and the separators are kept.
 */
export async function fetchUserDocPage(path: string): Promise<DocsPageResponse> {
  const encoded = path
    .split("/")
    .filter((segment) => segment.length > 0)
    .map(encodeURIComponent)
    .join("/");
  return apiFetch<DocsPageResponse>(`/api/user-docs/pages/${encoded}`);
}
