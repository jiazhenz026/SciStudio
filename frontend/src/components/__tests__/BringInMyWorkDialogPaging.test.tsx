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
import { act, cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  Q5_HELP,
  Q5_LABEL,
  SETUP_STEP_TITLE,
  SKIP_LABEL,
  SKIPPED_MARKER,
  stepStatus,
} from "../BringInMyWorkDialog.parts/copy";
import {
  REASON_NO_PERMISSION_MODE,
  REASON_NO_PROJECT,
  REASON_NO_PROVIDER,
} from "../BringInMyWorkDialog.parts/formState";
import { useAppStore } from "../../store";
import {
  blockedGoingOn,
  CLAUDE,
  CODEX,
  currentPage,
  LAST_PAGE,
  PAGE_IDS,
  provider,
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
  q5: "work-import-q5",
} as const;

/**
 * #2454 — provider and permission mode start unchosen. A test that answers the
 * setup page itself has to make that choice too, as the user would.
 */
function chooseAgent(name = "claude-code"): void {
  fireEvent.change(screen.getByTestId("setup-provider-select"), { target: { value: name } });
  fireEvent.click(screen.getByTestId("setup-permission-safe"));
}

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

    for (const page of ["q1", "q2", "q3", "q4", "q5"] as const) {
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
    // A run of pages of unknown length is its own kind of unpleasant.
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
      /Required: where your work is/i,
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
    const { onClose } = renderDialog([CLAUDE], { startSession });
    await settled();

    chooseAgent();
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
      /Required: where your work is/i,
    );
  });
});

describe("FR-020 — what a page requires, and what it lets the user past", () => {
  it("does not accuse the user of anything before they have tried to move on", async () => {
    renderDialog();
    await settled();
    expect(screen.queryByTestId("work-import-blocking-reasons")).toBeNull();
  });

  it("says what is missing in the attention colour, on every page that can block", async () => {
    // The owner could not see the old message: it was `text-stone-500`, the
    // same weight as a hint, and it opened "Before you go on:" which he read as
    // condescending (2026-08-08). An incomplete page has to be obvious at a
    // glance. The treatment is the repository's existing dialog error shape —
    // `Git/CommitDialog.tsx` — not a new colour.
    /** The banner shown after trying to leave a page that is not answered. */
    function attentionBanner(): HTMLElement {
      fireEvent.click(screen.getByTestId("work-import-next"));
      const banner = screen.getByTestId("work-import-blocking-reasons");
      expect(banner.className).toContain("bg-red-50");
      expect(banner.className).toContain("text-red-700");
      expect(banner).toHaveAttribute("role", "alert");
      expect(banner).toHaveAttribute("aria-live", "assertive");
      // No coaxing lead-in.
      expect(banner.textContent).not.toMatch(/before you go on/i);
      return banner;
    }

    renderDialog();
    await settled();

    // Page 1 — the source, or the no-codebase option.
    expect(attentionBanner().textContent).toMatch(/Required: where your work is/i);
    expect(currentPage()).toBe("setup");
    chooseAgent();
    fireEvent.change(screen.getByTestId("work-import-source-input"), {
      target: { value: SOURCE },
    });
    fireEvent.click(screen.getByTestId("work-import-next"));
    // Answering clears it rather than leaving a stale warning behind.
    expect(screen.queryByTestId("work-import-blocking-reasons")).toBeNull();

    // Page 2 — question 1.
    expect(currentPage()).toBe("q1");
    expect(attentionBanner().textContent).toMatch(/Required: at least one kind of data/i);
    expect(currentPage()).toBe("q1");

    // Page 3 — question 2, which blocks only in no-codebase mode (FR-016,
    // FR-017) and gets exactly the same treatment there.
    cleanup();
    renderDialog();
    await settled();
    walkTo("q2", {
      setup: () => {
        chooseAgent();
        fireEvent.click(screen.getByTestId("work-import-no-codebase"));
      },
    });
    expect(attentionBanner().textContent).toMatch(/Required: a description of your workflow/i);
    expect(currentPage()).toBe("q2");
  });

  it("never puts the attention colour on a question the user skipped", async () => {
    // FR-020 — the attention treatment means "required and unanswered". A skip
    // is a legitimate answer, so it gets a neutral state chip and nothing else.
    renderDialog();
    await settled();
    walkTo("q3");
    fireEvent.click(screen.getByTestId("work-import-q3-skip"));
    fireEvent.click(screen.getByTestId("work-import-back"));

    const marker = screen.getByTestId("work-import-q3-skipped");
    expect(marker.textContent).toBe(SKIPPED_MARKER);
    expect(marker.className).not.toMatch(/red/);
    expect(screen.queryByTestId("work-import-blocking-reasons")).toBeNull();
  });

  it("blocks the setup page until the source or the no-codebase option is given", async () => {
    renderDialog();
    await settled();
    expect(blockedGoingOn()).toMatch(/Required: where your work is, or /i);
    // …and puts the user in front of the control that fixes it.
    expect(document.activeElement).toBe(screen.getByTestId("work-import-source-input"));

    chooseAgent();
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
    expect(blockedGoingOn()).toMatch(/Required: at least one kind of data/i);

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
    expect(screen.getByTestId("work-import-q3-skipped").textContent).toBe(SKIPPED_MARKER);
    fireEvent.change(screen.getByTestId("work-import-q3-input"), {
      target: { value: "Actually, let me pick the background patch." },
    });
    expect(screen.queryByTestId("work-import-q3-skipped")).toBeNull();
  });

  it("an answer given after un-skipping is the one that is sent", async () => {
    const startSession = vi.fn<StartSession>(async () => sessionResponse());
    renderDialog([CLAUDE], { startSession });
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
    renderDialog([CLAUDE], { startSession });
    await settled();

    walkTo(LAST_PAGE);
    fireEvent.click(screen.getByTestId("work-import-start"));

    await waitFor(() => expect(startSession).toHaveBeenCalledTimes(1));
    const body = startSession.mock.calls[0][0];
    expect(body.skipped).toEqual([
      "workflow_description",
      "interaction_wishes",
      "other_software",
      "anything_else",
    ]);
    expect(body.workflow_description).toBeNull();
    expect(body.interaction_wishes).toBeNull();
    expect(body.other_software).toBeNull();
    expect(body.anything_else).toBeNull();
  });

  it("offers no skip on a question that is required", async () => {
    // FR-016 / FR-017 — the decision is made on page one and the consequence
    // lands two pages later. A skip control that was present but ineffective
    // would be worse than none.
    renderDialog();
    await settled();
    walkTo("q2", {
      setup: () => {
        chooseAgent();
        fireEvent.click(screen.getByTestId("work-import-no-codebase"));
      },
    });
    expect(screen.queryByTestId("work-import-q2-skip")).toBeNull();
    // Only Back and Next in the navigation row — no third control.
    expect(within(screen.getByTestId("work-import-nav-actions")).getAllByRole("button")).toEqual([
      screen.getByTestId("work-import-next"),
    ]);

    // …and it comes back if the user changes their mind about the codebase.
    walkTo("setup");
    fireEvent.click(screen.getByTestId("work-import-no-codebase"));
    walkTo("q2");
    expect(screen.getByTestId("work-import-q2-skip")).toBeTruthy();
  });
});

