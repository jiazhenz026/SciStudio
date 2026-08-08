// **The** promotion action (ADR-053 §6.2 FR-025).
//
// Spec: docs/specs/adr-053-personal-tool-library.md
//   §6   FR-017 (copy, never move), FR-018 (a collision prompts with overwrite
//        and save-as-new-name; silent overwrite is forbidden), FR-019 (offered
//        only for a resolved origin of `project`), FR-020 (confirm inline and
//        reveal the item in its new palette section),
//   §6.1 FR-021 – FR-024 (cascade),
//   §6.2 FR-025 (E1, E2, E3 and E5 share one implementation, including
//        collision prompting and cascade).
//
// E3 — the agent's `promote_to_user_library` MCP tool — is the fourth caller
// and lives on the backend, so FR-025's "one implementation" is one *per
// process*: this module is the frontend's, and its semantics are the same
// contract as the tool's, refusal for refusal. The two refusal halves agree
// because they are now the *same condition* rather than two readings of it:
// `isPromotableOrigin` tests the resolved origin, and the tool tests the same
// origin resolved by the same function — `map_block_origin` in
// `scistudio.core.origins`, which is also what fills `BlockSummary.origin`.
//
//   | E3 (`tools_library.py`)                      | here                       |
//   |----------------------------------------------|----------------------------|
//   | resolved origin `builtin` → refused          | FR-019 hides the action    |
//   | resolved origin `package` → refused          | FR-019 hides the action    |
//   | resolved origin `user` → refused             | FR-019 hides the action    |
//   | resolved origin `custom` → refused           | FR-019 hides the action    |
//   | existing destination → `FileExistsError`     | 409 → FR-018 prompt        |
//   | `overwrite=True`                             | "Overwrite"                |
//   | `new_name='<other>.py'`                      | "Save as new name"         |
//   | copies; the project keeps its file           | copies (FR-017)            |
//
// The `custom` row is the one that used to be missing on the E3 side: the tool
// could not import the shared resolver across the layer boundary and asked two
// narrower questions instead, so a drop-in whose file resolved under neither
// tier root was hidden here and accepted there
// (`docs/audit/2026-08-07-adr-053-spec1-track-b.md` P2-2). The whole table is
// walked by `test_e3_promotes_exactly_the_origins_the_frontend_offers` in
// `tests/ai/test_mcp_tools_library.py`.
//
// Everything above the transport is shared by all three frontend entry points:
// they differ only in how they build the `PromotableItem` they pass in
// (`promotable.ts`), and the prompts are injected so the collision and cascade
// decisions are one dialog rather than three.
//
// Injected `io` and `prompts` also make the whole flow testable without a DOM:
// FR-017 (copy not move), FR-018 (never a silent overwrite) and FR-021 – FR-024
// are properties of this function, not of any component.

import type { TypeSummary, UserLibraryTarget } from "../../types/api";

import { resolveCascade, type CascadePlan, type TypeDependency } from "./cascade";
import { isPromotableOrigin, type PromotableItem, type PromotionSourceRef } from "./promotable";

/** The bytes a promotion copies, and the filename it suggests for them. */
export interface PromotionSource {
  filename: string;
  content: string;
}

/** One completed write into the user library. */
export interface PromotedFile {
  kind: "block" | "type";
  label: string;
  filename: string;
  /** Absolute path of the new file in the library. */
  path: string;
  /** True when an existing library file was replaced after an explicit opt-in. */
  overwritten: boolean;
}

/** Everything the action needs from the outside world. */
export interface PromotionIo {
  /** Read the file a `PromotableItem` points at. Never moves or deletes it. */
  readSource: (ref: PromotionSourceRef) => Promise<PromotionSource>;
  /** Read one project-level type's source, for the cascade walk. */
  readTypeSource: (type: TypeSummary) => Promise<string>;
  /** The registered type catalogue, carrying the FR-003 resolved origins. */
  typeCatalogue: () => Promise<readonly TypeSummary[]>;
  /**
   * `PUT /api/user-library/file`. MUST reject an existing destination unless
   * `overwrite` is set — the 409 is what drives the FR-018 prompt, and a
   * caller that defaulted it to `true` would be the silent overwrite the spec
   * forbids.
   */
  write: (
    target: UserLibraryTarget,
    filename: string,
    content: string,
    options: { overwrite: boolean },
  ) => Promise<{ path: string; kind: "created" | "modified" }>;
  /** True when an error from `write` is the FR-008 collision. */
  isCollision: (error: unknown) => boolean;
}

/** What the user is being asked to confirm (FR-023). */
export interface PromotionPlan {
  item: PromotableItem;
  filename: string;
  cascade: CascadePlan;
}

