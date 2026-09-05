/**
 * ADR-054 spec 4 (T-005) — cell outputs, rendered from the `.ipynb` MIME
 * bundle (FR-011).
 *
 * The shape this module reads is nbformat's, not SciStudio's: `output_type` is
 * `stream` / `display_data` / `execute_result` / `error`, and a rich output is
 * a `data` map from MIME type to payload. That is deliberate and is the whole
 * reason the notebook looks the same here and in Jupyter — inventing a
 * SciStudio output shape would mean a notebook whose outputs are ours until
 * somebody opens it in JupyterLab.
 *
 * **The ANSI renderer is ours, and there is no dependency behind it.** A
 * traceback arrives with SGR escapes in it, and the bundle carries no ANSI
 * library. `parseAnsi` below implements the SGR subset IPython actually emits:
 * reset, bold/dim/italic/underline, the sixteen basic colours, the 256-colour
 * cube and truecolor. Everything else — cursor moves, erase-line, an escape
 * that never terminates — is consumed and dropped rather than printed, because
 * a traceback with `[0;31m` scattered through it is worse than no colour.
 *
 * **HTML is framed, not filtered.** An `<iframe sandbox>` with no permissions
 * at all is stronger than a sanitiser: a sanitiser is a filter list that has to
 * be right about every attribute and every future browser, while the frame
 * denies scripts, same-origin access, forms, popups and navigation outright. It
 * costs one thing — a script-driven HTML output (a Plotly or Bokeh bundle)
 * renders as its static markup. See the follow-up register, S4-A2 F-A2-003.
 */

import { useMemo, useState } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";

import type { ExploreOutput } from "../types/api";

// -- ANSI (FR-011) ----------------------------------------------------------

/** Every attribute one run of ANSI-styled text can carry. */
export interface AnsiStyle {
  color?: string;
  background?: string;
  bold?: boolean;
  dim?: boolean;
  italic?: boolean;
  underline?: boolean;
}

export interface AnsiSegment {
  text: string;
  style: AnsiStyle;
}

/**
 * The sixteen basic colours, chosen for a light background.
 *
 * A terminal palette used unchanged would put IPython's bright yellow on white
 * paper, which is unreadable; these are the same hues at a weight that reads.
 */
const BASIC_COLORS = [
  "#3f3f46",
  "#b91c1c",
  "#15803d",
  "#b45309",
  "#1d4ed8",
  "#a21caf",
  "#0e7490",
  "#71717a",
] as const;

const BRIGHT_COLORS = [
  "#52525b",
  "#ef4444",
  "#16a34a",
  "#ca8a04",
  "#3b82f6",
  "#d946ef",
  "#06b6d4",
  "#a1a1aa",
] as const;

/** One entry of the xterm 256-colour table, as a CSS colour. */
function color256(index: number): string {
  if (index < 8) return BASIC_COLORS[index];
  if (index < 16) return BRIGHT_COLORS[index - 8];
  if (index < 232) {
    const offset = index - 16;
    const steps = [0, 95, 135, 175, 215, 255];
    const r = steps[Math.floor(offset / 36) % 6];
    const g = steps[Math.floor(offset / 6) % 6];
    const b = steps[offset % 6];
    return `rgb(${r}, ${g}, ${b})`;
  }
  const grey = 8 + (index - 232) * 10;
  return `rgb(${grey}, ${grey}, ${grey})`;
}

/** Apply one SGR parameter run to a style, returning how many it consumed. */
function applySgr(style: AnsiStyle, params: number[], at: number): number {
  const code = params[at];
  if (code === 0) {
    for (const key of Object.keys(style) as (keyof AnsiStyle)[]) delete style[key];
    return 1;
  }
  if (code === 1) {
    style.bold = true;
    return 1;
  }
  if (code === 2) {
    style.dim = true;
    return 1;
  }
  if (code === 3) {
    style.italic = true;
    return 1;
  }
  if (code === 4) {
    style.underline = true;
    return 1;
  }
  if (code === 21 || code === 22) {
    delete style.bold;
    delete style.dim;
    return 1;
  }
  if (code === 23) {
    delete style.italic;
    return 1;
  }
  if (code === 24) {
    delete style.underline;
    return 1;
  }
  if (code >= 30 && code <= 37) {
    style.color = BASIC_COLORS[code - 30];
    return 1;
  }
  if (code >= 90 && code <= 97) {
    style.color = BRIGHT_COLORS[code - 90];
    return 1;
  }
  if (code === 39) {
    delete style.color;
    return 1;
  }
  if (code >= 40 && code <= 47) {
    style.background = BASIC_COLORS[code - 40];
    return 1;
  }
  if (code >= 100 && code <= 107) {
    style.background = BRIGHT_COLORS[code - 100];
    return 1;
  }
  if (code === 49) {
    delete style.background;
    return 1;
  }
  if (code === 38 || code === 48) {
    const target: keyof AnsiStyle = code === 38 ? "color" : "background";
    if (params[at + 1] === 5 && params.length > at + 2) {
      style[target] = color256(params[at + 2]);
      return 3;
    }
    if (params[at + 1] === 2 && params.length > at + 4) {
      style[target] = `rgb(${params[at + 2]}, ${params[at + 3]}, ${params[at + 4]})`;
      return 5;
    }
    // A truncated extended-colour sequence: drop it rather than guess.
    return params.length - at;
  }
  // Everything else (inverse, conceal, fonts, ...) is consumed and ignored.
  return 1;
}

