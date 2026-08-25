/**
 * The documentation reader's markdown rendering (#2157).
 *
 * The user guide is written for the web: 158 fenced code blocks, 132 rows of
 * table, and a web of relative links between its pages. `PageMarkdown` — the
 * deliberately tiny renderer a tutorial's own reading pages use — renders none
 * of those, and a guide whose tables and code samples came out as raw pipes and
 * backticks would not be the documentation, it would be a picture of it. So
 * this surface renders real markdown, through `react-markdown` + `remark-gfm`.
 *
 * Raw HTML in a document is *not* rendered: `react-markdown` requires
 * `rehype-raw` to parse it, and that plugin is deliberately absent. The guide
 * contains no HTML today, and the reader is not the place to acquire an
 * injection surface.
 *
 * Two things are done here that the plain library does not do:
 *
 * - **Headings carry ids.** `using-the-gui.md#previewing-data` is a link the
 *   guide actually uses, so a heading has to be addressable. The slug matches
 *   Python-Markdown's `toc` slugify, which is what generated the anchors those
 *   links were written against.
 * - **Links are handed to the reader, not to the browser.** An in-guide link
 *   navigates the reader; an `http(s)` link opens outside; anything else — an
 *   absolute path, a foreign scheme, a target that leaves the guide — renders
 *   as its own text rather than as a link that goes nowhere.
 */

import type { ComponentPropsWithoutRef, ReactNode } from "react";
import { isValidElement } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { headingSlug, resolveDocsLink, type DocsLinkTarget } from "./docsNav";

interface DocMarkdownProps {
  /** The markdown source. */
  source: string;
  /** The tree-relative path of the page, which relative links resolve against. */
  path: string;
  /** Follow an in-guide link. */
  onNavigate: (path: string, anchor: string | null) => void;
  /** Jump to a heading on this page. */
  onAnchor: (anchor: string) => void;
  /** Open a link outside the product. */
  onExternal: (href: string) => void;
}

/** The visible text of a rendered node, for slugging a heading. */
function textOf(node: ReactNode): string {
  if (node === null || node === undefined || typeof node === "boolean") return "";
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(textOf).join("");
  if (isValidElement(node)) {
    return textOf((node.props as { children?: ReactNode }).children);
  }
  return "";
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
    return (
      <Tag className={HEADING_CLASS[level]} id={headingSlug(textOf(children))}>
        {children}
      </Tag>
    );
  };
}

export function DocMarkdown({ source, path, onNavigate, onAnchor, onExternal }: DocMarkdownProps) {
  const follow = (target: DocsLinkTarget) => {
    if (target.kind === "page") onNavigate(target.path, target.anchor);
    else if (target.kind === "anchor") onAnchor(target.anchor);
    else if (target.kind === "external") onExternal(target.href);
  };

  return (
    <div
      className="flex flex-col gap-3 text-sm leading-6 text-stone-700"
      data-testid="doc-markdown"
    >
      <Markdown
        components={{
          h1: heading(1),
          h2: heading(2),
          h3: heading(3),
          h4: heading(4),
          h5: heading(5),
          h6: heading(6),
          p: ({ children }) => <p className="leading-6">{children}</p>,
          a: ({ href, children }) => {
            const target = resolveDocsLink(path, href ?? "");
            if (target.kind === "none") return <>{children}</>;
            return (
              <a
                className="text-pine underline decoration-pine/40 underline-offset-2 transition hover:decoration-pine"
                data-doc-link={target.kind}
                href={href}
                onClick={(event) => {
                  event.preventDefault();
                  follow(target);
                }}
              >
                {children}
              </a>
            );
          },
          ul: ({ children }) => (
            <ul className="flex list-disc flex-col gap-1.5 pl-5">{children}</ul>
          ),
          ol: ({ children }) => (
            <ol className="flex list-decimal flex-col gap-1.5 pl-5">{children}</ol>
          ),
          li: ({ children }) => <li className="leading-6">{children}</li>,
          blockquote: ({ children }) => (
            <blockquote className="border-l-2 border-stone-300 pl-4 text-stone-600">
              {children}
            </blockquote>
          ),
          hr: () => <hr className="border-stone-200" />,
          /*
           * Inline code is a pill; a fenced block is a slab. Both arrive as
           * `<code>`, and a fenced block is *not* reliably told apart by its
           * className — four of the guide's fences open bare and so carry
           * none. The `pre` cancels the pill for whatever it wraps, which no
           * missing language can defeat.
           */
          pre: ({ children }) => (
            <pre className="overflow-x-auto rounded-xl border border-stone-200 bg-stone-50 p-4 font-mono text-xs leading-5 text-ink [&_code]:bg-transparent [&_code]:p-0 [&_code]:text-[1em]">
              {children}
            </pre>
          ),
          code: ({ children }) => (
            <code className="rounded bg-stone-100 px-1 py-0.5 font-mono text-[0.85em] text-ink">
              {children}
            </code>
          ),
          /* GFM tables. The guide leans on them; they scroll rather than clip. */
          table: ({ children }) => (
            <div className="overflow-x-auto">
              <table className="w-full border-collapse text-left text-xs">{children}</table>
            </div>
          ),
          thead: ({ children }) => <thead className="border-b border-stone-300">{children}</thead>,
          th: ({ children }) => (
            <th className="px-2 py-1.5 align-top font-semibold text-ink">{children}</th>
          ),
          tr: ({ children }) => <tr className="border-b border-stone-100">{children}</tr>,
          td: ({ children }) => <td className="px-2 py-1.5 align-top">{children}</td>,
        }}
        remarkPlugins={[remarkGfm]}
      >
        {source}
      </Markdown>
    </div>
  );
}
