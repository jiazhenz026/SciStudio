/**
 * ADR-053 spec 2 (#2001) — Bring In My Work dialog.
 *
 * Covers the acceptance scenarios of User Stories 1–4 that live on this side of
 * the boundary: the framing questions, the no-codebase path, graded agent
 * availability, and the correctness caveat.
 *
 * The availability payload is supplied through the `fetchAvailability` seam so
 * these tests pin contract C1 (`checklist §7.1`) directly, rather than the
 * transport of the module that will implement it.
 *
 * THE DIALOG IS PAGED, so a test that renders it sees ONE page. Everything here
 * drives it to the page it means to assert about through the shared `walkTo`,
 * which throws if a page will not let it through — the alternative is a test
 * that quietly passes because it searched page one for something on page four.
 * The paging rules themselves are pinned in `BringInMyWorkDialogPaging.test.tsx`.
 */
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type * as ApiModule from "../../lib/api";

vi.mock("../../lib/api", async () => {
  const actual = await vi.importActual<typeof ApiModule>("../../lib/api");
  return { ...actual, api: { ...actual.api, openNativeDialog: vi.fn() } };
});

import { BringInMyWorkDialog } from "../BringInMyWorkDialog";
import {
  CAVEAT_BODY,
  DATA_KIND_GROUPS,
  Q1_LABEL,
  Q2_LABEL,
  Q3_LABEL,
  Q4_LABEL,
  SOURCE_LABEL,
} from "../BringInMyWorkDialog.parts/copy";
import { validateWorkImportRequest } from "../../lib/api/workImport";
import { api } from "../../lib/api";
import { useAppStore } from "../../store";
import type { AgentAvailabilityResponse } from "../../lib/api/agentAvailability";
import {
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
  type PageAnswers,
  type PageId,
  type StartSession,
} from "./BringInMyWorkDialog.harness";

/** Answer only what FR-020 requires, then stop on the last page. */
function walkToStart(answers: PageAnswers = {}): void {
  walkTo(LAST_PAGE, answers);
}

const NO_CODEBASE: PageAnswers = {
  setup: () => fireEvent.click(screen.getByTestId("work-import-no-codebase")),
  q2: () =>
    fireEvent.change(screen.getByTestId("work-import-q2-input"), {
      target: { value: "Every Monday I open the export in Excel and average the replicates." },
    }),
};

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
  vi.mocked(api.openNativeDialog).mockReset();
});

afterEach(cleanup);

describe("FR-037 / FR-038 — the correctness caveat", () => {
  it("is present, in full, on the page that carries the start action", async () => {
    renderDialog();
    await settled();
    walkToStart();

    const caveat = screen.getByTestId("work-import-caveat");
    expect(caveat.textContent).toContain(CAVEAT_BODY);
    // All four claims FR-037 requires.
    expect(caveat.textContent).toMatch(/can make mistakes/i);
    expect(caveat.textContent).toMatch(/instructed to check/i);
    expect(caveat.textContent).toMatch(/does not guarantee/i);
    expect(caveat.textContent).toMatch(/review the result yourself/i);
    // FR-004 / FR-038 — it is on screen at the same moment the start action is.
    expect(screen.getByTestId("work-import-start")).toBeTruthy();
  });

  it("is not weakened or omitted in no-codebase mode", async () => {
    renderDialog();
    await settled();
    walkToStart(NO_CODEBASE);
    expect(screen.getByTestId("work-import-caveat").textContent).toContain(CAVEAT_BODY);
  });

  it("is not dismissible and cannot be bypassed before the start action", async () => {
    renderDialog();
    await settled();
    walkToStart();
    const caveat = screen.getByTestId("work-import-caveat");
    // No dismiss/close/hide affordance inside it, in either mode (FR-038).
    expect(within(caveat).queryAllByRole("button")).toHaveLength(0);
    expect(caveat.getAttribute("hidden")).toBeNull();
  });

  it("no page carries a start action without carrying the caveat", async () => {
    // FR-038 in its paged form. On the scrolling page the caveat and the button
    // merely shared a footer; paged, "the user has seen it" is a claim about
    // which page they are on, so it is checked on every page there is.
    renderDialog();
    await settled();
    for (const page of PAGE_IDS) {
      walkTo(page);
      const hasStart = screen.queryByTestId("work-import-start") !== null;
      const hasCaveat = screen.queryByTestId("work-import-caveat") !== null;
      expect(hasStart && !hasCaveat).toBe(false);
    }
  });
});

