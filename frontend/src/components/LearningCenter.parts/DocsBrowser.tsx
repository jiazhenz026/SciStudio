/**
 * The Learning Center's Reading tab: a reader for the shipped documentation (#2157).
 *
 * SciStudio ships its whole user documentation set inside the wheel —
 * `scistudio/_user_guide/`, the guide pages plus the generated API reference —
 * and publishes that same tree as the documentation site. Until now the product
 * gave a reader no way in: the Reading tab held reading *tutorials*, of which
 * there are none, so it said "Reading tutorials will appear here" and stopped.
 *
 * It now holds the documentation, laid out the way the site lays it out: the
 * menu on the left, the page on the right, opening on the user guide's front
 * page. The menu is not an editorial re-listing — the backend reproduces
 * MkDocs' own nav rules, so the order, the titles, and the two sections that
 * expand are the published sidebar's, down to its quirks.
 *
 * Package Development is not here. It is a developer document that lives in the
 * repository rather than in the shipped tree, and was never part of what a user
 * gets.
 *
 * Reading tutorials did not go away — they are simply listed in their own
 * source's tab now, alongside every other tutorial, and still run in
 * `ReadingSurface`.
 */

import { ArrowLeft, FileCode2, Loader2 } from "lucide-react";
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";

import {
  fetchUserDocPage,
  fetchUserDocsNav,
  type DocsNavItem,
  type DocsNavResponse,
  type DocsPageResponse,
} from "../../lib/api/userDocs";

import { DocMarkdown } from "./DocMarkdown";
import { docsNavPathOf, docsPages } from "./docsNav";

/** Where the reader is: a path, and a heading on it to land on. */
interface DocsLocation {
  path: string;
  anchor: string | null;
}

interface DocsNavListProps {
  items: DocsNavItem[];
  depth: number;
  current: string | null;
  onOpen: (path: string) => void;
}

/**
 * One level of the menu.
 *
 * A section is a heading, not a link — that is what it is on the site, where
 * MkDocs generates it from a directory name and gives it nothing to open.
 */
function DocsNavList({ items, depth, current, onOpen }: DocsNavListProps) {
  return (
    <ul className="flex flex-col gap-0.5">
      {items.map((item) => {
        if (item.kind === "section") {
          /*
           * A section has no path of its own, so it is keyed by the first page
           * under it — the one thing about a section that is unique in a tree
           * where two directories may share a title.
           */
          const key = `section:${docsPages(item.children)[0]?.path ?? item.title}`;
          return (
            <li key={key}>
              <p
                className="px-2 pb-0.5 pt-3 text-[0.7rem] font-semibold uppercase tracking-wide text-stone-400"
                data-testid={`docs-nav-section-${item.title}`}
                style={{ paddingLeft: `${0.5 + depth * 0.75}rem` }}
              >
                {item.title}
              </p>
              <DocsNavList
                current={current}
                depth={depth + 1}
                items={item.children}
                onOpen={onOpen}
              />
            </li>
          );
        }
        const path = item.path ?? "";
        const selected = path === current;
        return (
          <li key={`page:${path}`}>
            <button
              aria-current={selected ? "page" : undefined}
              className={`w-full rounded-lg py-1.5 pr-2 text-left text-xs leading-5 transition ${
                selected
                  ? "bg-ember/10 font-semibold text-ink"
                  : "text-stone-600 hover:bg-stone-100 hover:text-ink"
              }`}
              data-testid={`docs-nav-page-${path}`}
              onClick={() => onOpen(path)}
              style={{ paddingLeft: `${0.5 + depth * 0.75}rem` }}
              type="button"
            >
              {item.title}
            </button>
          </li>
        );
      })}
    </ul>
  );
}

