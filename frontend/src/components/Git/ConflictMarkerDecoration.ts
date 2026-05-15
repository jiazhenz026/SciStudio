/**
 * ADR-039 §3.5a / §6 Phase 3 — Monaco decoration provider for git
 * conflict markers (SKELETON).
 *
 * Status: SKELETON. The entry point `registerConflictDecorations` throws
 * `Error("TODO: D39-2.4b — ...")`. The pure conflict-region detector
 * `parseConflictRegions` is filled in (no Monaco dependency, useful in
 * isolation in unit tests).
 *
 * ============================================================================
 * PURPOSE
 * ============================================================================
 *
 * When a git merge produces conflicts, git writes the conflicting files
 * in-place with the textual markers:
 *
 *   <<<<<<< HEAD
 *   ... current branch's version ...
 *   =======
 *   ... incoming branch's version ...
 *   >>>>>>> source-branch-name
 *
 * (Optionally, with `merge.conflictStyle=diff3`, a third section between
 *  `<<<<<<<` and `=======`:
 *
 *   <<<<<<< HEAD
 *   ... current ...
 *   ||||||| merged common ancestors
 *   ... base ...
 *   =======
 *   ... incoming ...
 *   >>>>>>> source
 *
 *  SciEasy does NOT enable diff3 by default in v1; we handle it
 *  gracefully if the user's git config is set this way.)
 *
 * This module registers Monaco decorations to:
 *
 *   1. Highlight the "current" section with a subtle green background.
 *   2. Highlight the "incoming" section with a subtle blue background.
 *   3. Render inline glyph-margin action buttons above each conflict:
 *        [Accept Current] [Accept Incoming] [Accept Both] [Manual edit]
 *   4. Number conflicts ("1 of 3", "2 of 3") in the glyph margin so the
 *      user can navigate.
 *
 * VS Code itself shipped with this exact UX for years before adding the
 * dedicated 3-way merge editor in 2022. We adopt the same model per
 * ADR-039 §3.5a "no new editor; no third-party 3-way merge component".
 *
 * ============================================================================
 * MONACO INTEGRATION CONTRACT
 * ============================================================================
 *
 * Monaco is loaded lazily by `CodeEditor.tsx` (see ADR-036 §3.1). This
 * module exposes:
 *
 *   registerConflictDecorations(
 *     editor:   monaco.editor.IStandaloneCodeEditor,
 *     monaco:   typeof import("monaco-editor"),
 *     onAction: (action: ConflictAction, region: ConflictRegion) => void,
 *   ): () => void                                // dispose function
 *
 * The caller (`CodeEditor.tsx`) invokes this AFTER the editor is mounted
 * AND `mergeInProgress?.conflicted_files.includes(activeFile)` is true.
 * The returned dispose function unregisters listeners + clears decorations
 * when the file leaves conflict state.
 *
 * The Monaco types are intentionally typed as `unknown` / `any` in the
 * skeleton signature so we don't statically depend on `monaco-editor`
 * (which lives behind the lazy boundary). D39-2.4b will tighten this
 * to `monaco.editor.IStandaloneCodeEditor` if the impl agent can do so
 * without breaking lazy-load.
 *
 * ============================================================================
 * CONFLICT-REGION DATA SHAPE
 * ============================================================================
 *
 *   interface ConflictRegion {
 *     startLine:        number;  // 1-based; the line containing `<<<<<<<`
 *     currentEndLine:   number;  // 1-based; the line containing `=======`
 *                                // (or the diff3 `|||||||` line if diff3)
 *     baseEndLine:      number | null;  // diff3 only — line with `=======`
 *     incomingEndLine:  number;  // 1-based; the line containing `>>>>>>>`
 *     currentLabel:     string;  // e.g. "HEAD" or branch name from the marker
 *     incomingLabel:    string;  // e.g. "source-branch-name"
 *   }
 *
 *   interface ConflictAction { type: "accept_current" | "accept_incoming" |
 *                                     "accept_both" | "manual_edit"; }
 *
 * ============================================================================
 * PARSER ALGORITHM (kept in the skeleton — no Monaco dep)
 * ============================================================================
 *
 * Scan lines top-down with a small state machine:
 *
 *   state = "outside" | "in_current" | "in_base" | "in_incoming"
 *
 *   for (i = 0; i < lines.length; i++) {
 *     line = lines[i]
 *     if (state === "outside" && line.startsWith("<<<<<<<")) {
 *       region.startLine = i + 1
 *       region.currentLabel = line.slice(7).trim() || "current"
 *       state = "in_current"
 *     } else if (state === "in_current" && line.startsWith("|||||||")) {
 *       region.currentEndLine = i + 1
 *       state = "in_base"
 *     } else if ((state === "in_current" || state === "in_base") &&
 *                 line.startsWith("=======")) {
 *       if (state === "in_base") {
 *         region.baseEndLine = i + 1
 *       } else {
 *         region.currentEndLine = i + 1
 *         region.baseEndLine = null
 *       }
 *       state = "in_incoming"
 *     } else if (state === "in_incoming" && line.startsWith(">>>>>>>")) {
 *       region.incomingEndLine = i + 1
 *       region.incomingLabel = line.slice(7).trim() || "incoming"
 *       emit(region); region = {}; state = "outside"
 *     }
 *   }
 *
 * Malformed input (unclosed region, `=======` outside a region, etc.)
 * is logged with `console.warn` and the partial region is discarded.
 * Real git output is well-formed; we only see malformed input if the
 * user mid-edited the markers.
 *
 * Worst-case: O(L) line scan, O(R) regions; both bounded by file size.
 *
 * ============================================================================
 * EDGE CASES
 * ============================================================================
 *
 *   1. EMPTY CONTENT  → no regions; no decorations registered.
 *   2. NO MARKERS     → no regions; no decorations registered.
 *   3. NESTED MARKERS → git produces flat, never nested. If we encounter
 *      a `<<<<<<<` while inside a region, abandon the current region with
 *      a warn and start a new one. Defensive only — real git doesn't
 *      generate this.
 *   4. DIFF3 STYLE    → handled by the `|||||||` branch above.
 *   5. CARRIAGE RETURNS (Windows CRLF) → the parser splits on "\n"; the
 *      `<<<<<<<` etc. are at the start of the line, so trailing "\r" is
 *      benign. The `currentLabel` slice may pick up a trailing "\r"; the
 *      `.trim()` strips it.
 *   6. USER EDITS MID-CONFLICT — once the user types text into a region,
 *      Monaco fires onChange; D39-2.4b: re-run `parseConflictRegions`
 *      to keep decorations aligned. If the user deletes a marker, the
 *      region collapses naturally on re-parse.
 *
 * ============================================================================
 * INTEGRATION
 * ============================================================================
 *
 *   - `CodeEditor.tsx` (extended in this skeleton): registers on mount
 *     IF `gitSlice.mergeInProgress?.conflicted_files.includes(filePath)`.
 *     The dispose function is called on unmount or when the file leaves
 *     conflict state.
 *
 *   - `ConflictResolveView.tsx`: receives `ConflictAction` events via
 *     the `onAction` callback and dispatches `gitMergeStageFile(file)` on
 *     "Mark Resolved" after all regions are handled.
 *
 * ============================================================================
 */