describe("FR-008 – FR-010 — source, browse, and the no-codebase path", () => {
  it("the browse control asks for a directory, not a file", async () => {
    vi.mocked(api.openNativeDialog).mockResolvedValue({ paths: [SOURCE] });
    renderDialog();
    await settled();

    fireEvent.click(screen.getByTestId("work-import-source-browse"));
    await waitFor(() => expect(api.openNativeDialog).toHaveBeenCalled());
    expect(vi.mocked(api.openNativeDialog).mock.calls[0][0]).toBe("directory");
    await waitFor(() => expect(screen.getByTestId("work-import-source-input")).toHaveValue(SOURCE));
  });

  it("selecting 'I don't have a codebase' disables the source field and leaves the rest in effect", async () => {
    renderDialog();
    await settled();
    fireEvent.click(screen.getByTestId("work-import-no-codebase"));

    expect(screen.getByTestId("work-import-source-input")).toBeDisabled();
    expect(screen.getByTestId("work-import-source-browse")).toBeDisabled();
    // FR-010 — every other field remains in effect, including the destination
    // and the agent setup, which share the setup page with it.
    expect(screen.getByTestId("work-import-destination-user_library")).toBeEnabled();
    expect(screen.getByTestId("setup-permission-safe")).toBeEnabled();
    // And the questions, which are now pages of their own rather than fields
    // below it — reachable with no source location given.
    walkTo("q1", { setup: () => {} });
    expect(screen.getByTestId("work-import-data-kind-Image")).toBeEnabled();
  });
});

describe("FR-013 – FR-015 — question 1", () => {
  it("groups the presets so both readings of the same data can be selected", async () => {
    // FR-014 IS NOW CARRIED ENTIRELY BY THIS STRUCTURE. A sentence used to say
    // "the two lists describe the same data in different ways, so picking from
    // both is normal"; the owner cut it as padding (2026-08-08). FR-014 asks
    // for the presets to be "visually grouped so it is clear both may be
    // selected, rather than presented as one flat list", which is a
    // requirement about structure — so the structure is what is pinned: two
    // separate groups, each with its own visible legend, holding the two
    // competing readings, both selectable at once.
    renderDialog();
    await settled();
    walkTo("q1");

    const arrangement = screen.getByTestId("work-import-data-kind-group-arrangement");
    const domain = screen.getByTestId("work-import-data-kind-group-domain");
    expect(arrangement).not.toBe(domain);
    for (const group of DATA_KIND_GROUPS) {
      const fieldset = screen.getByTestId(`work-import-data-kind-group-${group.id}`);
      // A legend the user can read, not a bare box.
      expect(within(fieldset).getByText(group.legend)).toBeVisible();
      for (const option of group.options) {
        expect(within(fieldset).getByTestId(`work-import-data-kind-${option}`)).toBeTruthy();
      }
    }

    // The two readings of the same data live in different groups…
    expect(within(arrangement).getByTestId("work-import-data-kind-Series")).toBeTruthy();
    expect(within(domain).getByTestId("work-import-data-kind-Time series")).toBeTruthy();
    // …and picking both is possible, which is the thing the sentence used to say.
    fireEvent.click(screen.getByTestId("work-import-data-kind-Series"));
    fireEvent.click(screen.getByTestId("work-import-data-kind-Time series"));
    expect(screen.getByTestId("work-import-data-kind-Series")).toBeChecked();
    expect(screen.getByTestId("work-import-data-kind-Time series")).toBeChecked();
  });

  it("offers a free-text field for anything not listed", async () => {
    renderDialog();
    await settled();
    walkTo("q1");
    fireEvent.change(screen.getByTestId("work-import-data-kinds-other"), {
      target: { value: "chromatograms" },
    });
    expect(screen.getByTestId("work-import-data-kinds-other")).toHaveValue("chromatograms");
  });
});

describe("FR-016 – FR-020 — questions 2 to 4 and their skips", () => {
  it("question 2 is skippable with a source and required without one", async () => {
    renderDialog();
    await settled();
    walkTo("q2");

    expect(screen.getByTestId("work-import-q2-skip")).toBeTruthy();
    expect(screen.queryByTestId("work-import-q2-required")).toBeNull();
    const withSourceHelp = screen.getByTestId("work-import-q2-help").textContent ?? "";

    // FR-016 / FR-017 — the requirement is DECIDED on the setup page and
    // ENFORCED here, two pages later, so the round trip is the thing to pin.
    walkTo("setup");
    fireEvent.click(screen.getByTestId("work-import-no-codebase"));
    walkTo("q2", { setup: () => {} });

    expect(screen.queryByTestId("work-import-q2-skip")).toBeNull();
    expect(screen.getByTestId("work-import-q2-required")).toBeTruthy();

    // FR-017 — the no-codebase wording asks for more than the codebase wording.
    const noCodebaseHelp = screen.getByTestId("work-import-q2-help").textContent ?? "";
    expect(noCodebaseHelp).not.toBe(withSourceHelp);
    expect(noCodebaseHelp.length).toBeGreaterThan(withSourceHelp.length);
    expect(noCodebaseHelp).toMatch(/steps/i);
    expect(noCodebaseHelp).toMatch(/right/i);
  });

  it("questions 3 and 4 are skippable and question 3 carries concrete examples", async () => {
    renderDialog();
    await settled();
    walkTo("q3");
    expect(screen.getByTestId("work-import-q3-skip")).toBeTruthy();
    // FR-018 — without examples the question is too abstract to answer.
    const q3Help = screen.getByTestId("work-import-q3-help").textContent ?? "";
    expect(q3Help).toMatch(/background/i);
    expect(q3Help).toMatch(/segmentation mask/i);

    walkTo("q4");
    expect(screen.getByTestId("work-import-q4-skip")).toBeTruthy();
  });

  it("a skip reads as a choice rather than an abandoned field", async () => {
    // FR-020 USED TO BE CARRIED BY COPY AND IS NOW CARRIED BY STRUCTURE, so
    // this asserts the structure. The label was "Skip — let the agent work this
    // out" with a sentence under it explaining what the agent would be told;
    // the owner cut both as filler (2026-08-08). What makes a skip read as a
    // legitimate choice rather than an abandoned field is now three facts, and
    // each one is checked here because nothing else would notice losing it.
    renderDialog();
    await settled();
    walkTo("q3");
    const skip = screen.getByTestId("work-import-q3-skip");

    // 1. It is a button, not a checkbox under the input.
    expect(skip.tagName).toBe("BUTTON");

    // 2. It is a sibling of the primary action, in the same cluster — a peer of
    //    "Next", not a footnote below it.
    const actions = screen.getByTestId("work-import-nav-actions");
    expect(skip.parentElement).toBe(actions);
    expect(screen.getByTestId("work-import-next").parentElement).toBe(actions);

    // 3. It lives in the navigation row rather than inside the question, which
    //    is what makes it read as a way of moving on.
    expect(screen.getByTestId("work-import-nav").contains(skip)).toBe(true);
    expect(screen.getByTestId("work-import-q3").contains(skip)).toBe(false);
  });
});

