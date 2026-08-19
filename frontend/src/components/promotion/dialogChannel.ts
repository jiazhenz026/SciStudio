// The promise-based dialog channel behind promotion and the new-file flows.
//
// Spec: docs/specs/adr-053-personal-tool-library.md §6 FR-018 (collision
// prompt), FR-020 (inline confirmation), §6.1 FR-023 (cascade offer),
// §8 FR-029 (the new-file destination choice, entry point E4).
//
// Why a module-level channel rather than props: promotion is reachable from
// the editor toolbar, a canvas node, and two palette popovers, and the
// new-file flow is reachable from a hook with no render tree of its own
// (`useProjectActions`). Threading dialog state through four component trees
// would put a copy of the prompt at every entry point, which is precisely the
// duplication FR-025 forbids. Instead every caller `await`s a request here,
// one mounted `UserLibraryDialogs` renders whatever is pending, and the
// prompts are therefore identical by construction.
//
// This is the same promise-based-modal shape `PromptDialog` already uses for
// `window.prompt` (unsupported in Electron); only the transport differs,
// because `usePromptInput` is React state owned by `App` and unreachable from
// a canvas node.

import { useSyncExternalStore } from "react";

import type {
  CollisionAnswer,
  CollisionRequest,
  PromotionAnswer,
  PromotionOutcome,
  PromotionPlan,
} from "./promoteToUserLibrary";

/** FR-029 — where a newly created file goes. */
export type FileDestination = "library" | "project";

export interface DestinationRequest {
  /** Dialog heading, e.g. "New custom block". */
  title: string;
  /** What is being created, e.g. "block" — used in the option copy. */
  noun: string;
  /** Project the "this project" option would write into. */
  projectName: string;
  /** Project-relative directory the project option writes to, e.g. `blocks/`. */
  projectDirectory: string;
  /** User library directory the library option writes to, e.g. `~/.scistudio/blocks/`. */
  libraryDirectory: string;
}

/** A modal question waiting for an answer. Exactly one is pending at a time. */
export type PendingRequest =
  | { kind: "confirm"; plan: PromotionPlan; resolve: (answer: PromotionAnswer) => void }
  | {
      kind: "collision";
      request: CollisionRequest;
      resolve: (answer: CollisionAnswer) => void;
    }
  | {
      kind: "destination";
      request: DestinationRequest;
      resolve: (answer: FileDestination | null) => void;
    };

interface ChannelState {
  pending: PendingRequest | null;
  /** FR-020's inline confirmation. Non-modal, so it never hides the reveal. */
  notice: PromotionOutcome | null;
}

let state: ChannelState = { pending: null, notice: null };
const listeners = new Set<() => void>();
const queue: PendingRequest[] = [];

function emit(next: ChannelState): void {
  state = next;
  for (const listener of listeners) listener();
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

function enqueue(request: PendingRequest): void {
  if (state.pending) {
    queue.push(request);
    return;
  }
  emit({ ...state, pending: request });
}

/** Answer the pending request and open whatever queued behind it. */
function settle(): void {
  const next = queue.shift() ?? null;
  emit({ ...state, pending: next });
}

/** FR-023 — offer the item and its project-level type dependencies together. */
export function askPromotionConfirmation(plan: PromotionPlan): Promise<PromotionAnswer> {
  return new Promise((resolve) => {
    enqueue({
      kind: "confirm",
      plan,
      resolve: (answer) => {
        settle();
        resolve(answer);
      },
    });
  });
}

/** FR-018 — overwrite or save-as-new-name; never a silent overwrite. */
export function askCollisionResolution(request: CollisionRequest): Promise<CollisionAnswer> {
  return new Promise((resolve) => {
    enqueue({
      kind: "collision",
      request,
      resolve: (answer) => {
        settle();
        resolve(answer);
      },
    });
  });
}

/** FR-029 (E4) — the user library or the current project. */
export function askFileDestination(request: DestinationRequest): Promise<FileDestination | null> {
  return new Promise((resolve) => {
    enqueue({
      kind: "destination",
      request,
      resolve: (answer) => {
        settle();
        resolve(answer);
      },
    });
  });
}

/** FR-020 — the inline confirmation, shown beside the revealed palette. */
export function showPromotionResult(outcome: PromotionOutcome): void {
  emit({ ...state, notice: outcome });
}

export function dismissPromotionResult(): void {
  emit({ ...state, notice: null });
}

export function useDialogChannel(): ChannelState {
  return useSyncExternalStore(
    subscribe,
    () => state,
    () => ({ pending: null, notice: null }),
  );
}

/** Test seam — drop every pending question and notice. */
export function resetDialogChannel(): void {
  queue.length = 0;
  emit({ pending: null, notice: null });
}