describe("FR-005 — the agent is chosen on page one, exactly as in AI Chat (#2454)", () => {
  it("starts with no provider and no permission mode chosen", async () => {
    renderDialog([CLAUDE]);
    await settled();

    expect(screen.getByTestId("setup-provider-select")).toHaveValue("");
    for (const mode of ["safe", "auto", "dangerous"]) {
      expect(screen.getByTestId(`setup-permission-${mode}`)).toHaveAttribute(
        "aria-checked",
        "false",
      );
    }
  });

  it("holds the setup page until a provider is chosen, then until a permission mode is", async () => {
    renderDialog([CLAUDE, CODEX]);
    await settled();
    fireEvent.change(screen.getByTestId("work-import-source-input"), {
      target: { value: SOURCE },
    });

    expect(blockedGoingOn()).toBe(REASON_NO_PROVIDER);
    // …and puts the user in front of the picker that fixes it.
    expect(document.activeElement).toBe(screen.getByTestId("setup-provider-select"));

    fireEvent.change(screen.getByTestId("setup-provider-select"), { target: { value: "codex" } });
    expect(blockedGoingOn()).toBe(REASON_NO_PERMISSION_MODE);

    fireEvent.click(screen.getByTestId("setup-permission-safe"));
    fireEvent.click(screen.getByTestId("work-import-next"));
    expect(currentPage()).toBe("q1");
  });

  it("lists a provider that is not installed, disabled, and never lets it be chosen", async () => {
    renderDialog([CLAUDE, provider({ name: "codex", label: "Codex", available: false })]);
    await settled();

    const option = screen.getByTestId("setup-provider-option-codex") as HTMLOptionElement;
    expect(option.disabled).toBe(true);
    expect(option.textContent).toContain("(not installed)");
    expect(
      (screen.getByTestId("setup-provider-option-claude-code") as HTMLOptionElement).disabled,
    ).toBe(false);
  });

  it("shows AI Chat's no-providers notice, and blocks, when nothing is installed", async () => {
    renderDialog([provider({ name: "claude-code", label: "Claude Code", available: false })]);
    await settled();

    expect(screen.getByTestId("setup-no-providers-notice")).toBeTruthy();
    expect(screen.queryByTestId("setup-provider-select")).toBeNull();
    fireEvent.change(screen.getByTestId("work-import-source-input"), {
      target: { value: SOURCE },
    });
    expect(blockedGoingOn()).toBe(REASON_NO_PROVIDER);
    // Nowhere to start from, and no way to spend five pages finding that out.
    expect(screen.queryByTestId("work-import-start")).toBeNull();
  });

  it("does not block a provider that is installed but not signed in", async () => {
    // The CLI runs its own sign-in inside the session, as in AI Chat.
    const startSession = vi.fn<StartSession>(async () => sessionResponse());
    renderDialog([provider({ name: "claude-code", label: "Claude Code", logged_in: false })], {
      startSession,
    });
    await settled();

    const option = screen.getByTestId("setup-provider-option-claude-code") as HTMLOptionElement;
    expect(option.disabled).toBe(false);
    expect(option.textContent).toContain("(not logged in)");

    walkTo(LAST_PAGE);
    expect(screen.getByTestId("work-import-start")).toBeEnabled();
    fireEvent.click(screen.getByTestId("work-import-start"));
    await waitFor(() => expect(startSession).toHaveBeenCalledTimes(1));
    expect(startSession.mock.calls[0][0]).toMatchObject({
      provider: "claude-code",
      permission_mode: "safe",
    });
  });

  it("blocks the setup page when the provider status cannot be read", async () => {
    renderDialog(new Error("backend down"));
    await settled();

    expect(screen.getByTestId("setup-status-error")).toBeTruthy();
    fireEvent.change(screen.getByTestId("work-import-source-input"), {
      target: { value: SOURCE },
    });
    expect(blockedGoingOn()).toBe(REASON_NO_PROVIDER);
  });

  it("always shows Start on the last page, disabled with the reason when it cannot start", async () => {
    const startSession = vi.fn<StartSession>(async () => sessionResponse());
    renderDialog([CLAUDE], { startSession });
    await settled();
    walkTo(LAST_PAGE);
    expect(screen.getByTestId("work-import-start")).toBeEnabled();

    // The project closes under the dialog after every page was answered.
    act(() => useAppStore.setState({ currentProject: null }));
    expect(screen.getByTestId("work-import-start")).toBeDisabled();
    expect(screen.getByTestId("work-import-blocking-reasons").textContent).toBe(REASON_NO_PROJECT);
    fireEvent.click(screen.getByTestId("work-import-start"));
    expect(startSession).not.toHaveBeenCalled();
  });
});