describe("FR-006 / FR-007 — who the questions are written for", () => {
  /**
   * The words a scientist cannot be asked for. Half of them name SciStudio
   * concepts a first-day user has never met (FR-006); half name software
   * development (FR-007).
   */
  const FORBIDDEN = [
    /interpreter/i,
    /virtual environment/i,
    /dependenc/i,
    /\bports?\b/i,
    /data type/i,
    /interactive block/i,
    /previewer/i,
    /\bpip\b/i,
    /\bconda\b/i,
    /\bschema\b/i,
  ];

  /**
   * Everything the user can read on the page currently rendered.
   *
   * `textContent` alone would miss the examples, which are placeholders and
   * therefore attributes — and the examples are exactly where a well-meaning
   * edit would reach for a developer's vocabulary.
   */
  function visibleText(): string {
    const dialog = screen.getByTestId("work-import-dialog");
    const placeholders = Array.from(dialog.querySelectorAll("[placeholder]"))
      .map((element) => element.getAttribute("placeholder") ?? "")
      .join("\n");
    return `${dialog.textContent ?? ""}\n${placeholders}`;
  }

  /**
   * Walk every page, checking each one as it renders.
   *
   * THIS IS THE POINT OF THE TEST AND IT IS EASY TO LOSE. Before paging, one
   * render put the whole dialog on screen and one search covered it. Paged, a
   * search after a single render reads page one and reports on five — the guard
   * would keep passing while guarding almost nothing. So the walk visits each
   * page in turn, and then asserts BOTH that it reached all five and that what
   * it read contains the actual questions: an empty page, or a page that
   * silently stopped rendering, must fail here rather than pass by vacuity.
   */
  function everyPageIsAnswerableByAScientist(answers: PageAnswers = {}): void {
    const visited: PageId[] = [];
    let everything = "";
    for (const page of PAGE_IDS) {
      walkTo(page, answers);
      visited.push(currentPage());
      const text = visibleText();
      everything += `\n${text}`;
      for (const forbidden of FORBIDDEN) expect(text).not.toMatch(forbidden);
    }

    expect(visited).toEqual([...PAGE_IDS]);
    // The walk read real content, not five blanks.
    for (const label of [SOURCE_LABEL, Q1_LABEL, Q2_LABEL, Q3_LABEL, Q4_LABEL, CAVEAT_BODY]) {
      expect(everything).toContain(label);
    }
  }

  it("asks nothing that needs SciStudio or software-development knowledge", async () => {
    renderDialog();
    await settled();
    everyPageIsAnswerableByAScientist();
  });

  it("asks nothing that needs it in no-codebase mode either", async () => {
    // A different question-2 prompt, a different placeholder, and the mode with
    // the least context — so the wording most tempted to ask for detail only a
    // developer could give (FR-017).
    renderDialog();
    await settled();
    everyPageIsAnswerableByAScientist(NO_CODEBASE);
  });

  it("does not explain a control that already explains itself", async () => {
    /*
     * The owner's 2026-08-08 pass, kept from creeping back.
     *
     * Every sentence below was on these pages and was cut for the same reason:
     * it described a control that is on screen saying the same thing. They are
     * pinned by their exact words rather than by a rule, because "is this
     * filler?" is a judgement and "did somebody put this paragraph back?" is
     * not. A deliberate re-add should delete the line here too, and then be
     * visible in review as what it is.
     */
    const CUT = [
      // Page one's introduction.
      /You already have a way of doing this work/i,
      // The source field's help line, above a Browse button.
      /Point us at the folder your analysis lives in/i,
      // Question 1's help line; FR-014 is carried by the groups themselves.
      /picking from both is normal/i,
      // What skipping does; the Skip button beside Next is the affordance.
      /let the agent work this out/i,
      /knows to ask rather than assume/i,
      // The lead-in on the blocked-page message.
      /before you go on/i,
      // What the Start button does, above the caveat it was competing with.
      /This opens an ordinary chat session/i,
      // The paragraph beside the provider picker.
      /You can still start with one of the agents above/i,
      /not usable right now/i,
    ];

    renderDialog(ready(CLAUDE, CODEX));
    await settled();
    for (const page of PAGE_IDS) {
      walkTo(page, {
        setup: () => {
          fireEvent.change(screen.getByTestId("work-import-source-input"), {
            target: { value: SOURCE },
          });
          fireEvent.change(screen.getByTestId("setup-provider-select"), {
            target: { value: "codex" },
          });
        },
      });
      const text = screen.getByTestId("work-import-dialog").textContent ?? "";
      for (const gone of CUT) expect(text).not.toMatch(gone);
    }
  });
});