/** `ESC`, written as an escape so this file carries no raw control byte. */
const ESC = "\u001b";

/**
 * Split ANSI-escaped text into styled runs.
 *
 * Total on any input. The adversarial cases are the ones that matter and each
 * has one rule:
 *
 *   - an escape that never terminates (`"[31"` at end of a traceback) —
 *     dropped, and scanning stops, because there is no more printable text;
 *   - a CSI that is not SGR (`"[2K"`) — consumed and ignored;
 *   - a bare `ESC` with no `[` — dropped, and the following character is kept.
 */
export function parseAnsi(text: string): AnsiSegment[] {
  const segments: AnsiSegment[] = [];
  let style: AnsiStyle = {};
  let cursor = 0;
  let plainFrom = 0;

  const flush = (until: number) => {
    if (until > plainFrom) {
      segments.push({ text: text.slice(plainFrom, until), style: { ...style } });
    }
  };

  while (cursor < text.length) {
    const escapeAt = text.indexOf(ESC, cursor);
    if (escapeAt === -1) break;
    if (text[escapeAt + 1] !== "[") {
      // Not a CSI: drop the escape byte alone and keep reading.
      flush(escapeAt);
      plainFrom = escapeAt + 1;
      cursor = escapeAt + 1;
      continue;
    }
    let end = escapeAt + 2;
    while (end < text.length && !/[@-~]/.test(text[end])) end += 1;
    if (end >= text.length) {
      // Unterminated: everything from the escape on is control noise.
      flush(escapeAt);
      plainFrom = text.length;
      cursor = text.length;
      break;
    }
    flush(escapeAt);
    if (text[end] === "m") {
      const body = text.slice(escapeAt + 2, end);
      const params = body.split(";").map((part) => (part === "" ? 0 : Number.parseInt(part, 10)));
      const next = { ...style };
      let at = 0;
      while (at < params.length) {
        if (Number.isNaN(params[at])) break;
        at += applySgr(next, params, at);
      }
      style = next;
    }
    plainFrom = end + 1;
    cursor = end + 1;
  }
  flush(text.length);
  return segments;
}

function styleOf(style: AnsiStyle): React.CSSProperties {
  return {
    color: style.color,
    backgroundColor: style.background,
    fontWeight: style.bold ? 600 : undefined,
    fontStyle: style.italic ? "italic" : undefined,
    textDecoration: style.underline ? "underline" : undefined,
    opacity: style.dim ? 0.7 : undefined,
  };
}

/** Text above this is truncated with a control to show all (spec §2 edge case). */
const TEXT_BOUND_CHARS = 4000;

export interface AnsiTextProps {
  text: string;
  testId: string;
  className?: string;
}

/** ANSI-styled text in a `<pre>`, truncated above the bound with a control. */
export function AnsiText({ text, testId, className }: AnsiTextProps) {
  const [expanded, setExpanded] = useState(false);
  const truncated = text.length > TEXT_BOUND_CHARS;
  const shown = truncated && !expanded ? text.slice(0, TEXT_BOUND_CHARS) : text;
  const segments = useMemo(() => parseAnsi(shown), [shown]);
  return (
    <div>
      <pre
        className={`overflow-x-auto whitespace-pre-wrap break-words font-mono text-[12px] leading-[17px] scrollbar-thin ${className ?? "text-stone-700"}`}
        data-testid={testId}
      >
        {segments.map((segment, index) => (
          // Regenerated whole on every text change and never reordered.
          // eslint-disable-next-line react/no-array-index-key
          <span key={index} style={styleOf(segment.style)}>
            {segment.text}
          </span>
        ))}
      </pre>
      {truncated && !expanded ? (
        <button
          className="text-[11px] text-blue-700 underline"
          data-testid={`${testId}-show-all`}
          onClick={() => setExpanded(true)}
          type="button"
        >
          Show all {text.length.toLocaleString()} characters
        </button>
      ) : null}
    </div>
  );
}

// -- the MIME bundle (FR-011) ----------------------------------------------

/** nbformat writes multiline payloads as a list of lines; both shapes arrive. */
function asText(value: unknown): string {
  if (typeof value === "string") return value;
  if (Array.isArray(value))
    return value.map((part) => (typeof part === "string" ? part : "")).join("");
  if (value === null || value === undefined) return "";
  return JSON.stringify(value, null, 2);
}

const IMAGE_TYPES = ["image/png", "image/jpeg", "image/gif", "image/webp"] as const;

