/**
 * ADR-053 spec 2 (#2001) — the Bring In My Work framing dialog.
 *
 * Spec: `docs/specs/adr-053-work-import.md`, FR-003 – FR-021 and FR-037 – FR-044.
 *
 * A scientist who already has a working way of doing their analysis is the user
 * with the most to gain from SciStudio and the highest cost of entry. This
 * dialog is everything the product does before handing that user to an agent:
 * it collects where their work is, where the results should go, which agent
 * runs, how much that agent may do without asking, and four questions about
 * their own world. Then it says plainly that the result is not verified, and
 * starts an ordinary chat session (FR-025) with all of it already loaded.
 *
 * IT IS PAGED, AND THE REASON IS THE USER, NOT THE CODE. Owner directive,
 * 2026-08-07: a long questionnaire is unpleasant to look at and users will not
 * bother filling it in. So page one is the setup — where the work is, where the
 * results go, which agent, how much it may do — and each question then gets a
 * page of its own. This is also the shape #2001 described from the start:
 * "Dialog, page one" and "Dialog, the four questions" as separate groups.
 *
 * What paging does NOT change is the contract. The request body, its validation,
 * which answers are required, and the wording of every question are identical to
 * the single-page version. Only the arrangement moved. The four requirements
 * that paging could have quietly broken are handled in
 * `BringInMyWorkDialog.parts/pages.ts`, which is where the page rules live.
 *
 * Two constraints shape every question in here, and both are easy to erode:
 *
 *   FR-006 — no question may require SciStudio knowledge.
 *   FR-007 — no question may require software-development knowledge.
 *
 * The dialog asks only about the user's own world. The wording that makes that
 * true lives in `BringInMyWorkDialog.parts/copy.ts`, together with the note on
 * why questions 3 and 4 are also a discovery surface. Because only one page is
 * on screen at a time, the guard test for those two FRs walks EVERY page — a
 * test that rendered the dialog and searched it once would now be checking page
 * one and reporting on five.
 */
import { useCallback, useEffect, useState, type ReactNode } from "react";

import { api } from "../lib/api";
import {
  fromBackendPermissionMode,
  startWorkImportSession,
  validateWorkImportRequest,
  type WorkImportSessionRequest,
} from "../lib/api/workImport";
import { useAppStore } from "../store";

import { AgentSetup } from "./BringInMyWorkDialog.parts/AgentSetup";
import { AvailabilityGuidance } from "./BringInMyWorkDialog.parts/AvailabilityGuidance";
import { CorrectnessCaveat } from "./BringInMyWorkDialog.parts/CorrectnessCaveat";
import { DataKindsQuestion } from "./BringInMyWorkDialog.parts/DataKindsQuestion";
import { FreeTextQuestion } from "./BringInMyWorkDialog.parts/FreeTextQuestion";
import { PageNav, type PageNavAction } from "./BringInMyWorkDialog.parts/PageNav";
import { SourceAndDestination } from "./BringInMyWorkDialog.parts/SourceAndDestination";
import {
  hasUsableProvider,
  resolveSelectedProvider,
} from "./BringInMyWorkDialog.parts/availability";
import {
  AVAILABILITY_PROBING,
  BLOCKED_LEAD,
  CANCEL_LABEL,
  DIALOG_EYEBROW,
  DIALOG_LEAD,
  DIALOG_TITLE,
  NEXT_LABEL,
  NO_AGENT_BLOCKS_PAGING,
  Q2_HELP_NO_CODEBASE,
  Q2_HELP_WITH_SOURCE,
  Q2_LABEL,
  Q2_PLACEHOLDER_NO_CODEBASE,
  Q2_PLACEHOLDER_WITH_SOURCE,
  Q3_HELP,
  Q3_LABEL,
  Q3_PLACEHOLDER,
  Q4_HELP,
  Q4_LABEL,
  Q4_PLACEHOLDER,
  START_HELP,
  START_LABEL,
  STARTING_LABEL,
} from "./BringInMyWorkDialog.parts/copy";
import {
  blockingReasons,
  buildRequest,
  canStart,
  INITIAL_FORM_STATE,
  markSkipped,
  workflowDescriptionRequired,
  type WorkImportFormState,
} from "./BringInMyWorkDialog.parts/formState";
import {
  furthestReachablePage,
  LAST_PAGE_INDEX,
  pageGate,
  WORK_IMPORT_PAGES,
} from "./BringInMyWorkDialog.parts/pages";
import {
  useAgentAvailability,
  type AvailabilityFetcher,
} from "./BringInMyWorkDialog.parts/useAgentAvailability";

