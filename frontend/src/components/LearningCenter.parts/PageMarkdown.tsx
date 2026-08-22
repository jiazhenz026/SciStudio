/**
 * ADR-053 Learning Center — reading-page markdown rendering (#2084).
 *
 * Tutorial pages are markdown files a tutorial ships (`assets/pages/`). The
 * product has no markdown dependency, and pulling one in for a reading pane
 * would be the heaviest part of the surface — so this renders the subset the
 * pages are written in, as React elements and nothing else:
 *
 *   headings (`#`..`###`), paragraphs, unordered lists (`- `), and inline
 *   `**bold**`, `*italic*`, and `` `code` ``.
 *
 * Everything is emitted as text nodes — no HTML from the page is ever parsed
 * or injected, so a page (which for user/project tutorials is authored
 * content) cannot script this surface. Unrecognised markdown renders as its
 * literal text, which is the honest failure for a copy format: visible in
 * review, never lost.
 */

import type { ReactNode } from "react";

const INLINE = /(\*\*[^*]+\*\*|`[^`]+`|\*[^*]+\*)/g;

/** `**bold**`, `` `code` `` and `*italic*` spans; everything else is text. */
function renderInline(text: string): ReactNode[] {
  return text.split(INLINE).map((part, index) => {
    if (part.startsWith("**") && part.endsWith("**") && part.length > 4) {
      return <strong key={index}>{part.slice(2, -2)}</strong>;
    }
    if (part.startsWith("`") && part.endsWith("`") && part.length > 2) {
      return (
        <code className="rounded bg-stone-100 px-1 py-0.5 font-mono text-[0.85em]" key={index}>
          {part.slice(1, -1)}
        </code>
      );
    }
    if (part.startsWith("*") && part.endsWith("*") && part.length > 2) {
      return <em key={index}>{part.slice(1, -1)}</em>;
    }
    return part;
  });
}

interface Block {
  kind: "heading" | "paragraph" | "list";
  level?: number;
  lines: string[];
}

/** Split source into blank-line-separated blocks, classifying each. */
function parseBlocks(source: string): Block[] {
  const blocks: Block[] = [];
  for (const chunk of source.replace(/\r\n/g, "\n").split(/\n{2,}/)) {
    const lines = chunk.split("\n").filter((line) => line.trim().length > 0);
    if (lines.length === 0) continue;
    const heading = /^(#{1,3})\s+(.*)$/.exec(lines[0]);
    if (heading && lines.length === 1) {
      blocks.push({ kind: "heading", level: heading[1].length, lines: [heading[2]] });
      continue;
    }
    if (lines[0].trimStart().startsWith("- ")) {
      // A `- ` line starts an item; a following line without the marker is the
      // same item wrapped (tutorial pages are wrapped at source width).
      const items: string[] = [];
      for (const line of lines) {
        const trimmed = line.trimStart();
        if (trimmed.startsWith("- ")) {
          items.push(trimmed.slice(2));
        } else if (items.length > 0) {
          items[items.length - 1] += ` ${trimmed}`;
        }
      }
      blocks.push({ kind: "list", lines: items });
      continue;
    }
    if (heading) {
      // A heading with body lines in the same chunk: split it off.
      blocks.push({ kind: "heading", level: heading[1].length, lines: [heading[2]] });
      blocks.push({ kind: "paragraph", lines: lines.slice(1) });
      continue;
    }
    blocks.push({ kind: "paragraph", lines });
  }
  return blocks;
}

export function PageMarkdown({ source }: { source: string }) {
  return (
    <div className="flex flex-col gap-3" data-testid="reading-page-markdown">
      {parseBlocks(source).map((block, index) => {
        if (block.kind === "heading") {
          const content = renderInline(block.lines[0]);
          if (block.level === 1) {
            return (
              <h3 className="font-display text-xl text-ink" key={index}>
                {content}
              </h3>
            );
          }
          return (
            <h4 className="text-sm font-semibold text-ink" key={index}>
              {content}
            </h4>
          );
        }
        if (block.kind === "list") {
          return (
            <ul className="flex list-disc flex-col gap-1.5 pl-5" key={index}>
              {block.lines.map((line, item) => (
                <li className="text-sm leading-6 text-stone-700" key={item}>
                  {renderInline(line)}
                </li>
              ))}
            </ul>
          );
        }
        return (
          <p className="text-sm leading-6 text-stone-700" key={index}>
            {renderInline(block.lines.join(" "))}
          </p>
        );
      })}
    </div>
  );
}