/**
 * A single parsed conflict region. Lines are 1-based (Monaco
 * convention). Whole-file character offsets are NOT included; the
 * decoration provider derives them from Monaco's `model.getLineContent`.
 */
export interface ConflictRegion {
  /** 1-based: the line containing `<<<<<<<`. */
  startLine: number;
  /**
   * 1-based: in default 2-way style this is the `=======` line; in
   * diff3 style this is the `|||||||` line.
   */
  currentEndLine: number;
  /**
   * Diff3 only: the `=======` line. `null` for default 2-way style.
   */
  baseEndLine: number | null;
  /** 1-based: the `>>>>>>>` line. */
  incomingEndLine: number;
  /** Branch label after `<<<<<<<`, or "current" if absent. */
  currentLabel: string;
  /** Branch label after `>>>>>>>`, or "incoming" if absent. */
  incomingLabel: string;
}

/** Actions a user can invoke on a conflict region. */
export interface ConflictAction {
  type: "accept_current" | "accept_incoming" | "accept_both" | "manual_edit";
}

/**
 * Parse conflict regions from a file's text content. Pure function —
 * no Monaco dependency. KEPT IMPLEMENTED in the skeleton (not a TODO)
 * because it has no external dependency and is unit-test friendly.
 *
 * @param content - the full file text (newline-separated).
 * @returns Array of detected regions in source order. Returns [] if
 *          no conflict markers are present or all detected regions
 *          are malformed.
 */
