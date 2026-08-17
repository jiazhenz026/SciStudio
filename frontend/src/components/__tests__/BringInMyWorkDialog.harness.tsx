/**
 * ADR-053 spec 2 (#2001) — shared fixtures and navigation for the Bring In My
 * Work dialog's tests.
 *
 * Not a test file (vitest only collects `*.test.*`), and deliberately shared:
 * the dialog is paged, so almost every assertion about it now needs the dialog
 * driven to a particular page first. Two files each carrying their own idea of
 * how to page forward would drift, and a drifted walker is the failure mode this
 * whole exercise is trying to avoid — a test that thinks it exercised every page
 * while exercising one.
 *
 * `walkTo` is therefore the only way these tests move between pages, and it
 * FAILS LOUDLY rather than silently staying put: if a page will not let it
 * through it raises with the route it took, so a test can never quietly assert
 * against the wrong page.
 */
/* eslint-disable react-refresh/only-export-components --
 * A `.tsx` file that exports helpers rather than components. It renders JSX, so
 * it has to be `.tsx`; it is test-only, so Fast Refresh never sees it and the
 * rule's warning is about a situation that cannot arise here.
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { expect, vi, type Mock } from "vitest";

import { BringInMyWorkDialog } from "../BringInMyWorkDialog";
import type {
  AgentAvailabilityResponse,
  ProviderAvailability,
} from "../../lib/api/agentAvailability";

/**
 * One provider row, with contract C1's optional fields defaulted to "nothing to
 * report". Written as a factory rather than as object literals so a field added
 * to C1 lands in one place — and so a test that cares about `next_step` or
 * `session_unsupported_reason` says so by naming it.
 */
export function provider(
  overrides: Partial<ProviderAvailability> & { key: string },
): ProviderAvailability {
  return {
    label: overrides.key,
    state: "ready",
    cause: null,
    next_step: null,
    session_unsupported_reason: null,
    ...overrides,
  };
}

export const CLAUDE = provider({ key: "claude-code", label: "Claude Code" });
export const CODEX = provider({ key: "codex", label: "Codex" });

export function ready(
  ...providers: AgentAvailabilityResponse["providers"]
): AgentAvailabilityResponse {
  return { state: "ready", providers };
}

export type StartSession = NonNullable<
  React.ComponentProps<typeof BringInMyWorkDialog>["startSession"]
>;
export type SessionResponse = Awaited<ReturnType<StartSession>>;

export function sessionResponse(overrides: Partial<SessionResponse> = {}): SessionResponse {
  return {
    tab_id: "a1b2c3d4e5f6",
    title: "Bring in my work",
    brief_path: ".scistudio/work-import/s1.md",
    provider: "claude-code",
    permission_mode: "safe",
    ...overrides,
  };
}

export interface Harness {
  startSession: Mock<StartSession>;
  onClose: Mock<() => void>;
}

export function renderDialog(
  availability: AgentAvailabilityResponse | Error = ready(CLAUDE),
  overrides: Partial<Harness> = {},
): Harness {
  const startSession: Mock<StartSession> =
    overrides.startSession ?? vi.fn<StartSession>(async () => sessionResponse());
  const onClose: Mock<() => void> = overrides.onClose ?? vi.fn<() => void>();
  render(
    <BringInMyWorkDialog
      onClose={onClose}
      fetchAvailability={() =>
        availability instanceof Error ? Promise.reject(availability) : Promise.resolve(availability)
      }
      startSession={startSession}
    />,
  );
  return { startSession, onClose };
}

/** Wait for the availability probe to settle so the start action is decided. */
export async function settled(): Promise<void> {
  await waitFor(() => expect(screen.queryByTestId("work-import-probing")).toBeNull());
}

// ---------------------------------------------------------------------------
// Paging.
// ---------------------------------------------------------------------------

/**
 * The pages, in order. Duplicated from `pages.ts` on purpose: a test that
 * imported the page list from the implementation would agree with it by
 * construction, including about a page that went missing.
 */
export const PAGE_IDS = ["setup", "q1", "q2", "q3", "q4", "q5"] as const;
export type PageId = (typeof PAGE_IDS)[number];

export const LAST_PAGE: PageId = PAGE_IDS[PAGE_IDS.length - 1];

export const SOURCE = "/home/ana/plate-reader";

export function currentPage(): PageId {
  const id = screen.getByTestId("work-import-page").getAttribute("data-page");
  if (!PAGE_IDS.includes(id as PageId)) throw new Error(`unknown page "${id}"`);
  return id as PageId;
}

/** How to answer a page on the way past it. */
export type PageAnswers = Partial<Record<PageId, () => void>>;

/**
 * FR-020's required answers, and nothing else. Questions 2 (with a source), 3,
 * 4 and 5 are skippable, so the default walk pages straight past them — which is
 * also the state FR-021 has to survive.
 *
 * Both are IDEMPOTENT, because a walk may cross a page more than once: a test
 * that goes back to change something on the setup page and forward again would
 * otherwise untick the checkbox it ticked on the way through, and fail on a
 * requirement it had already met.
 */
const REQUIRED_ANSWERS: PageAnswers = {
  setup: () => {
    const noCodebase = screen.getByTestId("work-import-no-codebase") as HTMLInputElement;
    const input = screen.getByTestId("work-import-source-input") as HTMLInputElement;
    if (!noCodebase.checked && !input.value) {
      fireEvent.change(input, { target: { value: SOURCE } });
    }
  },
  q1: () => {
    const box = screen.getByTestId("work-import-data-kind-Table / dataframe") as HTMLInputElement;
    if (!box.checked) fireEvent.click(box);
  },
};

/**
 * Drive the dialog to `target`, answering each page on the way with `answers`
 * (or the minimum FR-020 requires, where `answers` says nothing). Walks
 * backwards too, which is how a test returns to the setup page to change the
 * decision a later page depends on.
 *
 * THROWS RATHER THAN GIVING UP QUIETLY, naming the page that refused and the
 * reason it gave. A walker that silently stayed put would let a test assert
 * against page one in the belief it was on the last page — which is the whole
 * failure mode paging introduces to this suite.
 */
export function walkTo(target: PageId, answers: PageAnswers = {}): void {
  const plan: PageAnswers = { ...REQUIRED_ANSWERS, ...answers };
  const route: PageId[] = [];
  let steps = 0;
  while (currentPage() !== target) {
    steps += 1;
    if (steps > PAGE_IDS.length * 2) {
      throw new Error(`looping reaching "${target}"; route was ${route.join(" -> ")}`);
    }
    const page = currentPage();
    route.push(page);
    if (PAGE_IDS.indexOf(page) > PAGE_IDS.indexOf(target)) {
      fireEvent.click(screen.getByTestId("work-import-back"));
      continue;
    }
    plan[page]?.();
    // A skip control both answers and advances, so only push Next if the answer
    // did not already move on.
    if (currentPage() === page) fireEvent.click(screen.getByTestId("work-import-next"));
    if (currentPage() === page) {
      const said =
        screen.queryByTestId("work-import-blocking-reasons")?.textContent ?? "no reason given";
      throw new Error(`stuck on "${page}" reaching "${target}" via ${route.join(" -> ")}: ${said}`);
    }
  }
}

/** Attempt to leave the current page, and report what the dialog said instead. */
export function blockedGoingOn(): string {
  const before = currentPage();
  fireEvent.click(screen.getByTestId("work-import-next"));
  expect(currentPage()).toBe(before);
  return screen.getByTestId("work-import-blocking-reasons").textContent ?? "";
}