describe("FR-005 / FR-031 / FR-034 — graded availability", () => {
  it("names the executable to install and where SciStudio looked, and offers no start action", async () => {
    // FR-031's guidance column for this state is "Installation instructions"
    // and SC-002 requires "a specific next action". Asserting only that the
    // block exists would pass against an empty body, which is how the shipped
    // "Set one of the supported agents up" survived review: it named the
    // providers and then named nothing to do. The instruction is the backend's
    // `next_step`, so what is pinned here is that the dialog RENDERS it.
    renderDialog({
      state: "not_installed",
      providers: [
        provider({
          key: "claude-code",
          label: "Claude Code",
          state: "not_installed",
          next_step:
            "Install the Claude Code CLI so that `claude` is on your PATH and in ~/.local/bin.",
        }),
      ],
    });
    await settled();
    const panel = screen.getByTestId("work-import-guidance-not_installed");
    expect(panel.textContent).toContain("Claude Code");
    expect(panel.textContent).toContain("`claude`");
    expect(panel.textContent).toContain("~/.local/bin");
    expect(screen.queryByTestId("work-import-start")).toBeNull();
  });

  it("names the sign-in command for the detected provider", async () => {
    // FR-031's guidance column here is "Login instructions for the detected
    // provider". "Sign in the way that agent expects" is the explicit absence
    // of that, so this asserts an actual command reaches the user rather than
    // that the panel contains the word "sign".
    renderDialog({
      state: "not_authenticated",
      providers: [
        provider({
          key: "codex",
          label: "Codex",
          state: "not_authenticated",
          next_step: "Sign in by running `codex login` in a terminal.",
        }),
      ],
    });
    await settled();
    const panel = screen.getByTestId("work-import-guidance-not_authenticated");
    expect(panel.textContent).toContain("Codex");
    expect(panel.textContent).toContain("codex login");
    expect(screen.queryByTestId("work-import-start")).toBeNull();
  });

  it("reports the concrete cause on call_failed and never suggests reinstalling", async () => {
    renderDialog({
      state: "call_failed",
      providers: [
        provider({
          key: "claude-code",
          label: "Claude Code",
          state: "call_failed",
          cause: "quota exceeded",
        }),
      ],
    });
    await settled();
    const panel = screen.getByTestId("work-import-guidance-call_failed");
    expect(panel.textContent).toContain("quota exceeded");
    // FR-034 — a correctly configured user must never be sent to reinstall
    // software they are already running. The branch avoids the word entirely.
    expect(panel.textContent).not.toMatch(/reinstall/i);
    expect(screen.queryByTestId("work-import-guidance-not_installed")).toBeNull();
  });

  it("does not tell a user whose call failed that their setup is fine", async () => {
    // The implementation's own measurement table records the observed
    // `kimi-code` failure as "No model configured" — a local problem the user
    // has to fix. Copy asserting the opposite would send that user away from
    // the only thing that would help. Not naming a fix is honest; asserting
    // there is nothing to fix is not, and FR-034 does not license it.
    renderDialog({
      state: "call_failed",
      providers: [
        provider({
          key: "kimi-code",
          label: "Kimi Code",
          state: "call_failed",
          cause: "No model configured.",
        }),
      ],
    });
    await settled();
    const panel = screen.getByTestId("work-import-guidance-call_failed");
    expect(panel.textContent).not.toMatch(/nothing on your computer/i);
    expect(panel.textContent).not.toMatch(/setup is fine/i);
    expect(panel.textContent).toContain("No model configured.");
  });

  it("offers a retry that re-probes with refresh=true", async () => {
    // The copy invites the user to check again, and the backend memoises the
    // report for 60 seconds; without `refresh` a user who has just fixed their
    // quota is re-served the same failure. Wiring the control is what makes
    // that invitation something the UI can carry out.
    const failing = {
      state: "call_failed" as const,
      providers: [
        provider({ key: "codex", label: "Codex", state: "call_failed", cause: "quota exceeded" }),
      ],
    };
    const fetchAvailability = vi
      .fn<(options?: { refresh?: boolean }) => Promise<AgentAvailabilityResponse>>()
      .mockResolvedValueOnce(failing)
      .mockResolvedValueOnce(ready(CODEX));

    render(
      <BringInMyWorkDialog
        onClose={vi.fn()}
        fetchAvailability={fetchAvailability}
        startSession={vi.fn<StartSession>(async () => sessionResponse())}
      />,
    );
    await settled();
    expect(fetchAvailability.mock.calls[0][0]).toBeUndefined();

    fireEvent.click(screen.getByTestId("work-import-availability-retry"));

    await waitFor(() => expect(screen.getByTestId("setup-provider-select")).toBeTruthy());
    expect(fetchAvailability).toHaveBeenCalledTimes(2);
    expect(fetchAvailability.mock.calls[1][0]).toEqual({ refresh: true });
    expect(screen.queryByTestId("work-import-guidance-call_failed")).toBeNull();
    // The user was held on the setup page while no agent could run; the fix
    // releases them, all the way through to a start action.
    walkToStart();
    expect(screen.getByTestId("work-import-start")).toBeTruthy();
  });

  it("each state gets its own guidance rather than one state's cause standing in for another", async () => {
    renderDialog({
      state: "call_failed",
      providers: [
        provider({
          key: "codex",
          label: "Codex",
          state: "call_failed",
          cause: "network unreachable",
        }),
        provider({ key: "kimi-code", label: "Kimi", state: "not_authenticated" }),
      ],
    });
    await settled();
    const failed = screen.getByTestId("work-import-guidance-list-call_failed");
    const unauthenticated = screen.getByTestId("work-import-guidance-list-not_authenticated");
    expect(failed.textContent).toContain("Codex");
    expect(failed.textContent).not.toContain("Kimi");
    expect(unauthenticated.textContent).toContain("Kimi");
    expect(unauthenticated.textContent).not.toContain("network unreachable");
  });

  it("lets the user proceed when some providers are usable and others are not", async () => {
    renderDialog({
      state: "ready",
      providers: [
        CLAUDE,
        provider({ key: "codex", label: "Codex", state: "call_failed", cause: "quota" }),
      ],
    });
    await settled();

    // The unusable one is IN THE DROPDOWN, greyed, with a short suffix — the AI
    // chat's pattern (owner, 2026-08-08). There is no longer a block of prose
    // beside the picker telling a user with a working agent how to repair one
    // they are not using.
    const codex = screen.getByTestId("setup-provider-option-codex") as HTMLOptionElement;
    expect(codex.disabled).toBe(true);
    expect(codex.textContent).toBe("Codex (call failed)");
    // FR-034 — never reported as an install problem.
    expect(codex.textContent).not.toMatch(/install/i);
    // The remedy and the cause are not here; they belong to the dead-end state.
    expect(screen.queryByTestId("work-import-guidance-call_failed")).toBeNull();
    expect(screen.getByTestId("work-import-dialog").textContent).not.toContain("quota");

    // Not blocked: a mixed result lets the user through to the start action.
    walkToStart();
    expect(screen.getByTestId("work-import-start")).toBeTruthy();
  });

  it("lists every provider in the one dropdown, selectable ones first", async () => {
    // The owner's own machine: two agents working, three not, and previously a
    // paragraph of install and login instructions under the picker for the
    // three he was not going to use.
    renderDialog({
      state: "ready",
      providers: [
        provider({
          key: "qoder",
          label: "Qoder CLI",
          state: "not_installed",
          next_step: "Install the Qoder CLI so that `qodercli` is on your PATH.",
        }),
        CLAUDE,
        provider({
          key: "qoder-cn",
          label: "Qoder CLI (China)",
          state: "not_authenticated",
          next_step: "Start `qoderclicn` in a terminal and complete its sign-in.",
        }),
        CODEX,
      ],
    });
    await settled();

    const select = screen.getByTestId("setup-provider-select") as HTMLSelectElement;
    const options = Array.from(select.querySelectorAll("option")).map((option) => ({
      value: option.value,
      text: option.textContent,
      disabled: option.disabled,
    }));
    expect(options).toEqual([
      { value: "", text: "Choose provider…", disabled: true },
      { value: "claude-code", text: "Claude Code", disabled: false },
      { value: "codex", text: "Codex", disabled: false },
      { value: "qoder", text: "Qoder CLI (not installed)", disabled: true },
      { value: "qoder-cn", text: "Qoder CLI (China) (not signed in)", disabled: true },
    ]);

    // None of the remedies reaches the user in this state.
    const dialog = screen.getByTestId("work-import-dialog").textContent ?? "";
    expect(dialog).not.toContain("qodercli");
    expect(dialog).not.toMatch(/complete its sign-in/i);
  });

  it("renders with a reported state rather than waiting when the probe fails", async () => {
    renderDialog(new Error("probe exploded"));
    await settled();
    expect(screen.getByTestId("work-import-dialog")).toBeTruthy();
    expect(screen.getByTestId("work-import-guidance-call_failed").textContent).toContain(
      "probe exploded",
    );
    expect(screen.queryByTestId("work-import-start")).toBeNull();
  });

  it("renders immediately while the probe is still in flight", () => {
    render(
      <BringInMyWorkDialog
        onClose={vi.fn()}
        fetchAvailability={() => new Promise<AgentAvailabilityResponse>(() => {})}
        startSession={vi.fn<StartSession>(async () => sessionResponse())}
      />,
    );
    // FR-035 — a hanging probe never produces a stuck surface. The dialog is on
    // screen, the setup page is usable, only the agent section reports waiting…
    expect(screen.getByTestId("work-import-dialog")).toBeTruthy();
    expect(currentPage()).toBe("setup");
    expect(screen.getByTestId("work-import-probing")).toBeTruthy();
    // …and an unresolved probe does not hold the user on page one either. Only
    // the start action waits on it.
    walkTo("q1");
    expect(screen.getByTestId("work-import-q1")).toBeTruthy();
  });

  it("explains itself when the report names no providers at all", async () => {
    // Contract C1 names this case — `aggregate_state([])` is `not_installed` —
    // and guidance derived from provider ROWS produced nothing for it: a dialog
    // full of questions, no start action, and no explanation of either.
    renderDialog({ state: "not_installed", providers: [] });
    await settled();
    const panel = screen.getByTestId("work-import-guidance-not_installed");
    expect(panel.textContent).toMatch(/no agent providers registered/i);
    expect(screen.queryByTestId("work-import-start")).toBeNull();
  });
});