/**
 * FR-019a — question 5, added after the feature shipped (owner, 2026-08-17).
 *
 * It lives here rather than with the other questions because what is new about
 * it is where it sits: it is the page the start action is now on, and the last
 * thing the dialog asks. What it collects is asserted the same way every other
 * answer is.
 */
describe("FR-019a — the last question is the open one", () => {
  it("is asked last, names no subject, and offers a skip", async () => {
    renderDialog();
    await settled();

    walkTo("q5");
    // Last, and last for a reason: asked earlier, an open question collects the
    // answers the specific questions were going to collect, and worse ones.
    expect(currentPage()).toBe(LAST_PAGE);
    expect(screen.getByTestId("work-import-q5-skip")).toBeTruthy();

    // It names no subject — that is the whole of what makes it question 5
    // rather than a sixth specific question. Its help line offers kinds of
    // thing to say, and deliberately not an example answer, which would narrow
    // exactly the question that exists not to be narrow.
    expect(screen.getByTestId("work-import-q5").textContent).toContain(Q5_LABEL);
    expect(screen.getByTestId("work-import-q5-help").textContent).toBe(Q5_HELP);
  });

  it("FR-023: its answer reaches the request like any other", async () => {
    const startSession = vi.fn<StartSession>(async () => sessionResponse());
    renderDialog([CLAUDE], { startSession });
    await settled();

    walkTo(LAST_PAGE);
    fireEvent.change(screen.getByTestId("work-import-q5-input"), {
      target: { value: "Ask me before you touch anything under raw/." },
    });
    fireEvent.click(screen.getByTestId("work-import-start"));

    await waitFor(() => expect(startSession).toHaveBeenCalledTimes(1));
    const body = startSession.mock.calls[0][0];
    expect(body.anything_else).toBe("Ask me before you touch anything under raw/.");
    expect(body.skipped).not.toContain("anything_else");
  });
});