export function parseConflictRegions(content: string): ConflictRegion[] {
  if (!content) return [];
  const lines = content.split("\n");
  const out: ConflictRegion[] = [];

  // Partial region accumulator. We only push to `out` once a region is
  // fully closed by a `>>>>>>>` marker.
  type Partial = {
    startLine: number;
    currentEndLine: number;
    baseEndLine: number | null;
    currentLabel: string;
  };
  let state: "outside" | "in_current" | "in_base" | "in_incoming" = "outside";
  let partial: Partial | null = null;

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const lineNo = i + 1;
    if (state === "outside" && line.startsWith("<<<<<<<")) {
      partial = {
        startLine: lineNo,
        currentEndLine: -1,
        baseEndLine: null,
        currentLabel: line.slice(7).trim() || "current",
      };
      state = "in_current";
    } else if (state === "in_current" && line.startsWith("|||||||")) {
      if (partial) partial.currentEndLine = lineNo;
      state = "in_base";
    } else if (
      (state === "in_current" || state === "in_base") &&
      line.startsWith("=======")
    ) {
      if (partial) {
        if (state === "in_base") {
          partial.baseEndLine = lineNo;
        } else {
          partial.currentEndLine = lineNo;
          partial.baseEndLine = null;
        }
      }
      state = "in_incoming";
    } else if (state === "in_incoming" && line.startsWith(">>>>>>>")) {
      if (partial) {
        out.push({
          startLine: partial.startLine,
          currentEndLine: partial.currentEndLine,
          baseEndLine: partial.baseEndLine,
          incomingEndLine: lineNo,
          currentLabel: partial.currentLabel,
          incomingLabel: line.slice(7).trim() || "incoming",
        });
      }
      partial = null;
      state = "outside";
    } else if (state !== "outside" && line.startsWith("<<<<<<<")) {
      // Defensive: a new `<<<<<<<` while already inside a region.
      // Abandon the in-flight partial and start over.
      console.warn(
        `ConflictMarkerDecoration: unexpected nested '<<<<<<<' at line ${lineNo}; ` +
          "abandoning prior partial region.",
      );
      partial = {
        startLine: lineNo,
        currentEndLine: -1,
        baseEndLine: null,
        currentLabel: line.slice(7).trim() || "current",
      };
      state = "in_current";
    }
  }

  // If we reach EOF mid-region, drop it with a warn.
  if (state !== "outside") {
    console.warn(
      `ConflictMarkerDecoration: unclosed conflict region starting at line ` +
        `${partial?.startLine ?? "?"}; discarding.`,
    );
  }

  return out;
}

