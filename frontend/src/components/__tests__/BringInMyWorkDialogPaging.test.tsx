/**
 * ADR-053 spec 2 (#2001) — the Bring In My Work dialog, one question per page.
 *
 * Owner directive, 2026-08-07: the single scrolling questionnaire is unpleasant
 * to look at and users will not bother filling it in. Page one is the setup —
 * browse, provider, permission mode — and the questions start on page two, one
 * per page. That is also the shape #2001 described in the first place.
 *
 * This file pins the paging itself: the layout, moving between pages, and the
 * four requirements paging could have quietly broken. It is deliberately
 * separate from `BringInMyWorkDialog.test.tsx`, which pins what the dialog
 * ASKS and SENDS — that contract is unchanged by paging and its tests should
 * not have to be read as paging tests.
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { BringInMyWorkDialog } from "../BringInMyWorkDialog";
import {
  SETUP_STEP_TITLE,
  SKIP_LABEL,
  SKIPPED_NOTE,
  stepStatus,
} from "../BringInMyWorkDialog.parts/copy";
import { useAppStore } from "../../store";
import type { AgentAvailabilityResponse } from "../../lib/api/agentAvailability";
import {
  blockedGoingOn,
  CLAUDE,
  CODEX,
  currentPage,
  LAST_PAGE,
  PAGE_IDS,
  provider,
  ready,
  renderDialog,
  sessionResponse,
  settled,
  SOURCE,
  walkTo,
  type StartSession,
} from "./BringInMyWorkDialog.harness";

const QUESTION_TESTIDS = {
  q1: "work-import-q1",
  q2: "work-import-q2",
  q3: "work-import-q3",
  q4: "work-import-q4",
} as const;

beforeEach(() => {
  useAppStore.setState({
    currentProject: {
      id: "p1",
      name: "Demo",
      description: "",
      path: "/projects/demo",
      workflow_count: 0,
      workflows: [],
      current_workflow_id: "main",
    },
    terminalTabs: [],
    activeTerminalTabId: null,
    activeBottomTab: "config",
    bottomPanelCollapsed: true,
  });
});

afterEach(cleanup);

describe("the page layout the owner asked for", () => {
  it("opens on the setup page — where the work is, where it goes, and which agent", async () => {
    renderDialog();
    await settled();

    expect(currentPage()).toBe("setup");
    expect(screen.getByTestId("work-import-source-input")).toBeTruthy();
    expect(screen.getByTestId("work-import-source-browse")).toBeTruthy();
    expect(screen.getByTestId("work-import-no-codebase")).toBeTruthy();
    expect(screen.getByTestId("work-import-destination-group")).toBeTruthy();
    expect(screen.getByTestId("setup-provider-select")).toBeTruthy();
    expect(screen.getByTestId("setup-permission-group")).toBeTruthy();

    // "然后第二页开始问题" — and not one question before then.
    for (const testId of Object.values(QUESTION_TESTIDS)) {
      expect(screen.queryByTestId(testId)).toBeNull();
    }
  });

  it("gives each question a page of its own, in order", async () => {
    renderDialog();
    await settled();

    for (const page of ["q1", "q2", "q3", "q4"] as const) {
      walkTo(page);
      expect(currentPage()).toBe(page);
      // Exactly one question is on screen: the point of the change.
      const present = Object.entries(QUESTION_TESTIDS).filter(
        ([, testId]) => screen.queryByTestId(testId) !== null,
      );
      expect(present.map(([id]) => id)).toEqual([page]);
      // And none of the setup controls have followed it.
      expect(screen.queryByTestId("work-import-source-input")).toBeNull();
      expect(screen.queryByTestId("setup-provider-select")).toBeNull();
    }
  });

  it("says where the user is and how much is left, on every page", async () => {
    // Five pages of unknown length is its own kind of unpleasant.
    renderDialog();
    await settled();
    expect(screen.getByTestId("work-import-step-status").textContent).toBe(
      `${stepStatus(1, PAGE_IDS.length)} · ${SETUP_STEP_TITLE}`,
    );

    for (const [index, page] of PAGE_IDS.entries()) {
      walkTo(page);
      expect(screen.getByTestId("work-import-step-status").textContent).toContain(
        stepStatus(index + 1, PAGE_IDS.length),
      );
      expect(screen.getByTestId(`work-import-step-${index + 1}`)).toHaveAttribute(
        "aria-current",
        "step",
      );
    }
  });
});

describe("moving between pages", () => {
  it("back does not lose an answer", async () => {
    renderDialog();
    await settled();

    walkTo("q3", {
      q1: () => {
        fireEvent.click(screen.getByTestId("work-import-data-kind-Image"));
        fireEvent.change(screen.getByTestId("work-import-data-kinds-other"), {
          target: { value: "chromatograms" },
        });
      },
      q2: () =>
        fireEvent.change(screen.getByTestId("work-import-q2-input"), {
          target: { value: "Plate export in, one number per condition out." },
        }),
    });
    fireEvent.change(screen.getByTestId("work-import-q3-input"), {
      target: { value: "Let me pick the background patch." },
    });

    // All the way back to the start, then forward again.
    walkTo("setup");
    expect(screen.getByTestId("work-import-source-input")).toHaveValue(SOURCE);
    walkTo("q1", { setup: () => {} });
    expect(screen.getByTestId("work-import-data-kind-Image")).toBeChecked();
    expect(screen.getByTestId("work-import-data-kinds-other")).toHaveValue("chromatograms");
    walkTo("q2", { q1: () => {} });
    expect(screen.getByTestId("work-import-q2-input")).toHaveValue(
      "Plate export in, one number per condition out.",
    );
    walkTo("q3");
    expect(screen.getByTestId("work-import-q3-input")).toHaveValue(
      "Let me pick the background patch.",
    );
  });

  it("the progress indicator is a shortcut backwards, never a way past a requirement", async () => {
    renderDialog();
    await settled();

    // Forward from an unanswered setup page: clamped, and told why.
    fireEvent.click(screen.getByTestId("work-import-step-5"));
    expect(currentPage()).toBe("setup");
    expect(screen.getByTestId("work-import-blocking-reasons").textContent).toMatch(
      /Say where your work is/i,
    );

    walkTo("q4");
    // Backwards is always free.
    fireEvent.click(screen.getByTestId("work-import-step-2"));
    expect(currentPage()).toBe("q1");
    fireEvent.click(screen.getByTestId("work-import-step-4"));
    expect(currentPage()).toBe("q3");
  });

  it("back is offered on every page and does nothing on the first", async () => {
    renderDialog();
    await settled();
    expect(screen.getByTestId("work-import-back")).toBeDisabled();
    walkTo("q1");
    expect(screen.getByTestId("work-import-back")).toBeEnabled();
  });

  it("Enter advances where that is unambiguous, and never starts a session", async () => {
    const startSession = vi.fn<StartSession>(async () => sessionResponse());
    const { onClose } = renderDialog(ready(CLAUDE), { startSession });
    await settled();

    // In a one-line field, Enter means "done with this".
    fireEvent.change(screen.getByTestId("work-import-source-input"), {
      target: { value: SOURCE },
    });
    fireEvent.keyDown(screen.getByTestId("work-import-source-input"), { key: "Enter" });
    expect(currentPage()).toBe("q1");

    fireEvent.click(screen.getByTestId("work-import-data-kind-Image"));
    fireEvent.keyDown(screen.getByTestId("work-import-dialog"), { key: "Enter" });
    expect(currentPage()).toBe("q2");

    // In a textarea it does not: these answers are prose and may have
    // paragraphs, so Enter belongs to the box.
    fireEvent.keyDown(screen.getByTestId("work-import-q2-input"), { key: "Enter" });
    expect(currentPage()).toBe("q2");

    // And on the last page it does nothing at all. A stray keypress must not
    // spawn an agent in the user's project.
    walkTo(LAST_PAGE);
    fireEvent.keyDown(screen.getByTestId("work-import-dialog"), { key: "Enter" });
    expect(startSession).not.toHaveBeenCalled();

    // Escape still closes, from any page.
    fireEvent.keyDown(screen.getByTestId("work-import-dialog"), { key: "Escape" });
    expect(onClose).toHaveBeenCalled();
  });

  it("Enter on a page that is not answered yet reports what is missing", async () => {
    renderDialog();
    await settled();
    fireEvent.keyDown(screen.getByTestId("work-import-dialog"), { key: "Enter" });
    expect(currentPage()).toBe("setup");
    expect(screen.getByTestId("work-import-blocking-reasons").textContent).toMatch(
      /Say where your work is/i,
    );
  });
});

describe("FR-020 — what a page requires, and what it lets the user past", () => {
  it("does not accuse the user of anything before they have tried to move on", async () => {
    renderDialog();
    await settled();
    expect(screen.queryByTestId("work-import-blocking-reasons")).toBeNull();
  });

  it("blocks the setup page until the source or the no-codebase option is given", async () => {
    renderDialog();
    await settled();
    expect(blockedGoingOn()).toMatch(/Say where your work is, or choose/i);
    // …and puts the user in front of the control that fixes it.
    expect(document.activeElement).toBe(screen.getByTestId("work-import-source-input"));

    fireEvent.click(screen.getByTestId("work-import-no-codebase"));
    fireEvent.click(screen.getByTestId("work-import-next"));
    expect(currentPage()).toBe("q1");
  });

  it("blocks question 1 until a kind of data is chosen or written in", async () => {
    renderDialog();
    await settled();
    // The walk stops ON question 1, so it arrives with the question unanswered.
    walkTo("q1");
    fireEvent.click(screen.getByTestId("work-import-data-kind-Table / dataframe"));
    expect(screen.getByTestId("work-import-data-kind-Table / dataframe")).toBeChecked();
    // Untick it again and the page closes.
    fireEvent.click(screen.getByTestId("work-import-data-kind-Table / dataframe"));
    expect(blockedGoingOn()).toMatch(/Choose at least one kind of data/i);

    // The free-text field satisfies it just as well as a preset does.
    fireEvent.change(screen.getByTestId("work-import-data-kinds-other"), {
      target: { value: "chromatograms" },
    });
    fireEvent.click(screen.getByTestId("work-import-next"));
    expect(currentPage()).toBe("q2");
  });

  it("never blocks questions 3 and 4", async () => {
    renderDialog();
    await settled();
    walkTo("q3");
    fireEvent.click(screen.getByTestId("work-import-next"));
    expect(currentPage()).toBe("q4");
  });
});

describe("FR-020 / FR-021 — a skip is a choice, and it reaches the request", () => {
  it("skipping advances the page and says so on the way back", async () => {
    renderDialog();
    await settled();
    walkTo("q3");
    expect(screen.getByTestId("work-import-q3-skip").textContent).toBe(SKIP_LABEL);

    fireEvent.click(screen.getByTestId("work-import-q3-skip"));
    expect(currentPage()).toBe("q4");

    // Coming back, the skip is legible as a decision rather than as a blank the
    // user forgot — and it is not final.
    fireEvent.click(screen.getByTestId("work-import-back"));
    expect(screen.getByTestId("work-import-q3-skipped").textContent).toBe(SKIPPED_NOTE);
    fireEvent.change(screen.getByTestId("work-import-q3-input"), {
      target: { value: "Actually, let me pick the background patch." },
    });
    expect(screen.queryByTestId("work-import-q3-skipped")).toBeNull();
  });

  it("an answer given after un-skipping is the one that is sent", async () => {
    const startSession = vi.fn<StartSession>(async () => sessionResponse());
    renderDialog(ready(CLAUDE), { startSession });
    await settled();

    walkTo("q3");
    fireEvent.click(screen.getByTestId("work-import-q3-skip"));
    fireEvent.click(screen.getByTestId("work-import-back"));
    fireEvent.change(screen.getByTestId("work-import-q3-input"), {
      target: { value: "Let me pick the background patch." },
    });
    walkTo(LAST_PAGE);
    fireEvent.click(screen.getByTestId("work-import-start"));

    await waitFor(() => expect(startSession).toHaveBeenCalledTimes(1));
    const body = startSession.mock.calls[0][0];
    expect(body.interaction_wishes).toBe("Let me pick the background patch.");
    expect(body.skipped).not.toContain("interaction_wishes");
  });

  it("a question the user simply paged past is sent as skipped, never omitted", async () => {
    // FR-021 in its paged form. On one page an unanswered optional question was
    // a box the user scrolled by; paged, it is a page they pressed Next on. The
    // agent must be able to tell "they did not say" from "nothing applies", so
    // both are the same explicit skip in the request.
    const startSession = vi.fn<StartSession>(async () => sessionResponse());
    renderDialog(ready(CLAUDE), { startSession });
    await settled();

    walkTo(LAST_PAGE);
    fireEvent.click(screen.getByTestId("work-import-start"));

    await waitFor(() => expect(startSession).toHaveBeenCalledTimes(1));
    const body = startSession.mock.calls[0][0];
    expect(body.skipped).toEqual(["workflow_description", "interaction_wishes", "other_software"]);
    expect(body.workflow_description).toBeNull();
    expect(body.interaction_wishes).toBeNull();
    expect(body.other_software).toBeNull();
  });

  it("offers no skip on a question that is required", async () => {
    // FR-016 / FR-017 — the decision is made on page one and the consequence
    // lands two pages later. A skip control that was present but ineffective
    // would be worse than none.
    renderDialog();
    await settled();
    walkTo("q2", { setup: () => fireEvent.click(screen.getByTestId("work-import-no-codebase")) });
    expect(screen.queryByTestId("work-import-q2-skip")).toBeNull();
    expect(screen.queryByTestId("work-import-skip-help")).toBeNull();

    // …and it comes back if the user changes their mind about the codebase.
    walkTo("setup");
    fireEvent.click(screen.getByTestId("work-import-no-codebase"));
    walkTo("q2");
    expect(screen.getByTestId("work-import-q2-skip")).toBeTruthy();
  });
});

describe("FR-005 — a user learns there is no usable agent on page one, not page five", () => {
  const NOT_INSTALLED: AgentAvailabilityResponse = {
    state: "not_installed",
    providers: [
      provider({
        key: "claude-code",
        label: "Claude Code",
        state: "not_installed",
        next_step: "Install the Claude Code CLI so that `claude` is on your PATH.",
      }),
    ],
  };

  it("shows the guidance on the setup page and holds the user there", async () => {
    renderDialog(NOT_INSTALLED);
    await settled();

    expect(currentPage()).toBe("setup");
    expect(screen.getByTestId("work-import-guidance-not_installed")).toBeTruthy();
    expect(screen.getByTestId("work-import-agent-blocks-paging")).toBeTruthy();

    fireEvent.change(screen.getByTestId("work-import-source-input"), {
      target: { value: SOURCE },
    });
    expect(blockedGoingOn()).toMatch(/No agent is ready to run the session/i);
    // Nowhere to start from, and no way to spend five pages finding that out.
    expect(screen.queryByTestId("work-import-start")).toBeNull();
  });

  it("releases the user as soon as an agent becomes usable", async () => {
    const fetchAvailability = vi
      .fn<(options?: { refresh?: boolean }) => Promise<AgentAvailabilityResponse>>()
      .mockResolvedValueOnce(NOT_INSTALLED)
      .mockResolvedValueOnce(ready(CLAUDE));

    render(
      <BringInMyWorkDialog
        onClose={vi.fn()}
        fetchAvailability={fetchAvailability}
        startSession={vi.fn<StartSession>(async () => sessionResponse())}
      />,
    );
    await settled();
    fireEvent.change(screen.getByTestId("work-import-source-input"), {
      target: { value: SOURCE },
    });
    expect(blockedGoingOn()).toMatch(/No agent is ready/i);

    // `not_installed` has no retry control of its own — the user installs an
    // agent and reopens — so this stands in for the probe resolving usable.
    cleanup();
    renderDialog(ready(CLAUDE));
    await settled();
    walkTo(LAST_PAGE);
    expect(screen.getByTestId("work-import-start")).toBeTruthy();
  });

  it("puts the guidance in place of the start action if it is only learnt late", async () => {
    // The probe is still in flight while the user answers, and resolves to "no
    // usable agent" only once they are on the last page. FR-005 is a statement
    // about the page that carries the start action, wherever the user got to.
    let settle: (value: AgentAvailabilityResponse) => void = () => {};
    render(
      <BringInMyWorkDialog
        onClose={vi.fn()}
        fetchAvailability={() =>
          new Promise<AgentAvailabilityResponse>((resolve) => {
            settle = resolve;
          })
        }
        startSession={vi.fn<StartSession>(async () => sessionResponse())}
      />,
    );
    // FR-035 — an unresolved probe never holds the user up.
    walkTo(LAST_PAGE);
    expect(screen.getByTestId("work-import-probing")).toBeTruthy();
    expect(screen.queryByTestId("work-import-start")).toBeNull();

    settle(NOT_INSTALLED);
    await waitFor(() => expect(screen.queryByTestId("work-import-probing")).toBeNull());
    expect(currentPage()).toBe(LAST_PAGE);
    expect(screen.getByTestId("work-import-guidance-not_installed")).toBeTruthy();
    expect(screen.queryByTestId("work-import-start")).toBeNull();
    // The caveat is still there: it is not conditioned on being able to start.
    expect(screen.getByTestId("work-import-caveat")).toBeTruthy();
  });

  it("does not hold up a user who has a choice of providers still to make", async () => {
    // Two usable agents: the choice blocks the setup page (it is where the
    // choice is), and making it releases the whole flow.
    renderDialog(ready(CLAUDE, CODEX));
    await settled();
    fireEvent.change(screen.getByTestId("work-import-source-input"), {
      target: { value: SOURCE },
    });
    expect(blockedGoingOn()).toMatch(/Choose which agent runs the session/i);
    fireEvent.change(screen.getByTestId("setup-provider-select"), { target: { value: "codex" } });
    walkTo(LAST_PAGE);
    expect(screen.getByTestId("work-import-start")).toBeTruthy();
  });
});
