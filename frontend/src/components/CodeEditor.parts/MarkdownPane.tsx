/**
 * Live markdown preview beside the editor (#2361).
 *
 * A `.md` tab splits the centre stage: Monaco on the left, this on the right.
 * The source is the tab's own content, which the editor already writes into the
 * store on every keystroke, so the preview follows typing without a save, a
 * refetch, or any state of its own.
 *
 * Rendering goes through `react-markdown` + `remark-gfm` — the same pair the
 * documentation reader uses (`LearningCenter.parts/DocMarkdown`). That one is
 * bound to the user guide's navigation tree, so it cannot serve an arbitrary
 * project file; the component map here is the standalone equivalent, with the
 * link and image policy a project file needs.
 *
 * Raw HTML in the document is not rendered: parsing it requires `rehype-raw`,
 * which is deliberately absent here as it is there. A project's own markdown is
 * not a trusted source of markup for the app's own DOM.
 *
 * Two constructs cannot work and so are shown as what they are rather than as
 * something broken:
 *
 * - **Images.** The backend serves a project file as JSON text
 *   (`GET /api/projects/{id}/file`); there is no route that returns its bytes,
 *   so no `<img src>` can resolve against a project-relative path. An image
 *   renders as a marker naming the file it points at.
 * - **Relative links.** A link to another project file has nowhere to go for
 *   the same reason. It renders as its own text carrying the target in a
 *   tooltip. An `http(s)` or `mailto:` link is real and opens outside the app.
 *
 * Nothing is dropped in either case: the target stays visible, and the source
 * is on screen in the editor beside it.
 */

import { useEffect, useState } from "react";
import type { ComponentPropsWithoutRef } from "react";
import { PanelRightClose } from "lucide-react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";

/** Schemes a link may actually open with. */
const OPENABLE = /^(?:https?:|mailto:)/i;

/**
 * Open *href* outside the app.
 *
 * In the packaged desktop shell `window.open` would ask Electron for a child
 * BrowserWindow the main window has no handler for, so the link goes nowhere;
 * the preload bridge routes it through a validated `shell.openExternal` in the
 * main process instead. The browser build has no bridge and falls back to a
 * plain new tab.
 */
export function openExternally(href: string): void {
  const bridge = window.scistudioDesktop;
  if (bridge?.openExternal) {
    void bridge.openExternal(href);
    return;
  }
  window.open(href, "_blank", "noopener,noreferrer");
}

/** How long the preview waits after the last keystroke before it reparses. */
export const MARKDOWN_PREVIEW_DEBOUNCE_MS = 150;

export type LinkPolicy =
  | { kind: "open"; href: string }
  /** Rendered as text, with `target` shown in a tooltip when there is one. */
  | { kind: "inert"; target: string };

/**
 * Decide what a link in a project document may do.
 *
 * Only a scheme the browser can open leaves the app. Everything else — a
 * relative path, a bare fragment, a foreign scheme — stays as text, because a
 * control that looks like a link and goes nowhere is worse than plain prose.
 */
export function linkPolicy(href: string | undefined): LinkPolicy {
  const value = (href ?? "").trim();
  if (OPENABLE.test(value)) return { kind: "open", href: value };
  return { kind: "inert", target: value };
}

