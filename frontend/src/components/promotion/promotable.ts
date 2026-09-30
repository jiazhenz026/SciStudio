// What can be promoted, and from where — the item model shared by every
// promotion entry point.
//
// Spec: docs/specs/adr-053-personal-tool-library.md
//   §6 FR-017 (promotion moves: the project's file is consumed), FR-019
//   (offered only for a
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
 * Every variant is a *read*. FR-017 makes promotion a move, but the removal
 * is the server's and happens only as part of the library write that replaces
 * the file — nothing reachable from this module can delete anything.
 */
export type PromotionSourceRef =
  /** A registered block, read through `GET /api/blocks/{type}/source`. */
  | { from: "block"; blockType: string }
  /** A project-relative file, read through `GET /api/projects/{id}/file`. */
  | { from: "projectFile"; path: string }
  /**
   * A whole panel directory — `{project}/panels/<panel_id>/` (ADR-054 FR-039).
   *
   * The odd one out, and deliberately so: a MiniApp is a directory, not a
   * file, so there is no content for the caller to read and hand back. The
   * move happens server-side in one call
   * (`POST /api/user-library/directory?target=panels&name=<panel_id>`, pinned
   * in the Phase D contract §1.2), which writes the library copy and then
   * removes the project copy under the same FR-017 rule every file promotion
   * follows, degrading to a copy when the removal fails.
   *
   * It is still a `PromotionSourceRef` rather than a second promotion path so
   * that FR-025 keeps holding: the entry point builds a `PromotableItem` and
   * nothing else, and the FR-019 origin rule that hides the action for a
   * non-project item is the same function for a MiniApp as for a block.
   */
  | { from: "panelDirectory"; panelId: string };

export interface PromotableItem {
  /** Which user library directory the copy lands in (FR-006). */
  target: UserLibraryTarget;
  kind: "block" | "type" | "previewer" | "miniapp";
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
  // Learning Center #2086: a project previewer promotes through the same
  // door as blocks and types. The editor tab is its one entry point — a
  // previewer has no palette card and no canvas node to hang E2/E5 on.
  { prefix: "previewers/", target: "previewers" },
];

/** The item kind each target's files register as. */
const KIND_FOR_TARGET: Record<UserLibraryTarget, PromotableItem["kind"]> = {
  blocks: "block",
  types: "type",
  previewers: "previewer",
  // ADR-054 FR-039 — `panels` has no `DROPIN_DIRS` entry on purpose: a MiniApp
  // is promoted from its card, never from an open editor tab, and treating
  // `panels/<id>/panel.py` as a promotable drop-in would promote one file out
  // of a directory that only works whole. The entry exists because this map is
  // exhaustive over `UserLibraryTarget`.
  panels: "miniapp",
};

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
 *    opened from the project tree and is editing. Its origin is inferred as
 *    `project` from the *shape of the path*: project-relative, and directly
 *    inside the project's own drop-in directory.
 *
 * That inference is a claim about the path, not the backend's answer, and the
 * two can disagree in exactly one case — FR-002's `custom` fallback, where a
 * file inside `blocks/` resolves, through a symlink or onto a different Windows
 * drive, to somewhere outside the project root. The backend calls that
 * `custom`, so the palette and the canvas node hide the action while this tab
 * still offers it (`docs/audit/2026-08-07-adr-053-spec1-track-b.md` P3-2).
 *
 * It stays an inference rather than becoming a lookup because there is nothing
 * to look up: `BlockSummary` deliberately carries no file path — the palette
 * listing does not publish an absolute path for every registered block — so the
 * editor cannot join a project-relative tab path back to a registered summary.
 * Publishing one to close a case the user reaches only by hand-making a symlink
 * inside their own project, whose worst outcome is copying their own file into
 * their own library, is not a trade worth making. The block source tab, which
 * *does* have a summary, uses the resolved origin rather than any inference.
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
    kind: KIND_FOR_TARGET[dropin.target],
    label: base.replace(/\.py$/i, ""),
    origin: "project",
    source: { from: "projectFile", path },
  };
}

/**
 * The fields a MiniApp listing entry has to carry to be promotable.
 *
 * Structurally the relevant half of `MiniAppSummary`
 * (`frontend/src/miniapps/types.ts`), declared here rather than imported so
 * this module keeps its one job — turning what the user is pointing at into a
 * `PromotableItem` — without taking on a dependency on the MiniApp client.
 */
export interface PromotableMiniApp {
  panel_id: string;
  name: string;
  tier: "project" | "user" | "package" | "core";
}

/**
 * The promotable record for a MiniApp card (ADR-054 FR-039).
 *
 * The tier the listing reports *is* the resolved origin — the backend decides
 * which of the four roots a panel directory was discovered under — so FR-019
 * needs no second reading of it here: only a `project` MiniApp is offered the
 * action, exactly as only a project block is.
 */
export function promotableMiniApp(miniapp: PromotableMiniApp): PromotableItem {
  return {
    target: "panels",
    kind: "miniapp",
    label: miniapp.name,
    origin: miniapp.tier,
    source: { from: "panelDirectory", panelId: miniapp.panel_id },
  };
}

/**
 * The fields a preview panel card in All Previewers has to carry to be promotable.
 *
 * Structurally the relevant half of `PreviewerSpecSummary`, declared here for
 * the same reason as {@link PromotableMiniApp}.
 */
export interface PromotablePreviewPanel {
  owner_kind: "project" | "user" | "package" | "core";
  panel?: { id: string; contexts: string[]; name?: string };
}

/**
 * The promotable record for a preview panel card in All Previewers, or `null`.
 *
 * A preview panel is a directory like a MiniApp, so it moves through the same
 * directory promotion; only the kind differs, which is what the confirmation
 * names it as. `null` for a legacy previewer and for a panel that is not
 * written for the preview context: the first is a file this entry point never
 * addresses, and the second is not something All Previewers lists as a
 * preview. The owner kind is the resolved origin, as the MiniApp tier is, so
 * FR-019 still hides the action for anything outside the project.
 */
export function promotablePreviewPanel(previewer: PromotablePreviewPanel): PromotableItem | null {
  const panel = previewer.panel;
  if (!panel || !panel.contexts.includes("preview")) return null;
  return {
    target: "panels",
    kind: "previewer",
    label: panel.name || panel.id,
    origin: previewer.owner_kind,
    source: { from: "panelDirectory", panelId: panel.id },
  };
}
