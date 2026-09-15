/**
 * ADR-053 spec 2 (#2001) — Bring In My Work dialog.
 *
 * Covers the acceptance scenarios of User Stories 1–4 that live on this side of
 * the boundary: the framing questions, the no-codebase path, the agent setup,
 * and the correctness caveat.
 *
 * #2454 — the agent setup is AI Chat's own (`AgentLaunchSetup` over
 * `GET /api/ai/status`), so provider status is faked with AI Chat's fixture
 * rather than a dialog-specific seam.
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
import { mockAgentStatus } from "../AIChat/__tests__/agentStatusFixture";
import {
  CAVEAT_BODY,
  DATA_KIND_GROUPS,
  Q1_LABEL,
  Q2_LABEL,
  Q3_LABEL,
  Q4_LABEL,
  Q5_LABEL,
  SOURCE_LABEL,
} from "../BringInMyWorkDialog.parts/copy";
import {
  REASON_NO_PERMISSION_MODE,
  REASON_NO_PROVIDER,
} from "../BringInMyWorkDialog.parts/formState";
import { validateWorkImportRequest } from "../../lib/api/workImport";
import { api } from "../../lib/api";
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
  type PageAnswers,
  type PageId,
  type StartSession,
} from "./BringInMyWorkDialog.harness";

/** Answer only what FR-020 requires, then stop on the last page. */
function walkToStart(answers: PageAnswers = {}): void {
  walkTo(LAST_PAGE, answers);
}

/**
 * Choose the agent on the setup page. Provider and permission mode both start
 * unchosen, exactly as in AI Chat (#2454), so a test that replaces the harness's
 * setup answer has to make this choice itself.
 */
function chooseAgent(name = "claude-code", mode: "safe" | "auto" | "dangerous" = "safe"): void {
  fireEvent.change(screen.getByTestId("setup-provider-select"), { target: { value: name } });
  fireEvent.click(screen.getByTestId(`setup-permission-${mode}`));
}

const NO_CODEBASE: PageAnswers = {
  setup: () => {
    fireEvent.click(screen.getByTestId("work-import-no-codebase"));
    chooseAgent();
  },
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
    expect(screen.getByTestId("setup-provider-select")).toBeEnabled();
    expect(screen.getByTestId("setup-permission-safe")).toBeEnabled();
    // And the questions, which are now pages of their own rather than fields
    // below it — reachable with no source location given.
    walkTo("q1", { setup: () => chooseAgent() });
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

  /** What the walk below must have actually read, or it read nothing. */
  const MUST_READ = [SOURCE_LABEL, Q1_LABEL, Q2_LABEL, Q3_LABEL, Q4_LABEL, Q5_LABEL, CAVEAT_BODY];

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
   * search after a single render reads page one and reports on all of them — the
   * guard would keep passing while guarding almost nothing. So the walk visits
   * each page in turn, and then asserts BOTH that it reached every page and that
   * what it read contains the actual questions: an empty page, or a page that
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
    // The walk read real content, not a run of blanks.
    for (const label of MUST_READ) expect(everything).toContain(label);
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

    renderDialog([CLAUDE, CODEX]);
    await settled();
    for (const page of PAGE_IDS) {
      walkTo(page, {
        setup: () => {
          fireEvent.change(screen.getByTestId("work-import-source-input"), {
            target: { value: SOURCE },
          });
          chooseAgent("codex");
        },
      });
      const text = screen.getByTestId("work-import-dialog").textContent ?? "";
      for (const gone of CUT) expect(text).not.toMatch(gone);
    }
  });
});

describe("#2454 — the agent setup is AI Chat's", () => {
  it("lists every provider in the one dropdown, installed ones first", async () => {
    renderDialog([
      provider({ name: "qoder", label: "Qoder CLI", available: false, version: null }),
      CLAUDE,
      provider({ name: "qoder-cn", label: "Qoder CLI (China)", logged_in: false, version: null }),
      CODEX,
    ]);
    await settled();

    const select = screen.getByTestId("setup-provider-select") as HTMLSelectElement;
    const options = Array.from(select.querySelectorAll("option")).map((option) => ({
      value: option.value,
      text: option.textContent,
      disabled: option.disabled,
    }));
    expect(options).toEqual([
      { value: "", text: "Choose provider…", disabled: true },
      { value: "claude-code", text: "Claude Code v9.9.9", disabled: false },
      // Not logged in is selectable: the CLI runs its own sign-in in the session.
      { value: "qoder-cn", text: "Qoder CLI (China) (not logged in)", disabled: false },
      { value: "codex", text: "Codex v9.9.9", disabled: false },
      { value: "qoder", text: "Qoder CLI (not installed)", disabled: true },
    ]);
  });

  it("shows AI Chat's no-providers notice when no agent is installed, and holds the user there", async () => {
    renderDialog([
      provider({ name: "claude-code", label: "Claude Code", available: false, version: null }),
      provider({ name: "codex", label: "Codex", available: false, version: null }),
    ]);
    await settled();

    const notice = screen.getByTestId("setup-no-providers-notice");
    expect(notice.textContent).toContain("Claude Code");
    expect(notice.textContent).toContain("Codex");
    expect(screen.queryByTestId("setup-provider-select")).toBeNull();

    fireEvent.change(screen.getByTestId("work-import-source-input"), {
      target: { value: SOURCE },
    });
    fireEvent.click(screen.getByTestId("setup-permission-safe"));
    expect(blockedGoingOn()).toContain(REASON_NO_PROVIDER);
  });

  it("reports a failed status check and holds the user on the setup page", async () => {
    renderDialog(new Error("status exploded"));
    await settled();
    expect(screen.getByTestId("setup-status-error")).toBeTruthy();
    expect(screen.getByTestId("work-import-dialog")).toBeTruthy();

    fireEvent.change(screen.getByTestId("work-import-source-input"), {
      target: { value: SOURCE },
    });
    expect(blockedGoingOn()).toContain(REASON_NO_PROVIDER);
  });

  it("reads provider status from /api/ai/status and never from the removed availability probe", async () => {
    const record = mockAgentStatus([CLAUDE]);
    render(
      <BringInMyWorkDialog
        onClose={vi.fn()}
        startSession={vi.fn<StartSession>(async () => sessionResponse())}
      />,
    );
    await settled();
    walkToStart();
    expect(screen.getByTestId("work-import-start")).toBeEnabled();

    expect(record.statusCalls.length).toBeGreaterThan(0);
    expect(record.availabilityCalls).toEqual([]);
  });
});

