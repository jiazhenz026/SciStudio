/**
 * ADR-053 spec 2 (#2001) — the dialog's pages, and what each one requires.
 *
 * Owner directive, 2026-08-07: *"一个长问卷用户看着很难受，也懒得填。我建议弄成
 * 翻页的，一页一个问题，第一页是browse，选provider之类的，然后第二页开始问题"* —
 * a long questionnaire is unpleasant to look at and users will not bother
 * filling it in; page one is the browse and provider setup, and the questions
 * start on page two, one per page.
 *
 * The dialog's contract does not change with paging. The request body, its
 * validation, which answers are required, and the wording of every question are
 * all exactly what they were on the single scrolling page. What changes is that
 * only one of them is on screen at a time — and that single fact quietly puts
 * four requirements at risk, which is what this module exists to keep true.
 *
 * FR-020 — REQUIRED VS SKIPPABLE IS NOW A NAVIGATION RULE. On one page, a
 * missing required answer disabled the start action. On five pages, the start
 * action is not even rendered until page five, so a user could answer nothing
 * and page straight past it. `pageGate` is therefore what enforces FR-020: a
 * page whose answer is required cannot be left, and the reason is the same
 * sentence the whole-form check would have given.
 *
 * FR-016 / FR-017 — QUESTION 2'S REQUIREMENT IS DECIDED ON A DIFFERENT PAGE
 * FROM WHERE IT IS ENFORCED. "I don't have a codebase" is ticked on page one;
 * question 2 becomes required on page three. Both read the same
 * `workflowDescriptionRequired(state)` over the same form state, so the two
 * pages cannot disagree — the state is held by the dialog, not by the page.
 *
 * FR-005 — AVAILABILITY HAS TO SURFACE EARLY. On one page the guidance replaced
 * the start action and the user saw it immediately. Paged, that guidance would
 * sit on the last page, and a user with no usable agent would answer five pages
 * before finding out none of it can run. The provider is chosen on page one, so
 * page one is where "no agent can run this" blocks — the user meets it before
 * the questions rather than after them.
 *
 * FR-021 is the one requirement paging does NOT touch, and deliberately so:
 * `buildRequest` already resolves an unanswered optional question to the same
 * payload as an explicitly skipped one, so a page the user simply moved past is
 * a skip in the request without any paging-specific handling.
 */
import {
  Q1_STEP_TITLE,
  Q2_STEP_TITLE,
  Q3_STEP_TITLE,
  Q4_STEP_TITLE,
  SETUP_STEP_TITLE,
} from "./copy";
import {
  REASON_NO_AGENT,
  REASON_NO_DATA_KIND,
  REASON_NO_PROJECT,
  REASON_NO_PROVIDER,
  REASON_NO_SOURCE,
  REASON_NO_WORKFLOW_DESCRIPTION,
  workflowDescriptionRequired,
  type WorkImportFormState,
} from "./formState";

export type WorkImportPageId = "setup" | "q1" | "q2" | "q3" | "q4";

/** The form-state keys holding an answer a user may skip (FR-020). */
export type SkippableAnswerKey = "workflowDescription" | "interactionWishes" | "otherSoftware";

export interface WorkImportPage {
  id: WorkImportPageId;
  /** The step's name in the progress indicator. */
  title: string;
  /**
   * The answer this page's skip control skips, when it has one. `setup` and
   * `q1` have none: FR-020 makes the source-or-no-codebase choice, the
   * destination and question 1 required. Question 2 has one only in codebase
   * mode, which is why the page carries the key and the dialog decides whether
   * to offer it.
   */
  skips: SkippableAnswerKey | null;
}

/**
 * Page one is the setup the owner asked for — browse, the no-codebase option,
 * destination, provider, permission mode — and the four questions then get a
 * page each, in the order spec §4.6 reproduces them to the agent.
 */