describe("a provider that cannot run a session is never offered (FR-029, FR-043)", () => {
  const KIMI_REASON =
    "Kimi Code has no positional prompt argument: its only prompt flag, -p/--prompt, runs one " +
    "prompt non-interactively and exits.";
  const KIMI = provider({
    key: "kimi-code",
    label: "Kimi Code",
    state: "ready",
    session_unsupported_reason: KIMI_REASON,
  });

  it("is not auto-selected when it is the only ready provider", async () => {
    // The bug this pins: `ready` alone made a provider usable, FR-043 then
    // selected the only usable one, and pressing Start returned an opaque 500
    // with a stray brief left in the user's project. "Answers a live call" and
    // "can be handed a task on its command line" are different capabilities and
    // this feature needs both.
    renderDialog({ state: "ready", providers: [KIMI] });
    await settled();
    expect(screen.queryByTestId("work-import-start")).toBeNull();
    expect(screen.queryByTestId("setup-provider-select")).toBeNull();
  });

  it("is explained rather than silently dropped", async () => {
    renderDialog({ state: "ready", providers: [KIMI] });
    await settled();
    const panel = screen.getByTestId("work-import-guidance-session_unsupported");
    expect(panel.textContent).toContain("Kimi Code");
    expect(panel.textContent).toContain("no positional prompt argument");
    // Not reported as an install problem: installing it again would not help.
    expect(screen.queryByTestId("work-import-guidance-not_installed")).toBeNull();
  });

  it("does not block a user who also has a provider that works", async () => {
    renderDialog({ state: "ready", providers: [CLAUDE, KIMI] });
    await settled();
    expect(screen.getByTestId("setup-provider-select")).toHaveValue("claude-code");

    const kimi = screen.getByTestId("setup-provider-option-kimi-code") as HTMLOptionElement;
    expect(kimi.disabled).toBe(true);
    // Its own suffix, not its availability state — it IS ready, and an option
    // reading "Kimi Code" with nothing after it would look selectable-but-broken.
    expect(kimi.textContent).toBe("Kimi Code (not available)");
    // The registry's full explanation is guidance, and this user needs none.
    expect(screen.getByTestId("work-import-dialog").textContent).not.toContain(
      "no positional prompt argument",
    );

    walkToStart();
    expect(screen.getByTestId("work-import-start")).toBeTruthy();
  });

  it("is reported under its own reason even when it is also not installed", async () => {
    // Installing it would not make it usable here, so "install this" would be
    // an action that does not work — which is the thing SC-002 rules out.
    renderDialog({
      state: "not_installed",
      providers: [
        provider({
          key: "kimi-code",
          label: "Kimi Code",
          state: "not_installed",
          next_step: "Install the Kimi Code CLI so that `kimi` is on your PATH.",
          session_unsupported_reason: KIMI_REASON,
        }),
      ],
    });
    await settled();
    expect(screen.getByTestId("work-import-guidance-session_unsupported")).toBeTruthy();
    expect(screen.queryByTestId("work-import-guidance-not_installed")).toBeNull();
  });
});