/** The text shown in place of an image the app cannot fetch. */
export function imageLabel(src: string | undefined, alt: string | undefined): string {
  const name = (src ?? "").split(/[?#]/)[0].split("/").filter(Boolean).pop() ?? "";
  const caption = (alt ?? "").trim();
  if (caption && name) return `${caption} — ${name}`;
  return caption || name || "image";
}

/**
 * Follow *value*, but no more often than every *delay* ms.
 *
 * Parsing runs over the whole document on each render, and a long README
 * reparsed on every keystroke is felt in the editor's own responsiveness. The
 * previous render stays on screen in between, so typing shows no flicker.
 */
export function useDebounced<T>(value: T, delay: number): T {
  const [settled, setSettled] = useState(value);
  useEffect(() => {
    if (Object.is(settled, value)) return;
    const timer = setTimeout(() => setSettled(value), delay);
    return () => clearTimeout(timer);
    // `settled` is read to skip a no-op timer, not to drive the effect: adding
    // it to the deps would restart the wait each time the value lands.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value, delay]);
  return settled;
}

const HEADING_CLASS: Record<number, string> = {
  1: "mt-1 font-display text-2xl text-ink",
  2: "mt-5 font-display text-xl text-ink",
  3: "mt-4 text-base font-semibold text-ink",
  4: "mt-3 text-sm font-semibold text-ink",
  5: "mt-3 text-sm font-semibold text-stone-700",
  6: "mt-3 text-xs font-semibold uppercase tracking-wide text-stone-500",
};

function heading(level: number) {
  const Tag = `h${level}` as "h1";
  return function Heading({ children }: ComponentPropsWithoutRef<"h1">) {
    return <Tag className={HEADING_CLASS[level]}>{children}</Tag>;
  };
}

/*
 * The component map is built once rather than per render: `react-markdown`
 * treats a fresh `components` object as a reason to rebuild the whole tree,
 * which would undo the debounce's only purpose.
 */
const COMPONENTS = {
  h1: heading(1),
  h2: heading(2),
  h3: heading(3),
  h4: heading(4),
  h5: heading(5),
  h6: heading(6),
  p: ({ children }: ComponentPropsWithoutRef<"p">) => <p className="leading-6">{children}</p>,
  a: ({ href, children }: ComponentPropsWithoutRef<"a">) => {
    const policy = linkPolicy(href);
    if (policy.kind === "inert") {
      return (
        <span
          className="text-stone-600 underline decoration-stone-300 decoration-dotted underline-offset-2"
          data-md-link="inert"
          title={policy.target || undefined}
        >
          {children}
        </span>
      );
    }
    return (
      <a
        className="text-pine underline decoration-pine/40 underline-offset-2 transition hover:decoration-pine"
        data-md-link="open"
        href={policy.href}
        onClick={(event) => {
          event.preventDefault();
          openExternally(policy.href);
        }}
        title={policy.href}
      >
        {children}
      </a>
    );
  },
  /*
   * No `<img>`: a project-relative path has no byte route to resolve against,
   * and an external one would fetch from a host the document chose. The marker
   * keeps the file name visible.
   */
  img: ({ src, alt }: ComponentPropsWithoutRef<"img">) => (
    <span
      className="inline-flex items-center rounded border border-dashed border-stone-300 px-1.5 py-0.5 font-mono text-xs text-stone-500"
      data-md-image="marker"
      title={typeof src === "string" && src ? src : undefined}
    >
      {imageLabel(typeof src === "string" ? src : "", alt)} (image not shown)
    </span>
  ),
  ul: ({ children }: ComponentPropsWithoutRef<"ul">) => (
    <ul className="flex list-disc flex-col gap-1.5 pl-5">{children}</ul>
  ),
  ol: ({ children }: ComponentPropsWithoutRef<"ol">) => (
    <ol className="flex list-decimal flex-col gap-1.5 pl-5">{children}</ol>
  ),
  /*
   * A GFM task list item carries its own checkbox and must not also carry a
   * bullet, so the marker is dropped exactly where `remark-gfm` set the class
   * it gives those items.
   */
  li: ({ children, className }: ComponentPropsWithoutRef<"li">) => (
    <li className={className?.includes("task-list-item") ? "list-none leading-6" : "leading-6"}>
      {children}
    </li>
  ),
  /* A task-list checkbox reports state; it is not an input the reader edits. */
  input: ({ checked, type }: ComponentPropsWithoutRef<"input">) => (
    <input
      checked={Boolean(checked)}
      className="mr-1.5 align-middle accent-pine"
      disabled
      readOnly
      type={type === "checkbox" ? "checkbox" : "text"}
    />
  ),
  blockquote: ({ children }: ComponentPropsWithoutRef<"blockquote">) => (
    <blockquote className="border-l-2 border-stone-300 pl-4 text-stone-600">{children}</blockquote>
  ),
  hr: () => <hr className="border-stone-200" />,
  /* A fence is a slab, inline code is a pill; both arrive as `code`. */
  pre: ({ children }: ComponentPropsWithoutRef<"pre">) => (
    <pre className="overflow-x-auto rounded-xl border border-stone-200 bg-stone-50 p-4 font-mono text-xs leading-5 text-ink [&_code]:bg-transparent [&_code]:p-0 [&_code]:text-[1em]">
      {children}
    </pre>
  ),
  code: ({ children }: ComponentPropsWithoutRef<"code">) => (
    <code className="rounded bg-stone-100 px-1 py-0.5 font-mono text-[0.85em] text-ink">
      {children}
    </code>
  ),
  table: ({ children }: ComponentPropsWithoutRef<"table">) => (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-left text-xs">{children}</table>
    </div>
  ),
  thead: ({ children }: ComponentPropsWithoutRef<"thead">) => (
    <thead className="border-b border-stone-300">{children}</thead>
  ),
  th: ({ children }: ComponentPropsWithoutRef<"th">) => (
    <th className="px-2 py-1.5 align-top font-semibold text-ink">{children}</th>
  ),
  tr: ({ children }: ComponentPropsWithoutRef<"tr">) => (
    <tr className="border-b border-stone-100">{children}</tr>
  ),
  td: ({ children }: ComponentPropsWithoutRef<"td">) => (
    <td className="px-2 py-1.5 align-top">{children}</td>
  ),
};

const REMARK_PLUGINS = [remarkGfm];

export interface MarkdownPaneProps {
  /** The document as it currently stands in the editor. */
  source: string;
  /** Close the preview and give the whole stage back to the editor. */
  onHide: () => void;
}

export function MarkdownPane({ source, onHide }: MarkdownPaneProps) {
  const settled = useDebounced(source, MARKDOWN_PREVIEW_DEBOUNCE_MS);
  const isEmpty = settled.trim() === "";

  return (
    <div className="flex h-full flex-col border-l border-stone-200 bg-white">
      <div className="flex items-center justify-between border-b border-stone-200 px-3 py-1.5">
        <span className="text-xs font-medium text-stone-500">Preview</span>
        <button
          aria-label="Hide the markdown preview"
          className="flex items-center gap-1 rounded-full border border-stone-300 px-2 py-0.5 text-xs text-stone-500 transition hover:border-ink hover:text-ink"
          data-testid="markdown-preview-hide"
          onClick={onHide}
          title="Hide the markdown preview"
          type="button"
        >
          <PanelRightClose className="h-3 w-3" />
          Hide
        </button>
      </div>
      <div className="flex-1 overflow-auto px-5 py-4" data-testid="markdown-preview">
        {isEmpty ? (
          <p className="text-sm text-stone-400" data-testid="markdown-preview-empty">
            This file is empty. What you type appears here.
          </p>
        ) : (
          <div className="flex flex-col gap-3 text-sm leading-6 text-stone-700">
            <Markdown components={COMPONENTS} remarkPlugins={REMARK_PLUGINS}>
              {settled}
            </Markdown>
          </div>
        )}
      </div>
    </div>
  );
}

export default MarkdownPane;