export const WORK_IMPORT_PAGES: readonly WorkImportPage[] = [
  { id: "setup", title: SETUP_STEP_TITLE, skips: null },
  { id: "q1", title: Q1_STEP_TITLE, skips: null },
  { id: "q2", title: Q2_STEP_TITLE, skips: "workflowDescription" },
  { id: "q3", title: Q3_STEP_TITLE, skips: "interactionWishes" },
  { id: "q4", title: Q4_STEP_TITLE, skips: "otherSoftware" },
];

export const LAST_PAGE_INDEX = WORK_IMPORT_PAGES.length - 1;

export interface PageGateOptions {
  projectDir: string | null;
  agentUsable: boolean;
  /**
   * True while the availability probe is still in flight. FR-035 — a probe that
   * has not answered yet must never produce a stuck surface, so it does not
   * block the user leaving page one. What it cannot do is let them START: the
   * start action on the last page is gated on `agentUsable`, and the last page
   * shows the probe's own state when it has not resolved.
   */
  probing: boolean;
}

export interface PageGate {
  /** Empty when the page may be left. Otherwise, what to do about it. */
  reasons: string[];
  /**
   * The DOM id of the control to put the user in front of when they try to move
   * on. A reason with nowhere to act on it is only half an answer, and on a
   * paged form the offending control may not be the one they were last in.
   */
  focusId: string | null;
}

const NO_BLOCK: PageGate = { reasons: [], focusId: null };

/**
 * What stops the user leaving this page, and where to send them to fix it.
 *
 * Every sentence here is one of `formState`'s reason constants, so the page
 * rule and the whole-form backstop say the same thing about the same problem.
 */
export function pageGate(
  pageIndex: number,
  state: WorkImportFormState,
  opts: PageGateOptions,
): PageGate {
  const page = WORK_IMPORT_PAGES[pageIndex];
  if (!page) return NO_BLOCK;

  switch (page.id) {
    case "setup": {
      const reasons: string[] = [];
      let focusId: string | null = null;
      if (!opts.projectDir) reasons.push(REASON_NO_PROJECT);
      if (!state.hasNoCodebase && !state.sourceLocation.trim()) {
        reasons.push(REASON_NO_SOURCE);
        focusId = "work-import-source";
      }
      // FR-005 — the agent is chosen here, so this is where a user learns that
      // none can run the session, rather than five pages later.
      if (!opts.probing) {
        if (!opts.agentUsable) {
          reasons.push(REASON_NO_AGENT);
        } else if (!state.provider) {
          reasons.push(REASON_NO_PROVIDER);
          focusId = focusId ?? "setup-provider-select-work-import";
        }
      }
      return { reasons, focusId };
    }
    case "q1":
      if (state.dataKinds.length > 0 || state.dataKindsOther.trim()) return NO_BLOCK;
      // The section rather than a single checkbox: the requirement is satisfied
      // by any of the presets or by the free-text field, and landing on one of
      // them would read as "this is the answer we wanted".
      return { reasons: [REASON_NO_DATA_KIND], focusId: "work-import-q1" };
    case "q2":
      if (!workflowDescriptionRequired(state) || state.workflowDescription.text.trim()) {
        return NO_BLOCK;
      }
      return { reasons: [REASON_NO_WORKFLOW_DESCRIPTION], focusId: "work-import-q2-input" };
    default:
      // FR-018 / FR-019 — questions 3 and 4 are skippable, so paging past them
      // without answering is a legitimate choice and never blocked.
      return NO_BLOCK;
  }
}

/**
 * The furthest page the user may jump to right now.
 *
 * The progress indicator lets them click any step, which would otherwise be a
 * way around the page rules — click step 5 from step 1 and every requirement in
 * between is skipped. Jumps are clamped to the first page that is still
 * incomplete, so the indicator can be a shortcut backwards and to pages already
 * satisfied, and never a bypass.
 */
export function furthestReachablePage(state: WorkImportFormState, opts: PageGateOptions): number {
  for (let index = 0; index < LAST_PAGE_INDEX; index += 1) {
    if (pageGate(index, state, opts).reasons.length > 0) return index;
  }
  return LAST_PAGE_INDEX;
}
