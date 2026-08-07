// What can be promoted, and from where — the item model shared by every
// promotion entry point.
//
// Spec: docs/specs/adr-053-personal-tool-library.md
//   §6 FR-017 (promotion copies, never moves), FR-019 (offered only for a
//   resolved origin of `project`; hidden, not disabled, otherwise),
//   §6.2 FR-025 (E1, E2, E3 and E5 share one implementation).
//
// Each entry point resolves what the user is pointing at into one
// `PromotableItem` and hands it to `promoteToUserLibrary`. That is the whole
// of the per-entry-point code: the editor toolbar knows about file tabs, the
// canvas node knows about `BlockNodeData`, and the palette popovers know about
// summaries, but none of them knows anything about promotion beyond building
// this record. Four copies of the promotion logic is exactly the drift the
// spec is written to avoid, and the way to not have four copies is for the
// four call sites to differ only in this function.
//
// Kept free of React and of the API client so the FR-019 visibility rule is
// unit-testable as a pure function.

import type { BlockOrigin, BlockSummary, TypeOrigin, TypeSummary } from "../../types/api";
import type { UserLibraryTarget } from "../../types/api";
import type { FileTab } from "../../store/types";
import { resolveBlockOrigin } from "../BlockPalette.parts/paletteModel";

/**
 * Where the bytes to copy come from.
 *
 * Promotion copies (FR-017), so every variant is a *read* of something that
 * stays exactly where it is. Nothing here can move or delete a file.
 */
export type PromotionSourceRef =
  /** A registered block, read through `GET /api/blocks/{type}/source`. */
  | { from: "block"; blockType: string }
  /** A project-relative file, read through `GET /api/projects/{id}/file`. */
  | { from: "projectFile"; path: string };

export interface PromotableItem {
  /** Which user library directory the copy lands in (FR-006). */
  target: UserLibraryTarget;
  kind: "block" | "type";
  /** Name shown in the confirmation dialog and the success confirmation. */
  label: string;
  /** The resolved origin the FR-019 condition tests. */
  origin: BlockOrigin | TypeOrigin;
  source: PromotionSourceRef;
}

/**
 * FR-019 — promotion is offered only for a **resolved origin of `project`**.
 *
 * Not the tier-1 classification: a user-library block is also tier-1 with a
 * resolvable `file_path`, so the broader test would offer promotion for an
 * item that is already promoted, and the promotion would copy a file onto
 * itself and raise a meaningless overwrite prompt. Built-in and packaged items
 * already live in a library. In all three cases the action is **hidden**, and
 * every entry point hides it by rendering nothing when this returns `false` —
 * never by rendering a disabled control, which would advertise an action that
 * can never become available.
 */
export function isPromotableOrigin(origin: BlockOrigin | TypeOrigin): boolean {
  return origin === "project";
}

/** {@link isPromotableOrigin} for a nullable item, for render-time gating. */
export function isPromotable(item: PromotableItem | null): item is PromotableItem {
  return item !== null && isPromotableOrigin(item.origin);
}

/** The promotable record for a palette / canvas block, or `null`. */
export function promotableBlock(block: BlockSummary): PromotableItem {
  return {
    target: "blocks",
    kind: "block",
    label: block.name,
    origin: resolveBlockOrigin(block),
    source: { from: "block", blockType: block.type_name },
  };
}

/**
 * The promotable record for a registered data type, or `null` when its file
 * cannot be located.
 *
 * A project-tier type lives at `{project}/types/<file>.py` by construction
 * (`scistudio.core.dropins.project_types_dir`), so the project-relative path
 * the file read needs is derivable from the absolute `file_path` the listing
 * reports. A type with no `file_path` resolves to origin `custom` and is not
 * promotable anyway; returning `null` keeps that a single check.
 */
export function promotableType(type: TypeSummary): PromotableItem | null {
  const base = type.file_path ? (type.file_path.split(/[\\/]/).pop() ?? "") : "";
  if (!base.toLowerCase().endsWith(".py")) {
    return null;
  }
  return {
    target: "types",
    kind: "type",
    label: type.name,
    origin: type.origin,
    source: { from: "projectFile", path: `types/${base}` },
  };
}

/** Project-relative drop-in directory → the user library target it promotes to. */
const DROPIN_DIRS: ReadonlyArray<{ prefix: string; target: UserLibraryTarget }> = [
  { prefix: "blocks/", target: "blocks" },
  { prefix: "types/", target: "types" },
];

/**
 * The promotable record for the file open in the editor (entry point E1), or
 * `null` when the active tab is not a promotable drop-in.
 *
 * Two tab shapes reach the block source editor and both are handled here:
 *
 *  - A **block source tab** (`blockSourceType`, opened by "View source"). Its
 *    origin comes from the registered summary, because the tab's own path is
 *    an absolute module path that may resolve anywhere.
 *  - A **project file tab** under `blocks/` or `types/` — the file the user
 *    opened from the project tree and is editing. Its origin is `project` by
 *    construction: the path is project-relative and inside the project's own
 *    drop-in directory, which is the definition of the project tier.
 */
export function promotableFileTab(
  tab: FileTab | null,
  blocks: readonly BlockSummary[],
): PromotableItem | null {
  if (!tab) return null;
  if (tab.blockSourceType) {
    const summary = blocks.find((block) => block.type_name === tab.blockSourceType);
    return summary ? promotableBlock(summary) : null;
  }
  const path = tab.filePath.replace(/\\/g, "/");
  if (!path.toLowerCase().endsWith(".py")) return null;
  const dropin = DROPIN_DIRS.find((entry) => path.startsWith(entry.prefix));
  if (!dropin) return null;
  const base = path.slice(dropin.prefix.length);
  // Only a file sitting directly in the drop-in directory is a drop-in; a
  // nested `blocks/vendor/x.py` is not scanned as one and must not claim to be.
  if (base.includes("/") || base.length === 0) return null;
  return {
    target: dropin.target,
    kind: dropin.target === "blocks" ? "block" : "type",
    label: base.replace(/\.py$/i, ""),
    origin: "project",
    source: { from: "projectFile", path },
  };
}