export type PromotionAnswer =
  | { action: "cancel" }
  /**
   * FR-023: a single confirmed action. `includeDependencies: false` is the
   * decline branch — the item is still promoted, and the caller is warned it
   * will fail to load in other projects.
   */
  | { action: "promote"; includeDependencies: boolean };

/** The FR-018 prompt's question. */
export interface CollisionRequest {
  target: UserLibraryTarget;
  filename: string;
  label: string;
  /** Server-supplied detail naming the file, so the prompt is not a guess. */
  detail: string;
}

export type CollisionAnswer =
  | { action: "cancel" }
  | { action: "overwrite" }
  | { action: "rename"; filename: string };

export interface PromotionPrompts {
  confirm: (plan: PromotionPlan) => Promise<PromotionAnswer>;
  resolveCollision: (request: CollisionRequest) => Promise<CollisionAnswer>;
}

export interface PromotionOutcome {
  /**
   * `partial` is a cancel that could not undo itself.
   *
   * Dependencies are written before the item (see `promoteToUserLibrary`), so
   * a user who cancels the collision prompt for the *item* does so after
   * cascade files have already been added to — or overwritten in — My Library.
   * Reporting that is the only honest option available: there is no delete
   * endpoint for the user library, and even with one a dependency write that
   * took the "Overwrite" branch destroyed the previous file, so a rollback
   * could not restore what it replaced. Returning `cancelled` instead left
   * `runPromotion` silent, which is the one outcome FR-020's teaching intent
   * rules out — the UI would say nothing while the library had changed.
   */
  status: "promoted" | "partial" | "cancelled" | "failed";
  item: PromotableItem;
  /** The item's own write, absent when it did not happen. */
  promoted: PromotedFile | null;
  /** Project-level types promoted alongside it (FR-023). */
  promotedDependencies: PromotedFile[];
  /** Project-level types the user declined (FR-023). */
  declinedDependencies: string[];
  /** Second-level project types, reported and never promoted (FR-024). */
  secondLevel: Array<{ name: string; via: string }>;
  /** Sentences the UI shows verbatim: cascade declines, FR-024 residue, errors. */
  warnings: string[];
  error?: string;
}

/** `normalize` / `normalize.py` → `normalize.py`. */
export function toLibraryFilename(name: string): string {
  const trimmed = name.trim();
  return /\.py$/i.test(trimmed) ? trimmed : `${trimmed}.py`;
}

function emptyOutcome(item: PromotableItem, status: PromotionOutcome["status"]): PromotionOutcome {
  return {
    status,
    item,
    promoted: null,
    promotedDependencies: [],
    declinedDependencies: [],
    secondLevel: [],
    warnings: [],
  };
}

/**
 * Write one file, resolving a collision with the user rather than around them.
 *
 * The loop is the whole of FR-018: `overwrite` starts `false`, a 409 is turned
 * into a question, and a rename re-enters with `overwrite` back at `false` so
 * the second name is checked as strictly as the first. Nothing in this
 * function can reach `overwrite: true` without the user having said so.
 */
async function writeWithCollisionPrompt(
  io: PromotionIo,
  prompts: PromotionPrompts,
  target: UserLibraryTarget,
  label: string,
  kind: "block" | "type",
  initialFilename: string,
  content: string,
): Promise<PromotedFile | null> {
  let filename = initialFilename;
  let overwrite = false;
  for (;;) {
    try {
      const result = await io.write(target, filename, content, { overwrite });
      return {
        kind,
        label,
        filename,
        path: result.path,
        overwritten: result.kind === "modified",
      };
    } catch (error) {
      if (!io.isCollision(error)) {
        throw error;
      }
      const detail = error instanceof Error ? error.message : String(error);
      const answer = await prompts.resolveCollision({ target, filename, label, detail });
      if (answer.action === "cancel") {
        return null;
      }
      if (answer.action === "overwrite") {
        overwrite = true;
        continue;
      }
      filename = toLibraryFilename(answer.filename);
      overwrite = false;
    }
  }
}

/**
 * The outcome of a cancel, which depends on what the cascade already wrote.
 *
 * Nothing written yet is a plain `cancelled` — the user's own decision, needing
 * no confirmation. Anything written is a `partial`, carrying the sentence that
 * names the files that stayed behind; see {@link PromotionOutcome.status} for
 * why they stay rather than being rolled back.
 */
function cancelledOutcome(
  item: PromotableItem,
  promotedDependencies: PromotedFile[],
): PromotionOutcome {
  if (promotedDependencies.length === 0) {
    return emptyOutcome(item, "cancelled");
  }
  const one = promotedDependencies.length === 1;
  const names = promotedDependencies.map((entry) => entry.label).join(", ");
  return {
    ...emptyOutcome(item, "partial"),
    promotedDependencies,
    warnings: [
      `"${item.label}" was not promoted, but the data ${one ? "type" : "types"} it depends on ` +
        `(${names}) had already been copied into My Library and ${one ? "is" : "are"} still ` +
        `there. Delete ${one ? "it" : "them"} from My Library if you did not mean to keep ` +
        `${one ? "it" : "them"}.`,
    ],
  };
}