/**
 * Register conflict-marker decorations + inline action widgets on a
 * Monaco editor instance.
 *
 * D39-2.4a SKELETON: throws on call. D39-2.4b IMPL: implement per the
 * docstring above. The returned dispose function MUST clear decorations
 * AND unregister all listeners — failure to do so leaks DOM nodes when
 * the user switches tabs.
 *
 * @param editor   - The Monaco IStandaloneCodeEditor (typed loose so we
 *                   stay behind the lazy-load boundary).
 * @param monaco   - The Monaco namespace, also typed loose.
 * @param onAction - Callback fired when the user clicks an inline
 *                   action button. The dispatcher (likely
 *                   `ConflictResolveView.tsx`) applies the text mutation
 *                   to the model.
 * @returns A dispose function that removes all decorations + listeners.
 */
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

  // Extract the three (or two) text sections.
  // 2-way:
  //   startLine                            (marker `<<<<<<<`)
  //   startLine+1 .. currentEndLine-1     (current section)
  //   currentEndLine                       (marker `=======`)
  //   currentEndLine+1 .. incomingEndLine-1 (incoming section)
  //   incomingEndLine                      (marker `>>>>>>>`)
  // diff3:
  //   startLine                            (marker `<<<<<<<`)
  //   startLine+1 .. currentEndLine-1     (current section)
  //   currentEndLine                       (marker `|||||||`)
  //   currentEndLine+1 .. baseEndLine-1   (base section)
  //   baseEndLine                          (marker `=======`)
  //   baseEndLine+1 .. incomingEndLine-1  (incoming section)
  //   incomingEndLine                      (marker `>>>>>>>`)
  const currentEnd = region.baseEndLine ?? region.currentEndLine;
  const currentSection = lines.slice(region.startLine, currentEnd - 1);
  const baseStart = region.baseEndLine !== null ? region.baseEndLine : null;
  const incomingStart =
    region.baseEndLine !== null ? region.baseEndLine : region.currentEndLine;
  const incomingSection = lines.slice(incomingStart, region.incomingEndLine - 1);
  void baseStart; // present for completeness; the impl never echoes base

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

/**
 * Register conflict-marker decorations + glyph-margin action widgets on
 * a Monaco editor instance.
 *
 * Layered behavior:
 *   1. Highlight the current section (green) + incoming section (blue)
 *      via `editor.deltaDecorations`.
 *   2. Mount one `IContentWidget` above each region with four buttons:
 *      Accept Current / Accept Incoming / Accept Both / Manual edit.
 *   3. On the editor's content-change event, re-parse and re-apply.
 *   4. The returned dispose function clears decorations + widgets + the
 *      change listener.
 *
 * The Monaco types are kept loose (`any`) to preserve the lazy-load
 * boundary from ADR-036 §3.1 (we cannot statically import `monaco-editor`
 * without breaking the bundle split).
 */
