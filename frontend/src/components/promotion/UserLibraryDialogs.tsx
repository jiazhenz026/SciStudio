// The one mounted host for every user-library question and confirmation.
//
// Spec: docs/specs/adr-053-personal-tool-library.md §6 FR-018 (overwrite /
// save-as-new-name), FR-020 (inline confirmation), §6.1 FR-023 (cascade
// offered as a single confirmed action; declining warns), FR-024 (second-level
// dependencies reported), §8 FR-029 (destination choice).
//
// Mounted once, from `AppDialogs`, and driven entirely by `dialogChannel`. No
// entry point renders a dialog of its own, which is what makes the collision
// prompt the palette shows and the collision prompt the canvas shows the same
// prompt rather than two that drifted apart.

import { useEffect, useState } from "react";

import type { CascadePlan } from "./cascade";
import {
  dismissPromotionResult,
  useDialogChannel,
  type DestinationRequest,
  type FileDestination,
} from "./dialogChannel";
import type {
  CollisionAnswer,
  CollisionRequest,
  PromotionAnswer,
  PromotionOutcome,
  PromotionPlan,
} from "./promoteToUserLibrary";

const OVERLAY =
  "fixed inset-0 z-50 flex items-center justify-center bg-stone-950/55 p-4 backdrop-blur-sm";
const CARD =
  "w-full max-w-md rounded-[1.5rem] border border-stone-200 bg-stone-50 p-6 shadow-panel";
const PRIMARY =
  "rounded-full bg-ink px-5 py-2 text-sm font-medium text-stone-50 transition hover:bg-pine";
const SECONDARY = "rounded-full border border-stone-300 px-4 py-2 text-sm";

/** FR-024 — the residue of the one-level limit, stated rather than dropped. */
function SecondLevelNotice({ cascade }: { cascade: CascadePlan }) {
  if (cascade.secondLevel.length === 0 && cascade.unreadable.length === 0) return null;
  return (
    <div
      className="mt-3 rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs leading-snug text-amber-900"
      data-testid="promotion-second-level"
    >
      <p className="font-medium">Not included — cascade is one level deep.</p>
      <ul className="mt-1 list-disc pl-4">
        {cascade.secondLevel.map((entry) => (
          <li key={`${entry.via.name}-${entry.type.name}`}>
            <span className="font-mono">{entry.type.name}</span>, imported by{" "}
            <span className="font-mono">{entry.via.name}</span>
          </li>
        ))}
        {cascade.unreadable.map((type) => (
          <li key={`unreadable-${type.name}`}>
            <span className="font-mono">{type.name}</span> could not be read, so what it imports is
            unknown
          </li>
        ))}
      </ul>
    </div>
  );
}

/** FR-023 — the item and its project-level types, as one confirmed action. */
function ConfirmDialog({
  plan,
  onAnswer,
}: {
  plan: PromotionPlan;
  onAnswer: (answer: PromotionAnswer) => void;
}) {
  const [includeDependencies, setIncludeDependencies] = useState(true);
  const dependencies = plan.cascade.dependencies;
  const noun = plan.item.kind === "block" ? "block" : "data type";

  return (
    <div className={OVERLAY}>
      <div aria-modal="true" className={CARD} data-testid="promotion-confirm-dialog" role="dialog">
        <h2 className="font-display text-2xl text-ink">Move to My Library</h2>
        {/* FR-017 — the sentence has to say the file leaves the project,
            because it does. It also has to say the block keeps working here,
            because it does: the library is on every project's scan path
            (FR-060), so this moves where the file lives, not what resolves. */}
        <p className="mt-3 text-sm leading-snug text-stone-700">
          Move the {noun} <span className="font-medium text-ink">{plan.item.label}</span> into your
          personal library as <span className="font-mono text-xs">{plan.filename}</span>. Its file
          leaves this project, and every project can use it from now on — including this one.
        </p>

        {dependencies.length > 0 ? (
          <label
            className="mt-4 flex items-start gap-2 rounded-xl border border-stone-200 bg-white p-3 text-sm"
            data-testid="promotion-cascade-toggle"
          >
            <input
              checked={includeDependencies}
              className="mt-0.5"
              onChange={(event) => setIncludeDependencies(event.currentTarget.checked)}
              type="checkbox"
            />
            <span>
              <span className="font-medium text-ink">
                Also save the {dependencies.length} project data{" "}
                {dependencies.length === 1 ? "type" : "types"} it uses
              </span>
              <ul className="mt-1 list-disc pl-4 text-xs text-stone-600">
                {dependencies.map((entry) => (
                  <li data-testid="promotion-cascade-dependency" key={entry.type.name}>
                    <span className="font-mono">{entry.type.name}</span>
                  </li>
                ))}
              </ul>
              {!includeDependencies ? (
                <span
                  className="mt-2 block text-xs text-red-600"
                  data-testid="promotion-cascade-decline-warning"
                >
                  Without them this {noun} will fail to load in other projects.
                </span>
              ) : null}
            </span>
          </label>
        ) : null}

        <SecondLevelNotice cascade={plan.cascade} />

        <div className="mt-6 flex justify-end gap-3">
          <button
            className={SECONDARY}
            data-testid="promotion-confirm-cancel"
            onClick={() => onAnswer({ action: "cancel" })}
            type="button"
          >
            Cancel
          </button>
          <button
            className={PRIMARY}
            data-testid="promotion-confirm-submit"
            onClick={() => onAnswer({ action: "promote", includeDependencies })}
            type="button"
          >
            Move to My Library
          </button>
        </div>
      </div>
    </div>
  );
}