/** FR-023's decline warning, and FR-024's report, as user-facing sentences. */
function cascadeWarnings(
  item: PromotableItem,
  declined: TypeDependency[],
  cascade: CascadePlan,
): string[] {
  const warnings: string[] = [];
  if (declined.length > 0) {
    const names = declined.map((entry) => entry.type.name).join(", ");
    warnings.push(
      `"${item.label}" imports project-level data ${declined.length === 1 ? "type" : "types"} ` +
        `${names}, which were not promoted. It will fail to load in other projects until ` +
        `${declined.length === 1 ? "it is" : "they are"} promoted too.`,
    );
  }
  for (const entry of cascade.secondLevel) {
    warnings.push(
      `"${entry.type.name}" is imported by "${entry.via.name}" and is still project-local. ` +
        `Cascade promotion is one level deep, so it was not copied — promote it separately.`,
    );
  }
  for (const type of cascade.unreadable) {
    warnings.push(
      `Could not read "${type.name}" to check what it imports, so any types it depends on ` +
        `are unknown.`,
    );
  }
  return warnings;
}

/**
 * Promote one item into the user-wide library.
 *
 * Order is load-bearing: dependencies are written before the item, so a failure
 * or a cancelled collision prompt part-way through leaves the library without
 * the item rather than with an item whose types are missing. The originating
 * project is never written to at any point (FR-017).
 *
 * The same ordering is why a cancel is not always a no-op. Stopping after the
 * cascade has written leaves those files in place, and the outcome says so
 * (`partial`) rather than reporting a cancellation the library does not
 * reflect — see {@link PromotionOutcome.status}.
 */
export async function promoteToUserLibrary(
  item: PromotableItem,
  deps: { io: PromotionIo; prompts: PromotionPrompts },
): Promise<PromotionOutcome> {
  const { io, prompts } = deps;
  if (!isPromotableOrigin(item.origin)) {
    // Defence in depth for FR-019. Every entry point hides the action for a
    // non-project origin; this makes a programmatic caller behave the same way
    // rather than copying a built-in block's file onto itself.
    return {
      ...emptyOutcome(item, "failed"),
      error: `"${item.label}" is not a project-level item, so it is already in a library.`,
    };
  }

  let source: PromotionSource;
  let catalogue: readonly TypeSummary[];
  try {
    source = await io.readSource(item.source);
    catalogue = await io.typeCatalogue();
  } catch (error) {
    return {
      ...emptyOutcome(item, "failed"),
      error: error instanceof Error ? error.message : String(error),
    };
  }

  // FR-021/FR-022: only a block can drag types along. A type's own cascade
  // would be a second level of the same walk, which FR-024 puts out of scope.
  const cascade: CascadePlan =
    item.kind === "block"
      ? await resolveCascade(source.content, catalogue, io.readTypeSource)
      : { dependencies: [], secondLevel: [], unreadable: [] };

  const filename = toLibraryFilename(source.filename);
  const answer = await prompts.confirm({ item, filename, cascade });
  if (answer.action === "cancel") {
    return emptyOutcome(item, "cancelled");
  }

  const included = answer.includeDependencies ? cascade.dependencies : [];
  const declined = answer.includeDependencies ? [] : cascade.dependencies;
  const promotedDependencies: PromotedFile[] = [];

  try {
    for (const dependency of included) {
      const nested = await io.readSource({
        from: "projectFile",
        path: `types/${(dependency.type.file_path ?? "").split(/[\\/]/).pop() ?? ""}`,
      });
      const written = await writeWithCollisionPrompt(
        io,
        prompts,
        "types",
        dependency.type.name,
        "type",
        toLibraryFilename(nested.filename),
        nested.content,
      );
      if (!written) {
        return cancelledOutcome(item, promotedDependencies);
      }
      promotedDependencies.push(written);
    }

    const promoted = await writeWithCollisionPrompt(
      io,
      prompts,
      item.target,
      item.label,
      item.kind,
      filename,
      source.content,
    );
    if (!promoted) {
      return cancelledOutcome(item, promotedDependencies);
    }

    return {
      status: "promoted",
      item,
      promoted,
      promotedDependencies,
      declinedDependencies: declined.map((entry) => entry.type.name),
      secondLevel: cascade.secondLevel.map((entry) => ({
        name: entry.type.name,
        via: entry.via.name,
      })),
      warnings: cascadeWarnings(item, declined, cascade),
    };
  } catch (error) {
    return {
      ...emptyOutcome(item, "failed"),
      promotedDependencies,
      error: error instanceof Error ? error.message : String(error),
    };
  }
}