describe("FR-040 – FR-044 — provider and permission mode", () => {
  it("preselects the single usable provider and keeps the control visible", async () => {
    renderDialog(ready(CLAUDE));
    await settled();
    const select = screen.getByTestId("setup-provider-select");
    expect(select).toBeVisible();
    expect(select).toHaveValue("claude-code");
  });

  it("lets the user choose between two usable providers", async () => {
    renderDialog(ready(CLAUDE, CODEX));
    await settled();
    const select = screen.getByTestId("setup-provider-select");
    // Neither is preselected — the choice is the user's (ADR-034 FR-021i).
    expect(select).toHaveValue("");
    expect(screen.getByTestId("setup-provider-option-claude-code")).toBeTruthy();
    expect(screen.getByTestId("setup-provider-option-codex")).toBeTruthy();
    fireEvent.change(select, { target: { value: "codex" } });
    expect(select).toHaveValue("codex");
  });

  it("defaults to the safe permission mode and offers the bypass one", async () => {
    renderDialog();
    await settled();
    expect(screen.getByTestId("setup-permission-safe")).toBeChecked();
    expect(screen.getByTestId("setup-permission-dangerous")).not.toBeChecked();
  });

  it("the chosen provider and permission mode reach the request", async () => {
    const startSession = vi.fn<StartSession>(async () =>
      sessionResponse({ provider: "codex", permission_mode: "bypass" }),
    );
    renderDialog(ready(CLAUDE, CODEX), { startSession });
    await settled();

    walkToStart({
      setup: () => {
        fireEvent.change(screen.getByTestId("work-import-source-input"), {
          target: { value: SOURCE },
        });
        fireEvent.change(screen.getByTestId("setup-provider-select"), {
          target: { value: "codex" },
        });
        fireEvent.click(screen.getByTestId("setup-permission-dangerous"));
      },
    });
    fireEvent.click(screen.getByTestId("work-import-start"));

    await waitFor(() => expect(startSession).toHaveBeenCalledTimes(1));
    expect(startSession.mock.calls[0][0]).toMatchObject({
      provider: "codex",
      // Checklist §7.4 — the backend spelling, mapped at the request boundary.
      permission_mode: "bypass",
    });
  });
});

