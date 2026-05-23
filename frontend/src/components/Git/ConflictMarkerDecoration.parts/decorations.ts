/**
 * Build Monaco model decorations from parsed conflict regions
 * (ADR-039 §3.5a).
 *
 * Extracted from `ConflictMarkerDecoration.ts` (#1422). Pure builder —
 * no side effects on the editor; the caller invokes
 * `editor.deltaDecorations` with the returned array.
 */

import type { ConflictRegion } from "./types";

/** Decoration descriptor shape consumed by `editor.deltaDecorations`. */
export interface DecorationDescriptor {
  range: {
    startLineNumber: number;
    startColumn: number;
    endLineNumber: number;
    endColumn: number;
  };
  options: Record<string, unknown>;
}

/**
 * Build decoration descriptors for every conflict region.
 *
 * @param regions - parsed conflict regions.
 * @param monaco  - Monaco namespace (loose typed). Required for
 *                  `monaco.Range` construction.
 */
export function buildDecorations(
  regions: ConflictRegion[],
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  monaco: any,
): DecorationDescriptor[] {
  return regions.flatMap((region) => {
    const out: DecorationDescriptor[] = [];
    const currentEnd = region.baseEndLine ?? region.currentEndLine;
    // current section: between `<<<<<<<` (exclusive) and ======= / |||||||  (exclusive)
    if (currentEnd - 1 > region.startLine) {
      out.push({
        range: new monaco.Range(region.startLine + 1, 1, currentEnd - 1, Number.MAX_SAFE_INTEGER),
        options: {
          isWholeLine: true,
          className: "conflict-current",
          // Light green-ish; Monaco supports CSS classes via the theme.
          inlineClassName: "conflict-current-inline",
          hoverMessage: { value: `Current: ${region.currentLabel}` },
        },
      });
    }
    // incoming section
    const incomingStart = region.baseEndLine !== null ? region.baseEndLine : region.currentEndLine;
    if (region.incomingEndLine - 1 > incomingStart) {
      out.push({
        range: new monaco.Range(
          incomingStart + 1,
          1,
          region.incomingEndLine - 1,
          Number.MAX_SAFE_INTEGER,
        ),
        options: {
          isWholeLine: true,
          className: "conflict-incoming",
          inlineClassName: "conflict-incoming-inline",
          hoverMessage: { value: `Incoming: ${region.incomingLabel}` },
        },
      });
    }
    // marker lines — number them in the gutter.
    out.push({
      range: new monaco.Range(region.startLine, 1, region.startLine, Number.MAX_SAFE_INTEGER),
      options: {
        isWholeLine: true,
        glyphMarginClassName: "conflict-marker-glyph",
      },
    });
    return out;
  });
}