export function registerConflictDecorations(
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  editor: any,
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  monaco: any,
  onAction: (action: ConflictAction, region: ConflictRegion) => void,
): () => void {
  if (!editor || !monaco) {
    return () => {};
  }
  const model = editor.getModel?.();
  if (!model) {
    return () => {};
  }

  let decorationIds: string[] = [];
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const widgets: any[] = [];

  function clearWidgets() {
    for (const w of widgets) {
      try {
        editor.removeContentWidget(w);
      } catch {
        /* ignore */
      }
    }
    widgets.length = 0;
  }

  function clearDecorations() {
    try {
      decorationIds = editor.deltaDecorations(decorationIds, []);
    } catch {
      decorationIds = [];
    }
  }

  function buildWidget(region: ConflictRegion, indexLabel: string) {
    const dom = document.createElement("div");
    dom.className =
      "conflict-action-widget flex gap-2 px-2 py-0.5 text-[11px] " +
      "bg-stone-100 border border-stone-300 rounded shadow-sm";
    dom.dataset.testid = `conflict-action-${region.startLine}`;
    dom.setAttribute("aria-label", `Conflict region ${indexLabel}`);

    const mkBtn = (
      label: string,
      type: ConflictAction["type"],
      testid: string,
    ) => {
      const b = document.createElement("button");
      b.type = "button";
      b.textContent = label;
      b.dataset.testid = testid;
      b.className =
        "rounded border border-stone-400 bg-white px-1.5 py-0.5 " +
        "hover:bg-stone-50";
      b.addEventListener("click", (ev) => {
        ev.preventDefault();
        ev.stopPropagation();
        onAction({ type }, region);
      });
      return b;
    };

    const label = document.createElement("span");
    label.textContent = `Conflict ${indexLabel}`;
    label.className = "mr-2 font-semibold text-stone-600";
    dom.appendChild(label);
    dom.appendChild(
      mkBtn(
        "Accept Current",
        "accept_current",
        `conflict-accept-current-${region.startLine}`,
      ),
    );
    dom.appendChild(
      mkBtn(
        "Accept Incoming",
        "accept_incoming",
        `conflict-accept-incoming-${region.startLine}`,
      ),
    );
    dom.appendChild(
      mkBtn(
        "Accept Both",
        "accept_both",
        `conflict-accept-both-${region.startLine}`,
      ),
    );
    dom.appendChild(
      mkBtn("Manual edit", "manual_edit", `conflict-manual-${region.startLine}`),
    );

    return {
      getId: () => `conflict-widget-${region.startLine}`,
      getDomNode: () => dom,
      getPosition: () => ({
        position: { lineNumber: region.startLine, column: 1 },
        preference: [
          // ABOVE — Monaco's enum value for ContentWidgetPositionPreference.ABOVE.
          // The values are stable: ABOVE=1, BELOW=2, EXACT=0. Use the
          // enum if available, else fall back to the numeric literal.
          monaco.editor?.ContentWidgetPositionPreference?.ABOVE ?? 1,
          monaco.editor?.ContentWidgetPositionPreference?.BELOW ?? 2,
        ],
      }),
    };
  }

  function refresh() {
    clearWidgets();
    const text = model.getValue();
    const regions = parseConflictRegions(text);

    if (regions.length === 0) {
      clearDecorations();
      return;
    }

    // Build decorations. Use raw class names; CodeEditor consumers can
    // theme via global CSS hooks `.conflict-current` / `.conflict-incoming`.
    const decorations = regions.flatMap((region) => {
      const out: Array<{
        range: { startLineNumber: number; startColumn: number; endLineNumber: number; endColumn: number };
        options: Record<string, unknown>;
      }> = [];
      const currentEnd = region.baseEndLine ?? region.currentEndLine;
      // current section: between `<<<<<<<` (exclusive) and ======= / |||||||  (exclusive)
      if (currentEnd - 1 > region.startLine) {
        out.push({
          range: new monaco.Range(
            region.startLine + 1,
            1,
            currentEnd - 1,
            Number.MAX_SAFE_INTEGER,
          ),
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
      const incomingStart =
        region.baseEndLine !== null ? region.baseEndLine : region.currentEndLine;
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
        range: new monaco.Range(
          region.startLine,
          1,
          region.startLine,
          Number.MAX_SAFE_INTEGER,
        ),
        options: {
          isWholeLine: true,
          glyphMarginClassName: "conflict-marker-glyph",
        },
      });
      return out;
    });

    try {
      decorationIds = editor.deltaDecorations(decorationIds, decorations);
    } catch (err) {
      console.warn("ConflictMarkerDecoration: failed to set decorations", err);
    }

    // Build widgets.
    regions.forEach((region, i) => {
      const widget = buildWidget(region, `${i + 1} of ${regions.length}`);
      try {
        editor.addContentWidget(widget);
        widgets.push(widget);
      } catch (err) {
        console.warn("ConflictMarkerDecoration: failed to add widget", err);
      }
    });
  }

  // Listen for content changes so the decorations follow user edits.
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  let disposable: { dispose: () => void } | null = null;
  try {
    disposable = model.onDidChangeContent(() => {
      refresh();
    });
  } catch {
    disposable = null;
  }

  refresh();

  return function dispose() {
    try {
      disposable?.dispose();
    } catch {
      /* ignore */
    }
    clearWidgets();
    clearDecorations();
  };
}