export function DocsBrowser() {
  const [nav, setNav] = useState<DocsNavResponse | null>(null);
  const [navError, setNavError] = useState<string | null>(null);
  const [location, setLocation] = useState<DocsLocation | null>(null);
  /* Where the reader came from, so an inline link is never a one-way door. */
  const [trail, setTrail] = useState<DocsLocation[]>([]);
  const [page, setPage] = useState<DocsPageResponse | null>(null);
  const [pageError, setPageError] = useState<string | null>(null);
  const contentRef = useRef<HTMLDivElement | null>(null);

  /* The tree, and the page it says to start on. */
  useEffect(() => {
    let stale = false;
    void (async () => {
      try {
        const tree = await fetchUserDocsNav();
        if (stale) return;
        setNav(tree);
        setLocation((current) => current ?? { path: tree.root, anchor: null });
      } catch (error) {
        if (stale) return;
        setNavError(error instanceof Error ? error.message : String(error));
      }
    })();
    return () => {
      stale = true;
    };
  }, []);

  /* The open page. */
  const path = location?.path ?? null;
  useEffect(() => {
    if (path === null) return;
    let stale = false;
    setPage(null);
    setPageError(null);
    void (async () => {
      try {
        const loaded = await fetchUserDocPage(path);
        if (!stale) setPage(loaded);
      } catch (error) {
        if (!stale) setPageError(error instanceof Error ? error.message : String(error));
      }
    })();
    return () => {
      stale = true;
    };
  }, [path]);

  /*
   * Land on the heading a link named, or at the top of a fresh page. Layout
   * effect rather than effect: the pane is already scrolled where the previous
   * page left it, and correcting that after paint is a visible jump.
   */
  const anchor = location?.anchor ?? null;
  useLayoutEffect(() => {
    const pane = contentRef.current;
    if (!pane || page === null) return;
    if (anchor !== null) {
      const heading = pane.querySelector(`#${CSS.escape(anchor)}`);
      if (heading instanceof HTMLElement) {
        pane.scrollTop = heading.offsetTop - pane.offsetTop;
        return;
      }
    }
    pane.scrollTop = 0;
  }, [page, anchor]);

  const go = useCallback((next: DocsLocation) => {
    setLocation((current) => {
      if (current && current.path === next.path && current.anchor === next.anchor) return current;
      if (current) setTrail((previous) => [...previous, current]);
      return next;
    });
  }, []);

  const back = useCallback(() => {
    setTrail((previous) => {
      const last = previous[previous.length - 1];
      if (!last) return previous;
      setLocation(last);
      return previous.slice(0, -1);
    });
  }, []);

  const onAnchor = useCallback((target: string) => {
    setLocation((current) => (current ? { path: current.path, anchor: target } : current));
  }, []);

  const onExternal = useCallback((href: string) => {
    window.open(href, "_blank", "noopener,noreferrer");
  }, []);

  if (navError !== null) {
    return (
      <p className="px-6 py-6 text-sm text-red-700" data-testid="docs-nav-error">
        {navError}
      </p>
    );
  }

  if (nav === null) {
    return (
      <p className="inline-flex items-center gap-2 px-6 py-6 text-sm text-stone-500">
        <Loader2 aria-hidden="true" className="size-4 animate-spin" />
        Loading the documentation…
      </p>
    );
  }

  const navPath = path === null ? null : docsNavPathOf(nav.items, path);

  return (
    <div className="flex min-h-0 flex-1" data-testid="docs-browser">
      {/* The left menu, as the site lays it out. */}
      <nav
        aria-label="Documentation"
        className="w-60 shrink-0 overflow-y-auto border-r border-stone-200 py-3 pl-3 pr-2"
      >
        <p className="px-2 pb-1 text-[0.7rem] font-semibold uppercase tracking-wide text-stone-400">
          {nav.title}
        </p>
        <DocsNavList
          current={navPath}
          depth={0}
          items={nav.items}
          onOpen={(next) => go({ path: next, anchor: null })}
        />
      </nav>

      <div className="flex min-w-0 flex-1 flex-col">
        {trail.length > 0 ? (
          <div className="shrink-0 px-6 pt-3">
            <button
              className="inline-flex items-center gap-1.5 text-xs font-medium text-stone-500 transition hover:text-ink"
              data-testid="docs-back"
              onClick={back}
              type="button"
            >
              <ArrowLeft aria-hidden="true" className="size-3.5" />
              Back
            </button>
          </div>
        ) : null}

        <div className="min-h-0 flex-1 overflow-y-auto px-6 py-4" ref={contentRef}>
          {pageError !== null ? (
            <p className="text-sm text-red-700" data-testid="docs-page-error">
              {pageError}
            </p>
          ) : page === null ? (
            <p className="inline-flex items-center gap-2 text-sm text-stone-500">
              <Loader2 aria-hidden="true" className="size-4 animate-spin" />
              Loading…
            </p>
          ) : page.kind === "markdown" ? (
            <DocMarkdown
              onAnchor={onAnchor}
              onExternal={onExternal}
              onNavigate={(next, target) => go({ path: next, anchor: target })}
              path={page.path}
              source={page.text}
            />
          ) : (
            /*
             * A worked example's source file. The guide links to `block.py` and
             * `accucor.R` the way the site serves them — verbatim, beside the
             * page that links them — so the reader shows the file, not a
             * rendering of it.
             */
            <div data-testid="docs-source">
              <p className="mb-2 inline-flex items-center gap-2 font-mono text-xs text-stone-500">
                <FileCode2 aria-hidden="true" className="size-4" />
                {page.path}
              </p>
              <pre className="overflow-x-auto rounded-xl border border-stone-200 bg-stone-50 p-4 font-mono text-xs leading-5 text-ink">
                {page.text}
              </pre>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