describe("FR-040 – FR-044 — provider and permission mode", () => {
  it("starts with neither a provider nor a permission mode chosen, even with one installed agent", async () => {
    renderDialog([CLAUDE]);
    await settled();
    const select = screen.getByTestId("setup-provider-select");
    expect(select).toBeVisible();
    expect(select).toHaveValue("");
    for (const mode of ["safe", "auto", "dangerous"]) {
      expect(screen.getByTestId(`setup-permission-${mode}`)).toHaveAttribute(
        "aria-checked",
        "false",
      );
    }
  });

  it("lets the user choose between two installed providers", async () => {
    renderDialog([CLAUDE, CODEX]);
    await settled();
    const select = screen.getByTestId("setup-provider-select");
    expect(select).toHaveValue("");
    expect(screen.getByTestId("setup-provider-option-claude-code")).toBeTruthy();
    expect(screen.getByTestId("setup-provider-option-codex")).toBeTruthy();
    fireEvent.change(select, { target: { value: "codex" } });
    expect(select).toHaveValue("codex");
  });

  it("the chosen provider and permission mode reach the request", async () => {
    const startSession = vi.fn<StartSession>(async () =>
      sessionResponse({ provider: "codex", permission_mode: "bypass" }),
    );
    renderDialog([CLAUDE, CODEX], { startSession });
    await settled();

    walkToStart({
      setup: () => {
        fireEvent.change(screen.getByTestId("work-import-source-input"), {
          target: { value: SOURCE },
        });
        chooseAgent("codex", "dangerous");
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
    const { onClose } = renderDialog([CLAUDE], { startSession });
    await settled();

    walkToStart({
      q2: () =>
        fireEvent.change(screen.getByTestId("work-import-q2-input"), {
          target: { value: "Load the export, drop blanks, normalise to the control." },
        }),
      // Question 3 is skipped by the control that says so; questions 4 and 5
      // are simply paged past. FR-021 makes those the same claim, and the
      // payload agrees.
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
      anything_else: null,
      skipped: ["interaction_wishes", "other_software", "anything_else"],
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
    renderDialog([CLAUDE], { startSession });
    await settled();

    // FR-020 under paging: the block is on the page that asks, not on a start
    // action several pages away that the user would otherwise never have
    // reached.
    walkTo("q2", { setup: NO_CODEBASE.setup });
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
    renderDialog([CLAUDE], { startSession: withSource });
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
      q4: () =>
        fireEvent.change(screen.getByTestId("work-import-q4-input"), { target: { value: "Fiji" } }),
    });
    // The last page is where the walk stops, so its answer is typed in place.
    fireEvent.change(screen.getByTestId("work-import-q5-input"), { target: { value: "Nothing." } });
    fireEvent.click(screen.getByTestId("work-import-start"));
    await waitFor(() => expect(withSource).toHaveBeenCalledTimes(1));
    expect(validateWorkImportRequest(withSource.mock.calls[0][0])).toEqual([]);
    cleanup();

    // No-codebase mode, reached by typing a source and then ticking the box —
    // the state most likely to send both fields at once.
    const noCodebase = vi.fn<StartSession>(async () => sessionResponse());
    renderDialog([CLAUDE], { startSession: noCodebase });
    await settled();
    walkToStart({
      setup: () => {
        fireEvent.change(screen.getByTestId("work-import-source-input"), {
          target: { value: "/typed/before/ticking" },
        });
        fireEvent.click(screen.getByTestId("work-import-no-codebase"));
        chooseAgent();
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
    renderDialog([CLAUDE], { startSession });
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

  it("cannot leave the setup page without a provider and a permission mode", async () => {
    renderDialog([CLAUDE, CODEX]);
    await settled();
    fireEvent.change(screen.getByTestId("work-import-source-input"), {
      target: { value: SOURCE },
    });
    // Nothing is preselected, so the request would carry a blank `provider` —
    // which the backend rejects. FR-040's choice is made on this page, so this
    // page is where the dialog blocks: the user is told now, not after four
    // more pages of answers.
    expect(blockedGoingOn()).toContain(REASON_NO_PROVIDER);

    fireEvent.change(screen.getByTestId("setup-provider-select"), { target: { value: "codex" } });
    expect(blockedGoingOn()).toContain(REASON_NO_PERMISSION_MODE);

    fireEvent.click(screen.getByTestId("setup-permission-safe"));
    fireEvent.click(screen.getByTestId("work-import-next"));
    expect(currentPage()).toBe("q1");
  });

  it("surfaces a failed start and leaves the dialog open", async () => {
    const startSession = vi.fn<StartSession>(async () => {
      throw new Error("brief could not be written");
    });
    const { onClose } = renderDialog([CLAUDE], { startSession });
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