/**
 * The MIME type to render, in the order the shell prefers them.
 *
 * The order is Jupyter's own preference — the richest representation the
 * surface can draw — with one exception: `text/plain` is last, because it is
 * the fallback every rich output also carries.
 */
export function pickMimeType(data: Record<string, unknown>): string | null {
  const available = Object.keys(data);
  for (const candidate of [...IMAGE_TYPES, "image/svg+xml", "text/html", "text/markdown"]) {
    if (available.includes(candidate)) return candidate;
  }
  if (available.includes("text/plain")) return "text/plain";
  return null;
}

/**
 * A sandboxed frame for HTML and SVG output (FR-011).
 *
 * `sandbox=""` grants nothing: no scripts, no same-origin access, no forms, no
 * popups, no top-level navigation. It is written as an empty attribute rather
 * than omitted, and the test asserts both that the attribute is present and
 * that it names neither `allow-scripts` nor `allow-same-origin` — an omitted
 * attribute would mean a frame with *every* permission.
 */
function SandboxedFrame({ html, testId }: { html: string; testId: string }) {
  return (
    <iframe
      className="h-60 w-full rounded border border-stone-200 bg-white"
      data-testid={testId}
      referrerPolicy="no-referrer"
      sandbox=""
      srcDoc={html}
      title="Cell output"
    />
  );
}

function RichOutput({ data, testId }: { data: Record<string, unknown>; testId: string }) {
  const mime = pickMimeType(data);
  if (mime === null) {
    const types = Object.keys(data);
    return (
      <p className="text-[11px] italic text-stone-500" data-testid={`${testId}-unrenderable`}>
        {types.length === 0
          ? "This output carries nothing the shell can render."
          : `No renderer for ${types.join(", ")}, and the output carries no plain text.`}
      </p>
    );
  }
  if ((IMAGE_TYPES as readonly string[]).includes(mime)) {
    const base64 = asText(data[mime]).replace(/\s+/g, "");
    return (
      <img
        alt="Cell output"
        className="max-w-full rounded border border-stone-200"
        data-mime={mime}
        data-testid={`${testId}-image`}
        src={`data:${mime};base64,${base64}`}
      />
    );
  }
  if (mime === "image/svg+xml" || mime === "text/html") {
    return <SandboxedFrame html={asText(data[mime])} testId={`${testId}-frame`} />;
  }
  if (mime === "text/markdown") {
    return (
      <div
        className="prose-sm max-w-none text-[13px] text-stone-700"
        data-testid={`${testId}-markdown`}
      >
        <Markdown remarkPlugins={[remarkGfm]}>{asText(data[mime])}</Markdown>
      </div>
    );
  }
  return <AnsiText testId={`${testId}-text`} text={asText(data[mime])} />;
}

function OneOutput({ output, testId }: { output: ExploreOutput; testId: string }) {
  if (output.output_type === "error") {
    const traceback = (output.traceback ?? []).join("\n");
    const text =
      traceback.length > 0 ? traceback : `${output.ename ?? "Error"}: ${output.evalue ?? ""}`;
    return (
      <div
        className="rounded border border-red-200 bg-red-50/60 px-2 py-1"
        data-testid={`${testId}-error`}
      >
        <AnsiText className="text-red-900" testId={`${testId}-traceback`} text={text} />
      </div>
    );
  }
  if (output.output_type === "stream") {
    const stderr = output.name === "stderr";
    return (
      <AnsiText
        className={stderr ? "text-red-800" : "text-stone-700"}
        testId={`${testId}-stream`}
        text={asText(output.text)}
      />
    );
  }
  if (output.data && Object.keys(output.data).length > 0) {
    return <RichOutput data={output.data} testId={testId} />;
  }
  // An output_type the shell does not know: fall back to whatever plain text it
  // carries, and say so plainly when it carries none (FR-011).
  const text = asText(output.text);
  if (text.length > 0) return <AnsiText testId={`${testId}-text`} text={text} />;
  return (
    <p className="text-[11px] italic text-stone-500" data-testid={`${testId}-unrenderable`}>
      No renderer for an output of type {output.output_type || "unknown"}.
    </p>
  );
}

export interface OutputRendererProps {
  cellId: string;
  outputs: readonly ExploreOutput[];
}

/** Every output of one cell, in the order the kernel produced them. */
export function OutputRenderer({ cellId, outputs }: OutputRendererProps) {
  if (outputs.length === 0) return null;
  return (
    <div className="mt-1 flex flex-col gap-1" data-testid={`explore-cell-outputs-${cellId}`}>
      {outputs.map((output, index) => (
        <div
          data-output-type={output.output_type}
          // Outputs have no ids of their own; the index is their identity and
          // the list is replaced whole by every `cell_output` event.
          // eslint-disable-next-line react/no-array-index-key
          key={index}
          data-testid={`explore-output-${cellId}-${index}`}
        >
          <OneOutput output={output} testId={`explore-output-${cellId}-${index}`} />
        </div>
      ))}
    </div>
  );
}

export default OutputRenderer;