/**
 * FR-018 — overwrite or save under a new name, both explicit.
 *
 * The dialog only ever opens because the server answered 409, so the file it
 * names is a file that is really there; and neither button is the default, so
 * no keyboard reflex can overwrite something silently.
 */
function CollisionDialog({
  request,
  onAnswer,
}: {
  request: CollisionRequest;
  onAnswer: (answer: CollisionAnswer) => void;
}) {
  const [renaming, setRenaming] = useState(false);
  const [name, setName] = useState(request.filename.replace(/\.py$/i, ""));
  const trimmed = name.trim();
  const valid = /^[A-Za-z_][A-Za-z0-9_]*$/.test(trimmed);

  return (
    <div className={OVERLAY}>
      <div
        aria-modal="true"
        className={CARD}
        data-testid="promotion-collision-dialog"
        role="dialog"
      >
        <h2 className="font-display text-2xl text-ink">That name is taken</h2>
        <p className="mt-3 text-sm leading-snug text-stone-700">{request.detail}</p>

        {renaming ? (
          <label className="mt-4 block text-sm font-medium text-stone-700">
            New filename (without .py)
            <input
              autoFocus
              className="mt-1 w-full rounded-xl border border-stone-300 bg-white px-3 py-2 text-sm outline-none focus:border-ink"
              data-testid="promotion-collision-rename-input"
              onChange={(event) => setName(event.currentTarget.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && valid) {
                  event.preventDefault();
                  onAnswer({ action: "rename", filename: `${trimmed}.py` });
                }
              }}
              value={name}
            />
            {!valid ? (
              <span className="mt-1 block text-xs text-red-600">
                Use a Python identifier (letters, digits, underscores).
              </span>
            ) : null}
          </label>
        ) : null}

        <div className="mt-6 flex flex-wrap justify-end gap-3">
          <button
            className={SECONDARY}
            data-testid="promotion-collision-cancel"
            onClick={() => onAnswer({ action: "cancel" })}
            type="button"
          >
            Cancel
          </button>
          {renaming ? (
            <button
              className={PRIMARY}
              data-testid="promotion-collision-rename-submit"
              disabled={!valid}
              onClick={() => onAnswer({ action: "rename", filename: `${trimmed}.py` })}
              type="button"
            >
              Save as this name
            </button>
          ) : (
            <>
              <button
                className={SECONDARY}
                data-testid="promotion-collision-overwrite"
                onClick={() => onAnswer({ action: "overwrite" })}
                type="button"
              >
                Overwrite
              </button>
              <button
                className={PRIMARY}
                data-testid="promotion-collision-rename"
                onClick={() => setRenaming(true)}
                type="button"
              >
                Save as new name
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

/**
 * FR-029 (E4) — where the new file goes.
 *
 * Spec §8: "the cheapest possible moment to teach that the library exists,
 * because the user is already deciding where their work lives". Both options
 * name their real directory, so the choice teaches the layout rather than
 * asking the user to trust two labels.
 */
function DestinationDialog({
  request,
  onAnswer,
}: {
  request: DestinationRequest;
  onAnswer: (answer: FileDestination | null) => void;
}) {
  const option =
    "w-full rounded-xl border border-stone-300 bg-white p-3 text-left text-sm transition hover:border-ink";
  return (
    <div className={OVERLAY}>
      <div aria-modal="true" className={CARD} data-testid="file-destination-dialog" role="dialog">
        <h2 className="font-display text-2xl text-ink">{request.title}</h2>
        <p className="mt-2 text-sm text-stone-600">Where should this {request.noun} live?</p>

        <div className="mt-4 space-y-2">
          <button
            className={option}
            data-testid="file-destination-library"
            onClick={() => onAnswer("library")}
            type="button"
          >
            <span className="block font-medium text-ink">My Library</span>
            <span className="block text-xs text-stone-500">
              <span className="font-mono">{request.libraryDirectory}</span> — available in every
              project.
            </span>
          </button>
          <button
            className={option}
            data-testid="file-destination-project"
            onClick={() => onAnswer("project")}
            type="button"
          >
            <span className="block font-medium text-ink">This project</span>
            <span className="block text-xs text-stone-500">
              <span className="font-mono">{request.projectDirectory}</span> in {request.projectName}{" "}
              — stays with this project.
            </span>
          </button>
        </div>

        <div className="mt-6 flex justify-end">
          <button
            className={SECONDARY}
            data-testid="file-destination-cancel"
            onClick={() => onAnswer(null)}
            type="button"
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}

/** How long a clean success stays up before it gets out of the way. */
const CLEAN_NOTICE_MS = 6000;

/**
 * The notice's heading per outcome.
 *
 * `partial` gets its own wording because it is the case where saying "Saved"
 * would be as misleading as the silence it replaces: the item the user asked
 * for is *not* there, only the dependencies the cascade had already written.
 * `cancelled` never reaches the notice (`runPromotion` shows nothing for it)
 * and is listed so the record stays exhaustive over the status union.
 */
const NOTICE_HEADING: Record<PromotionOutcome["status"], string> = {
  promoted: "Moved to My Library",
  partial: "Partly moved to My Library",
  cancelled: "Moved to My Library",
  failed: "Could not move to My Library",
};

/**
 * FR-020's inline confirmation.
 *
 * Deliberately **not** modal: FR-020 asks for a confirmation *and* a reveal,
 * and a modal would cover the palette section the reveal just brought on
 * screen. A result carrying warnings (a declined cascade, or FR-024 residue)
 * never auto-dismisses — those are the sentences the user has to act on.
 */
function ResultNotice({
  outcome,
  onDismiss,
}: {
  outcome: PromotionOutcome;
  onDismiss: () => void;
}) {
  const clean = outcome.status === "promoted" && outcome.warnings.length === 0;
  useEffect(() => {
    if (!clean) return undefined;
    const timer = window.setTimeout(onDismiss, CLEAN_NOTICE_MS);
    return () => window.clearTimeout(timer);
  }, [clean, onDismiss]);

  const failed = outcome.status === "failed";
  const promotedNames = [
    ...(outcome.promoted ? [outcome.promoted.label] : []),
    ...outcome.promotedDependencies.map((entry) => entry.label),
  ];

  return (
    <div
      className={`fixed bottom-4 right-4 z-50 w-80 rounded-2xl border p-4 shadow-panel ${
        failed ? "border-red-200 bg-red-50" : "border-stone-200 bg-white"
      }`}
      data-testid="promotion-result"
      role="status"
    >
      <p className="font-display text-sm font-semibold text-ink">
        {NOTICE_HEADING[outcome.status]}
      </p>
      {failed ? (
        <p className="mt-1 text-xs leading-snug text-red-700">{outcome.error}</p>
      ) : (
        <p className="mt-1 text-xs leading-snug text-stone-600">
          <span className="font-mono">{promotedNames.join(", ")}</span>{" "}
          {promotedNames.length === 1 ? "is" : "are"} now in{" "}
          <span className="font-medium text-ink">My Library</span> and available in every project.
        </p>
      )}
      {outcome.warnings.map((warning) => (
        <p
          className="mt-2 text-xs leading-snug text-amber-800"
          data-testid="promotion-result-warning"
          key={warning}
        >
          {warning}
        </p>
      ))}
      <div className="mt-3 flex justify-end">
        <button
          className="text-xs text-stone-500 underline"
          data-testid="promotion-result-dismiss"
          onClick={onDismiss}
          type="button"
        >
          Dismiss
        </button>
      </div>
    </div>
  );
}

/**
 * Mount once (from `AppDialogs`). Renders whichever user-library question is
 * pending and the last promotion's inline confirmation.
 */
export function UserLibraryDialogs() {
  const { pending, notice } = useDialogChannel();

  return (
    <>
      {pending?.kind === "confirm" ? (
        <ConfirmDialog key={pending.plan.filename} onAnswer={pending.resolve} plan={pending.plan} />
      ) : null}
      {pending?.kind === "collision" ? (
        <CollisionDialog
          key={pending.request.filename}
          onAnswer={pending.resolve}
          request={pending.request}
        />
      ) : null}
      {pending?.kind === "destination" ? (
        <DestinationDialog onAnswer={pending.resolve} request={pending.request} />
      ) : null}
      {notice ? <ResultNotice onDismiss={dismissPromotionResult} outcome={notice} /> : null}
    </>
  );
}
