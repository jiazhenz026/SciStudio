/**
 * Pure conflict-marker parser + resolver for ADR-039 §3.5a.
 *
 * Extracted from `ConflictMarkerDecoration.ts` (#1422). No Monaco
 * dependency — unit-test friendly in isolation.
 *
 * See `ConflictMarkerDecoration.ts` for the algorithm narrative; this
 * module is the executable form of the parser-algorithm + resolver
 * documented there.
 */

import type { ConflictAction, ConflictRegion } from "./types";

type ParserState = "outside" | "in_current" | "in_base" | "in_incoming";

interface PartialRegion {
  startLine: number;
  currentEndLine: number;
  baseEndLine: number | null;
  currentLabel: string;
}

interface ParserContext {
  state: ParserState;
  partial: PartialRegion | null;
  out: ConflictRegion[];
}

function newPartial(lineNo: number, line: string): PartialRegion {
  return {
    startLine: lineNo,
    currentEndLine: -1,
    baseEndLine: null,
    currentLabel: line.slice(7).trim() || "current",
  };
}

/**
 * Apply the marker found on `line` to the in-flight parser context.
 * Splitting the per-line transitions out of the main loop keeps the
 * loop's cyclomatic complexity within the ESLint `complexity: 15` cap.
 *
 * @returns `true` when a marker was matched and the context mutated;
 *          `false` for non-marker content lines.
 */
function applyMarker(ctx: ParserContext, line: string, lineNo: number): boolean {
  if (ctx.state === "outside" && line.startsWith("<<<<<<<")) {
    ctx.partial = newPartial(lineNo, line);
    ctx.state = "in_current";
    return true;
  }
  if (ctx.state === "in_current" && line.startsWith("|||||||")) {
    if (ctx.partial) ctx.partial.currentEndLine = lineNo;
    ctx.state = "in_base";
    return true;
  }
  if ((ctx.state === "in_current" || ctx.state === "in_base") && line.startsWith("=======")) {
    closeCurrentSection(ctx, lineNo);
    ctx.state = "in_incoming";
    return true;
  }
  if (ctx.state === "in_incoming" && line.startsWith(">>>>>>>")) {
    closeRegion(ctx, lineNo, line);
    return true;
  }
  if (ctx.state !== "outside" && line.startsWith("<<<<<<<")) {
    // Defensive: a new `<<<<<<<` while already inside a region.
    // Abandon the in-flight partial and start over.
    console.warn(
      `ConflictMarkerDecoration: unexpected nested '<<<<<<<' at line ${lineNo}; ` +
        "abandoning prior partial region.",
    );
    ctx.partial = newPartial(lineNo, line);
    ctx.state = "in_current";
    return true;
  }
  return false;
}

function closeCurrentSection(ctx: ParserContext, lineNo: number): void {
  if (!ctx.partial) return;
  if (ctx.state === "in_base") {
    ctx.partial.baseEndLine = lineNo;
  } else {
    ctx.partial.currentEndLine = lineNo;
    ctx.partial.baseEndLine = null;
  }
}

function closeRegion(ctx: ParserContext, lineNo: number, line: string): void {
  if (ctx.partial) {
    ctx.out.push({
      startLine: ctx.partial.startLine,
      currentEndLine: ctx.partial.currentEndLine,
      baseEndLine: ctx.partial.baseEndLine,
      incomingEndLine: lineNo,
      currentLabel: ctx.partial.currentLabel,
      incomingLabel: line.slice(7).trim() || "incoming",
    });
  }
  ctx.partial = null;
  ctx.state = "outside";
}

/**
 * Parse conflict regions from a file's text content. Pure function —
 * no Monaco dependency.
 *
 * @param content - the full file text (newline-separated).
 * @returns Array of detected regions in source order. Returns [] if
 *          no conflict markers are present or all detected regions
 *          are malformed.
 */
export function parseConflictRegions(content: string): ConflictRegion[] {
  if (!content) return [];
  const lines = content.split("\n");
  const ctx: ParserContext = { state: "outside", partial: null, out: [] };

  for (let i = 0; i < lines.length; i++) {
    applyMarker(ctx, lines[i], i + 1);
  }

  // If we reach EOF mid-region, drop it with a warn.
  if (ctx.state !== "outside") {
    console.warn(
      `ConflictMarkerDecoration: unclosed conflict region starting at line ` +
        `${ctx.partial?.startLine ?? "?"}; discarding.`,
    );
  }

  return ctx.out;
}

/**
 * Splice a `ConflictAction` into a Monaco model: replaces the conflict
 * region (lines `region.startLine..region.incomingEndLine` inclusive)
 * with the resolved text per `action.type`.
 *
 * Pure-ish helper: takes the raw model text, returns the rewritten text.
 * The Monaco-aware version below applies the edit through Monaco's edit
 * stack so undo works.
 */
export function resolveRegionText(
  fullText: string,
  region: ConflictRegion,
  action: ConflictAction,
): string {
  const lines = fullText.split("\n");
  // 1-based → 0-based slice indices.
  const beforeLines = lines.slice(0, region.startLine - 1);
  const afterLines = lines.slice(region.incomingEndLine);

  // Section boundaries (1-based line numbers from the parser):
  //
  // 2-way style:
  //   startLine                              (marker `<<<<<<<`)
  //   startLine+1 .. currentEndLine-1       (current section)
  //   currentEndLine                         (marker `=======`)
  //   currentEndLine+1 .. incomingEndLine-1 (incoming section)
  //   incomingEndLine                        (marker `>>>>>>>`)
  //
  // diff3 style:
  //   startLine                              (marker `<<<<<<<`)
  //   startLine+1 .. currentEndLine-1       (current section)
  //   currentEndLine                         (marker `|||||||`)
  //   currentEndLine+1 .. baseEndLine-1     (base section — not echoed)
  //   baseEndLine                            (marker `=======`)
  //   baseEndLine+1 .. incomingEndLine-1    (incoming section)
  //   incomingEndLine                        (marker `>>>>>>>`)
  //
  // Codex P1 (PR #952): the current section ALWAYS ends at
  // `currentEndLine` (whether that's `=======` in 2-way or `|||||||` in
  // diff3). The previous impl conflated diff3's `=======` with the end
  // of the current section, which caused `accept_current` /
  // `accept_both` to splice the diff3 marker + base block into the
  // resolved file — leaving malformed text that git refused to stage.
  const currentSection = lines.slice(region.startLine, region.currentEndLine - 1);
  // Incoming section starts after the `=======` marker:
  //   - 2-way: that's `currentEndLine`
  //   - diff3: that's `baseEndLine` (since `currentEndLine` is `|||||||`)
  const incomingMarkerLine =
    region.baseEndLine !== null ? region.baseEndLine : region.currentEndLine;
  const incomingSection = lines.slice(incomingMarkerLine, region.incomingEndLine - 1);

  let resolved: string[];
  switch (action.type) {
    case "accept_current":
      resolved = currentSection;
      break;
    case "accept_incoming":
      resolved = incomingSection;
      break;
    case "accept_both":
      resolved = [...currentSection, ...incomingSection];
      break;
    case "manual_edit":
      // No-op: leave the markers in place; the user wants to edit by hand.
      return fullText;
    default:
      return fullText;
  }

  return [...beforeLines, ...resolved, ...afterLines].join("\n");
}