export interface BringInMyWorkDialogProps {
  onClose: () => void;
  /**
   * Test seam for contract C1. Production passes nothing and the hook uses
   * `fetchAgentAvailability` from the availability track's client module.
   */
  fetchAvailability?: AvailabilityFetcher;
  /** Test seam for the request itself; production posts to `POST /api/work-import/sessions`. */
  startSession?: (request: WorkImportSessionRequest) => Promise<{
    tab_id: string;
    title: string;
    brief_path: string;
    provider: string;
    permission_mode: "safe" | "bypass";
  }>;
}

function parentDirectory(path: string): string | undefined {
  const trimmed = path.trim();
  if (!trimmed) return undefined;
  const normalized = trimmed.replace(/\\/g, "/");
  const index = normalized.lastIndexOf("/");
  return index > 0 ? trimmed.slice(0, index) : undefined;
}

const PAGE_TITLES = WORK_IMPORT_PAGES.map((page) => page.title);

export function BringInMyWorkDialog({
  onClose,
  fetchAvailability,
  startSession = startWorkImportSession,
}: BringInMyWorkDialogProps) {
  const projectDir = useAppStore((s) => s.currentProject?.path ?? null);
  const addWorkImportTerminalTab = useAppStore((s) => s.addWorkImportTerminalTab);
  const openBottomTab = useAppStore((s) => s.openBottomTab);

  const [state, setState] = useState<WorkImportFormState>(INITIAL_FORM_STATE);
  const [pageIndex, setPageIndex] = useState(0);
  /**
   * The page rules are enforced on every attempt to leave a page, but their
   * reasons are only SHOWN once the user has tried. Announcing what is missing
   * before they have touched the page reads as an error they have already made.
   */
  const [reasonsVisible, setReasonsVisible] = useState(false);
  const [browsing, setBrowsing] = useState(false);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // FR-035 — renders immediately; a hanging probe degrades to a reported state.
  const {
    loading: probing,
    availability,
    probeError,
    retry,
    retrying,
  } = useAgentAvailability(fetchAvailability);
  const agentUsable = hasUsableProvider(availability);

  // FR-043 — one usable provider is selected rather than offered as a choice.
  useEffect(() => {
    setState((prev) => {
      const next = resolveSelectedProvider(availability, prev.provider);
      return next === prev.provider ? prev : { ...prev, provider: next };
    });
  }, [availability]);

  const page = WORK_IMPORT_PAGES[pageIndex];
  const isLastPage = pageIndex === LAST_PAGE_INDEX;
  const gate = pageGate(pageIndex, state, { projectDir, agentUsable, probing });

  const advance = useCallback(() => {
    setReasonsVisible(false);
    setPageIndex((current) => Math.min(current + 1, LAST_PAGE_INDEX));
  }, []);

  /**
   * FR-020 — a required answer blocks the page, with a reason the user can act
   * on. Next is deliberately NOT disabled: a dead button tells the user nothing,
   * and pressing it is how they ask what is wrong. So it always responds — by
   * moving on, or by saying what is missing and putting them in front of the
   * control that fixes it.
   */
  const goNext = useCallback(() => {
    if (gate.reasons.length > 0) {
      setReasonsVisible(true);
      if (gate.focusId) document.getElementById(gate.focusId)?.focus();
      return;
    }
    advance();
  }, [advance, gate.focusId, gate.reasons.length]);

  const goBack = useCallback(() => {
    setReasonsVisible(false);
    setPageIndex((current) => Math.max(current - 1, 0));
  }, []);

  /**
   * Jumping from the progress indicator. Clamped to the first page that is still
   * incomplete, so the indicator is a shortcut and never a way around FR-020 —
   * and when it clamps, the user lands on the page that stopped them with the
   * reason already showing rather than somewhere unexplained.
   */
  const goTo = useCallback(
    (target: number) => {
      const limit = furthestReachablePage(state, { projectDir, agentUsable, probing });
      const next = Math.max(0, Math.min(target, limit));
      setReasonsVisible(next < target);
      setPageIndex(next);
    },
    [agentUsable, probing, projectDir, state],
  );

  const patch = useCallback((next: Partial<WorkImportFormState>) => {
    setState((prev) => ({ ...prev, ...next }));
  }, []);

  const toggleDataKind = useCallback((option: string) => {
    setState((prev) => ({
      ...prev,
      dataKinds: prev.dataKinds.includes(option)
        ? prev.dataKinds.filter((value) => value !== option)
        : [...prev.dataKinds, option],
    }));
  }, []);

  const handleBrowse = useCallback(async () => {
    setBrowsing(true);
    setError(null);
    try {
      // FR-008 — a DIRECTORY picker. The user's work is a folder.
      const response = await api.openNativeDialog(
        "directory",
        parentDirectory(state.sourceLocation),
        true,
      );
      if (response.paths.length > 0) patch({ sourceLocation: response.paths[0] });
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBrowsing(false);
    }
  }, [patch, state.sourceLocation]);

  const handleStart = useCallback(async () => {
    if (!projectDir) return;
    setStarting(true);
    setError(null);
    const request = buildRequest(state, projectDir);
    /*
     * A2's `ImportSessionContext` rejects a body that breaks any of its rules,
     * and a 422 at this point is a dead end: the user has answered five pages
     * and gets an HTTP status back. The page rules and `blockingReasons` should
     * already have made every violation unreachable, so this is a backstop that
     * turns a regression in the form's own rules into a readable sentence
     * instead of a rejected request.
     */
    const problems = validateWorkImportRequest(request);
    if (problems.length > 0) {
      setError(problems.join(" "));
      setStarting(false);
      return;
    }
    try {
      const response = await startSession(request);
      // C3 — the backend has already written the brief and spawned the PTY, so
      // the tab goes straight to `running` and joins the existing session over
      // `WS /api/ai/pty/{tab_id}`. FR-025: from here it is an ordinary chat
      // session the user can talk to, redirect, and end like any other.
      addWorkImportTerminalTab({
        tabId: response.tab_id,
        title: response.title,
        provider: response.provider,
        permissionMode: fromBackendPermissionMode(response.permission_mode),
      });
      openBottomTab("ai");
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setStarting(false);
    }
  }, [addWorkImportTerminalTab, onClose, openBottomTab, projectDir, startSession, state]);

  const q2Required = workflowDescriptionRequired(state);
  /**
   * FR-016 / FR-017 — question 2's skip depends on a choice made two pages
   * earlier. The state is held here rather than by the page, so the page that
   * asks and the page that decides cannot disagree.
   */
  const skipKey = page.skips !== null && !(page.id === "q2" && q2Required) ? page.skips : null;

  const handleSkip = useCallback(() => {
    if (!skipKey) return;
    setState((prev) => markSkipped(prev, skipKey));
    advance();
  }, [advance, skipKey]);

  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
        return;
      }
      if (event.key !== "Enter" || event.shiftKey || event.ctrlKey || event.metaKey || event.altKey)
        return;
      const tag = (event.target as HTMLElement | null)?.tagName?.toLowerCase();
      // Enter belongs to a textarea — the answers are prose and may have
      // paragraphs — and to a button, which already has its own activation.
      if (tag === "textarea" || tag === "button" || tag === "a") return;
      // Enter ADVANCES and only advances. It never starts the session: a stray
      // keypress on the last page must not spawn an agent in the user's project.
      if (isLastPage || starting) return;
      event.preventDefault();
      goNext();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [goNext, isLastPage, onClose, starting]);

  const startShown = isLastPage && !probing && agentUsable;
  const startable = canStart(state, { projectDir, agentUsable }) && !starting;
  const reasons = isLastPage
    ? startShown
      ? blockingReasons(state, { projectDir, agentUsable })
      : []
    : reasonsVisible
      ? gate.reasons
      : [];

  const action: PageNavAction | null = isLastPage
    ? startShown
      ? {
          label: starting ? STARTING_LABEL : START_LABEL,
          testId: "work-import-start",
          disabled: !startable,
          onClick: () => void handleStart(),
        }
      : null
    : { label: NEXT_LABEL, testId: "work-import-next", disabled: false, onClick: goNext };

  function pageBody(): ReactNode {
    switch (page.id) {
      case "setup":
        return (
          <div className="grid content-start gap-6">
            <SourceAndDestination
              state={state}
              onChange={patch}
              onBrowse={() => void handleBrowse()}
              browsing={browsing}
            />

            {/*
             * FR-005 — when NO agent is usable the guidance takes the picker's
             * place, and on a paged dialog it also stops the user going on: five
             * pages of answers that cannot be submitted is a worse dead end than
             * the one FR-005 already closes. The agent is chosen here, so this is
             * where that is found out. When some providers are usable the user
             * proceeds with one of those; the rest are reported inside
             * `AgentSetup` without blocking.
             */}
            {probing ? (
              <div className="grid gap-2">
                <p className="text-xs italic text-stone-500" data-testid="work-import-probing">
                  {AVAILABILITY_PROBING}
                </p>
                <AgentSetup
                  availability={availability}
                  probing
                  provider={state.provider}
                  permissionMode={state.permissionMode}
                  onProviderChange={(provider) => patch({ provider })}
                  onPermissionModeChange={(permissionMode) => patch({ permissionMode })}
                />
              </div>
            ) : agentUsable ? (
              <AgentSetup
                availability={availability}
                probing={false}
                provider={state.provider}
                permissionMode={state.permissionMode}
                onProviderChange={(provider) => patch({ provider })}
                onPermissionModeChange={(permissionMode) => patch({ permissionMode })}
              />
            ) : (
              <div className="grid gap-2">
                <AvailabilityGuidance
                  availability={availability}
                  probeError={probeError}
                  onRetry={retry}
                  retrying={retrying}
                />
                <p className="text-xs text-stone-500" data-testid="work-import-agent-blocks-paging">
                  {NO_AGENT_BLOCKS_PAGING}
                </p>
              </div>
            )}
          </div>
        );
      case "q1":
        return (
          <DataKindsQuestion
            selected={state.dataKinds}
            other={state.dataKindsOther}
            onToggle={toggleDataKind}
            onOtherChange={(dataKindsOther) => patch({ dataKindsOther })}
          />
        );
      case "q2":
        return (
          <FreeTextQuestion
            id="q2"
            label={Q2_LABEL}
            help={q2Required ? Q2_HELP_NO_CODEBASE : Q2_HELP_WITH_SOURCE}
            placeholder={q2Required ? Q2_PLACEHOLDER_NO_CODEBASE : Q2_PLACEHOLDER_WITH_SOURCE}
            value={state.workflowDescription}
            required={q2Required}
            onChange={(workflowDescription) => patch({ workflowDescription })}
          />
        );
      case "q3":
        return (
          <FreeTextQuestion
            id="q3"
            label={Q3_LABEL}
            help={Q3_HELP}
            placeholder={Q3_PLACEHOLDER}
            value={state.interactionWishes}
            onChange={(interactionWishes) => patch({ interactionWishes })}
          />
        );
      case "q4":
        return (
          <FreeTextQuestion
            id="q4"
            label={Q4_LABEL}
            help={Q4_HELP}
            placeholder={Q4_PLACEHOLDER}
            value={state.otherSoftware}
            onChange={(otherSoftware) => patch({ otherSoftware })}
          />
        );
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink/30 p-4">
      <div
        aria-modal="true"
        role="dialog"
        aria-labelledby="work-import-title"
        data-testid="work-import-dialog"
        className="flex max-h-[88vh] w-full max-w-2xl flex-col rounded-xl border border-stone-200 bg-stone-50 p-6 shadow-panel"
      >
        <div className="mb-3 flex items-start justify-between gap-4">
          <div>
            <p className="text-xs uppercase tracking-[0.28em] text-stone-500">{DIALOG_EYEBROW}</p>
            <h2 className="mt-2 font-display text-2xl text-ink" id="work-import-title">
              {DIALOG_TITLE}
            </h2>
          </div>
          <button
            className="rounded-full border border-stone-300 px-3 py-1 text-sm"
            onClick={onClose}
            type="button"
            data-testid="work-import-close"
          >
            {CANCEL_LABEL}
          </button>
        </div>
        {/*
         * What the whole thing is for, said once where it is read — on the way
         * in. Repeating it above every question would be the padding one
         * question per page exists to avoid.
         */}
        {pageIndex === 0 ? <p className="mb-4 text-sm text-stone-600">{DIALOG_LEAD}</p> : null}

        <div
          className="min-h-0 flex-1 overflow-y-auto pr-1 sm:min-h-[18rem]"
          data-testid="work-import-page"
          data-page={page.id}
        >
          {pageBody()}
        </div>

        <div className="mt-4 grid gap-3 border-t border-stone-200 pt-4">
          {error ? (
            <p className="text-sm text-red-600" data-testid="work-import-error">
              {error}
            </p>
          ) : null}

          {reasons.length > 0 ? (
            <div
              className="text-xs text-stone-500"
              data-testid="work-import-blocking-reasons"
              role="alert"
            >
              <p>{BLOCKED_LEAD}</p>
              <ul className="mt-1 list-disc pl-5">
                {reasons.map((reason) => (
                  <li key={reason}>{reason}</li>
                ))}
              </ul>
            </div>
          ) : null}

          {/*
           * FR-005, on the page that holds the start action. The user should
           * have met this on page one, where the agent is chosen — but a probe
           * that resolves late, or a retry that fails, can put them here with no
           * usable agent, and the requirement is that the guidance stands in for
           * the start action wherever that happens.
           */}
          {isLastPage && probing ? (
            <p className="text-xs italic text-stone-500" data-testid="work-import-probing">
              {AVAILABILITY_PROBING}
            </p>
          ) : null}
          {isLastPage && !probing && !agentUsable ? (
            <AvailabilityGuidance
              availability={availability}
              probeError={probeError}
              onRetry={retry}
              retrying={retrying}
            />
          ) : null}

          {startShown ? <p className="text-xs text-stone-500">{START_HELP}</p> : null}

          {/*
           * FR-004 / FR-038 — the caveat is on the page that carries the start
           * action, immediately above it, always expanded and never dismissible.
           * Paged, that is a stronger position than it was: on the scrolling
           * page the caveat and the button merely shared a footer, and here
           * there is no page containing a start action that does not also
           * contain this. A user cannot reach Start without it on screen.
           */}
          {isLastPage ? <CorrectnessCaveat /> : null}

          <PageNav
            stepIndex={pageIndex}
            titles={PAGE_TITLES}
            onGoTo={goTo}
            onBack={pageIndex === 0 ? null : goBack}
            skip={skipKey ? { testId: `work-import-${page.id}-skip`, onSkip: handleSkip } : null}
            action={action}
          />
        </div>
      </div>
    </div>
  );
}