describe("starting the session (FR-021 – FR-025)", () => {
  it("sends every answer, marks the skipped ones, and attaches the returned tab", async () => {
    const startSession = vi.fn<StartSession>(async () => sessionResponse());
    const { onClose } = renderDialog(ready(CLAUDE), { startSession });
    await settled();

    walkToStart({
      q2: () =>
        fireEvent.change(screen.getByTestId("work-import-q2-input"), {
          target: { value: "Load the export, drop blanks, normalise to the control." },
        }),
      // Question 3 is skipped by the control that says so; question 4 is simply
      // paged past. FR-021 makes those the same claim, and the payload agrees.
      q3: () => fireEvent.click(screen.getByTestId("work-import-q3-skip")),
    });
    fireEvent.click(screen.getByTestId("work-import-start"));

    await waitFor(() => expect(startSession).toHaveBeenCalledTimes(1));
    expect(startSession.mock.calls[0][0]).toEqual({
      project_dir: "/projects/demo",
      source_location: SOURCE,
      has_no_codebase: false,
      destination_tier: "project",
      data_kinds: ["Table / dataframe"],
      data_kinds_other: null,
      workflow_description: "Load the export, drop blanks, normalise to the control.",
      interaction_wishes: null,
      other_software: null,
      skipped: ["interaction_wishes", "other_software"],
      provider: "claude-code",
      permission_mode: "safe",
    });

    await waitFor(() => expect(useAppStore.getState().terminalTabs).toHaveLength(1));
    const tab = useAppStore.getState().terminalTabs[0];
    expect(tab.id).toBe("a1b2c3d4e5f6");
    expect(tab.state).toBe("running");
    expect(tab.provider).toBe("claude-code");
    // FR-025 — an ordinary chat session, so it lands in the chat surface.
    expect(tab.source).toBe("user");
    expect(useAppStore.getState().activeBottomTab).toBe("ai");
    expect(useAppStore.getState().bottomPanelCollapsed).toBe(false);
    expect(onClose).toHaveBeenCalled();
  });

  it("a no-codebase session cannot get past question 2 without it, and can with it", async () => {
    const startSession = vi.fn<StartSession>(async () => sessionResponse());
    renderDialog(ready(CLAUDE), { startSession });
    await settled();

    // FR-020 under paging: the block is on the page that asks, not on a start
    // action five pages away that the user would otherwise never have reached.
    walkTo("q2", { setup: () => fireEvent.click(screen.getByTestId("work-import-no-codebase")) });
    fireEvent.click(screen.getByTestId("work-import-next"));
    expect(currentPage()).toBe("q2");
    expect(screen.getByTestId("work-import-blocking-reasons").textContent).toMatch(
      /Required: a description of your workflow/i,
    );

    NO_CODEBASE.q2?.();
    walkToStart({ setup: () => {} });
    fireEvent.click(screen.getByTestId("work-import-start"));
    await waitFor(() => expect(startSession).toHaveBeenCalledTimes(1));
    expect(startSession.mock.calls[0][0]).toMatchObject({
      source_location: null,
      has_no_codebase: true,
    });
  });

  it("the submitted body satisfies A2's ImportSessionContext rules in every mode", async () => {
    // Codebase mode, everything answered.
    const withSource = vi.fn<StartSession>(async () => sessionResponse());
    renderDialog(ready(CLAUDE), { startSession: withSource });
    await settled();
    walkToStart({
      q2: () =>
        fireEvent.change(screen.getByTestId("work-import-q2-input"), {
          target: { value: "In: the plate export. Out: one number per condition." },
        }),
      q3: () =>
        fireEvent.change(screen.getByTestId("work-import-q3-input"), {
          target: { value: "Let me pick the background patch." },
        }),
    });
    // The last page is where the walk stops, so its answer is typed in place.
    fireEvent.change(screen.getByTestId("work-import-q4-input"), { target: { value: "Fiji" } });
    fireEvent.click(screen.getByTestId("work-import-start"));
    await waitFor(() => expect(withSource).toHaveBeenCalledTimes(1));
    expect(validateWorkImportRequest(withSource.mock.calls[0][0])).toEqual([]);
    cleanup();

    // No-codebase mode, reached by typing a source and then ticking the box —
    // the state most likely to send both fields at once.
    const noCodebase = vi.fn<StartSession>(async () => sessionResponse());
    renderDialog(ready(CLAUDE), { startSession: noCodebase });
    await settled();
    walkToStart({
      setup: () => {
        fireEvent.change(screen.getByTestId("work-import-source-input"), {
          target: { value: "/typed/before/ticking" },
        });
        fireEvent.click(screen.getByTestId("work-import-no-codebase"));
      },
      q1: () => fireEvent.click(screen.getByTestId("work-import-data-kind-Image")),
      q2: () =>
        fireEvent.change(screen.getByTestId("work-import-q2-input"), {
          target: { value: "Every Monday I open the export in Excel." },
        }),
    });
    fireEvent.click(screen.getByTestId("work-import-start"));
    await waitFor(() => expect(noCodebase).toHaveBeenCalledTimes(1));
    const body = noCodebase.mock.calls[0][0];
    expect(validateWorkImportRequest(body)).toEqual([]);
    // Exactly one of the two, never both.
    expect(body.source_location).toBeNull();
    expect(body.has_no_codebase).toBe(true);
  });

  it("a question the user typed into and then skipped is sent as skipped, with no answer", async () => {
    const startSession = vi.fn<StartSession>(async () => sessionResponse());
    renderDialog(ready(CLAUDE), { startSession });
    await settled();

    walkToStart({
      q3: () => {
        fireEvent.change(screen.getByTestId("work-import-q3-input"), {
          target: { value: "typed, then thought better of it" },
        });
        fireEvent.click(screen.getByTestId("work-import-q3-skip"));
      },
    });
    fireEvent.click(screen.getByTestId("work-import-start"));

    await waitFor(() => expect(startSession).toHaveBeenCalledTimes(1));
    const body = startSession.mock.calls[0][0];
    expect(body.interaction_wishes).toBeNull();
    expect(body.skipped).toContain("interaction_wishes");
    expect(validateWorkImportRequest(body)).toEqual([]);
  });

  it("cannot leave the setup page without a provider when two are usable", async () => {
    renderDialog(ready(CLAUDE, CODEX));
    await settled();
    fireEvent.change(screen.getByTestId("work-import-source-input"), {
      target: { value: SOURCE },
    });
    // Neither provider is preselected, so the request would carry a blank
    // `provider` — which the backend rejects. FR-040's choice is made on this
    // page, so this page is where the dialog blocks: the user is told now, not
    // after four more pages of answers.
    fireEvent.click(screen.getByTestId("work-import-next"));
    expect(currentPage()).toBe("setup");
    expect(screen.getByTestId("work-import-blocking-reasons").textContent).toMatch(
      /Required: which agent runs the session/i,
    );

    fireEvent.change(screen.getByTestId("setup-provider-select"), { target: { value: "codex" } });
    fireEvent.click(screen.getByTestId("work-import-next"));
    expect(currentPage()).toBe("q1");
  });

  it("surfaces a failed start and leaves the dialog open", async () => {
    const startSession = vi.fn<StartSession>(async () => {
      throw new Error("brief could not be written");
    });
    const { onClose } = renderDialog(ready(CLAUDE), { startSession });
    await settled();

    walkToStart();
    fireEvent.click(screen.getByTestId("work-import-start"));
    await waitFor(() =>
      expect(screen.getByTestId("work-import-error").textContent).toContain(
        "brief could not be written",
      ),
    );
    expect(onClose).not.toHaveBeenCalled();
    // Still on the page it failed on, with everything the user answered intact.
    expect(currentPage()).toBe(LAST_PAGE);
    expect(useAppStore.getState().terminalTabs).toHaveLength(0);
  });
});
