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
 */
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { Mock } from "vitest";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type * as ApiModule from "../../lib/api";

vi.mock("../../lib/api", async () => {
  const actual = await vi.importActual<typeof ApiModule>("../../lib/api");
  return { ...actual, api: { ...actual.api, openNativeDialog: vi.fn() } };
});

import { BringInMyWorkDialog } from "../BringInMyWorkDialog";
import { CAVEAT_BODY } from "../BringInMyWorkDialog.parts/copy";
import { validateWorkImportRequest } from "../../lib/api/workImport";
import { api } from "../../lib/api";
import { useAppStore } from "../../store";
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
function provider(
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

const CLAUDE = provider({ key: "claude-code", label: "Claude Code" });
const CODEX = provider({ key: "codex", label: "Codex" });

function ready(...providers: AgentAvailabilityResponse["providers"]): AgentAvailabilityResponse {
  return { state: "ready", providers };
}

type StartSession = NonNullable<React.ComponentProps<typeof BringInMyWorkDialog>["startSession"]>;
type SessionResponse = Awaited<ReturnType<StartSession>>;

function sessionResponse(overrides: Partial<SessionResponse> = {}): SessionResponse {
  return {
    tab_id: "a1b2c3d4e5f6",
    title: "Bring in my work",
    brief_path: ".scistudio/work-import/s1.md",
    provider: "claude-code",
    permission_mode: "safe",
    ...overrides,
  };
}

interface Harness {
  startSession: Mock<StartSession>;
  onClose: Mock<() => void>;
}

function renderDialog(
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
async function settled(): Promise<void> {
  await waitFor(() => expect(screen.queryByTestId("work-import-probing")).toBeNull());
}

function fillMinimum(): void {
  fireEvent.change(screen.getByTestId("work-import-source-input"), {
    target: { value: "/home/ana/plate-reader" },
  });
  fireEvent.click(screen.getByTestId("work-import-data-kind-Table / dataframe"));
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
  vi.mocked(api.openNativeDialog).mockReset();
});

afterEach(cleanup);

describe("FR-037 / FR-038 — the correctness caveat", () => {
  it("is present, in full, with the session start action", async () => {
    renderDialog();
    await settled();
    const caveat = screen.getByTestId("work-import-caveat");
    expect(caveat.textContent).toContain(CAVEAT_BODY);
    // All four claims FR-037 requires.
    expect(caveat.textContent).toMatch(/can make mistakes/i);
    expect(caveat.textContent).toMatch(/instructed to check/i);
    expect(caveat.textContent).toMatch(/does not guarantee/i);
    expect(caveat.textContent).toMatch(/review the result yourself/i);
  });

  it("is not weakened or omitted in no-codebase mode", async () => {
    renderDialog();
    await settled();
    fireEvent.click(screen.getByTestId("work-import-no-codebase"));
    expect(screen.getByTestId("work-import-caveat").textContent).toContain(CAVEAT_BODY);
  });

  it("is not dismissible and cannot be bypassed before the start action", async () => {
    renderDialog();
    await settled();
    const caveat = screen.getByTestId("work-import-caveat");
    // No dismiss/close/hide affordance inside it, in either mode (FR-038).
    expect(within(caveat).queryAllByRole("button")).toHaveLength(0);
    expect(caveat.getAttribute("hidden")).toBeNull();
    fireEvent.click(screen.getByTestId("work-import-no-codebase"));
    expect(within(screen.getByTestId("work-import-caveat")).queryAllByRole("button")).toHaveLength(
      0,
    );
  });
});

describe("FR-008 – FR-010 — source, browse, and the no-codebase path", () => {
  it("the browse control asks for a directory, not a file", async () => {
    vi.mocked(api.openNativeDialog).mockResolvedValue({ paths: ["/home/ana/plate-reader"] });
    renderDialog();
    await settled();

    fireEvent.click(screen.getByTestId("work-import-source-browse"));
    await waitFor(() => expect(api.openNativeDialog).toHaveBeenCalled());
    expect(vi.mocked(api.openNativeDialog).mock.calls[0][0]).toBe("directory");
    await waitFor(() =>
      expect(screen.getByTestId("work-import-source-input")).toHaveValue("/home/ana/plate-reader"),
    );
  });

  it("selecting 'I don't have a codebase' disables the source field and leaves the rest in effect", async () => {
    renderDialog();
    await settled();
    fireEvent.click(screen.getByTestId("work-import-no-codebase"));

    expect(screen.getByTestId("work-import-source-input")).toBeDisabled();
    expect(screen.getByTestId("work-import-source-browse")).toBeDisabled();
    // FR-010 — every other field remains in effect, including the destination.
    expect(screen.getByTestId("work-import-destination-user_library")).toBeEnabled();
    expect(screen.getByTestId("work-import-data-kind-Image")).toBeEnabled();
    expect(screen.getByTestId("setup-permission-safe")).toBeEnabled();
  });
});

describe("FR-013 – FR-015 — question 1", () => {
  it("groups the presets so both readings of the same data can be selected", async () => {
    renderDialog();
    await settled();

    const arrangement = screen.getByTestId("work-import-data-kind-group-arrangement");
    const domain = screen.getByTestId("work-import-data-kind-group-domain");
    expect(within(arrangement).getByTestId("work-import-data-kind-Series")).toBeTruthy();
    expect(within(domain).getByTestId("work-import-data-kind-Time series")).toBeTruthy();

    fireEvent.click(screen.getByTestId("work-import-data-kind-Series"));
    fireEvent.click(screen.getByTestId("work-import-data-kind-Time series"));
    expect(screen.getByTestId("work-import-data-kind-Series")).toBeChecked();
    expect(screen.getByTestId("work-import-data-kind-Time series")).toBeChecked();
  });

  it("offers a free-text field for anything not listed", async () => {
    renderDialog();
    await settled();
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

    expect(screen.getByTestId("work-import-q2-skip")).toBeTruthy();
    expect(screen.queryByTestId("work-import-q2-required")).toBeNull();
    const withSourceHelp = screen.getByTestId("work-import-q2-help").textContent ?? "";

    fireEvent.click(screen.getByTestId("work-import-no-codebase"));
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
    expect(screen.getByTestId("work-import-q3-skip")).toBeTruthy();
    expect(screen.getByTestId("work-import-q4-skip")).toBeTruthy();
    // FR-018 — without examples the question is too abstract to answer.
    const q3Help = screen.getByTestId("work-import-q3-help").textContent ?? "";
    expect(q3Help).toMatch(/background/i);
    expect(q3Help).toMatch(/segmentation mask/i);
  });

  it("a skip reads as a choice rather than an abandoned field", async () => {
    renderDialog();
    await settled();
    const skipLabel = screen.getByTestId("work-import-q3-skip").closest("label");
    expect(skipLabel?.textContent).toMatch(/let the agent work this out/i);
    expect(skipLabel?.textContent).toMatch(/knows to ask rather than assume/i);
  });
});

describe("FR-006 / FR-007 — who the questions are written for", () => {
  it("asks nothing that needs SciStudio or software-development knowledge", async () => {
    renderDialog();
    await settled();
    const text = screen.getByTestId("work-import-dialog").textContent ?? "";
    for (const forbidden of [
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
    ]) {
      expect(text).not.toMatch(forbidden);
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

    await waitFor(() => expect(screen.getByTestId("work-import-start")).toBeTruthy());
    expect(fetchAvailability).toHaveBeenCalledTimes(2);
    expect(fetchAvailability.mock.calls[1][0]).toEqual({ refresh: true });
    expect(screen.queryByTestId("work-import-guidance-call_failed")).toBeNull();
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
    expect(screen.getByTestId("work-import-start")).toBeTruthy();
    const note = screen.getByTestId("work-import-unusable-providers");
    expect(note.textContent).toContain("Codex");
    expect(note.textContent).toContain("quota");
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
    // FR-035 — a hanging probe never produces a stuck surface. The dialog and
    // every question are on screen; only the agent section reports waiting.
    expect(screen.getByTestId("work-import-dialog")).toBeTruthy();
    expect(screen.getByTestId("work-import-q1")).toBeTruthy();
    expect(screen.getByTestId("work-import-probing")).toBeTruthy();
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
    expect(screen.getByTestId("work-import-start")).toBeTruthy();
    expect(screen.getByTestId("setup-provider-select")).toHaveValue("claude-code");
    const note = screen.getByTestId("work-import-unusable-providers");
    expect(note.textContent).toContain("Kimi Code");
    // Its own reason, not its availability state — it IS ready, and saying so
    // in a list headed "not usable right now" would read as a bug.
    expect(note.textContent).toContain("no positional prompt argument");
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

    fillMinimum();
    fireEvent.change(screen.getByTestId("setup-provider-select"), { target: { value: "codex" } });
    fireEvent.click(screen.getByTestId("setup-permission-dangerous"));
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

    fillMinimum();
    fireEvent.change(screen.getByTestId("work-import-q2-input"), {
      target: { value: "Load the export, drop blanks, normalise to the control." },
    });
    fireEvent.click(screen.getByTestId("work-import-q3-skip"));
    fireEvent.click(screen.getByTestId("work-import-start"));

    await waitFor(() => expect(startSession).toHaveBeenCalledTimes(1));
    expect(startSession.mock.calls[0][0]).toEqual({
      project_dir: "/projects/demo",
      source_location: "/home/ana/plate-reader",
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

  it("a no-codebase session cannot start without question 2, and can with it", async () => {
    const startSession = vi.fn<StartSession>(async () => sessionResponse());
    renderDialog(ready(CLAUDE), { startSession });
    await settled();

    fireEvent.click(screen.getByTestId("work-import-no-codebase"));
    fireEvent.click(screen.getByTestId("work-import-data-kind-Table / dataframe"));
    expect(screen.getByTestId("work-import-start")).toBeDisabled();
    expect(screen.getByTestId("work-import-blocking-reasons").textContent).toMatch(
      /only description of your work/i,
    );

    fireEvent.change(screen.getByTestId("work-import-q2-input"), {
      target: { value: "Every Monday I open the export in Excel and average the replicates." },
    });
    expect(screen.getByTestId("work-import-start")).toBeEnabled();
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
    fillMinimum();
    fireEvent.change(screen.getByTestId("work-import-q2-input"), {
      target: { value: "In: the plate export. Out: one number per condition." },
    });
    fireEvent.change(screen.getByTestId("work-import-q3-input"), {
      target: { value: "Let me pick the background patch." },
    });
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
    fireEvent.change(screen.getByTestId("work-import-source-input"), {
      target: { value: "/typed/before/ticking" },
    });
    fireEvent.click(screen.getByTestId("work-import-no-codebase"));
    fireEvent.click(screen.getByTestId("work-import-data-kind-Image"));
    fireEvent.change(screen.getByTestId("work-import-q2-input"), {
      target: { value: "Every Monday I open the export in Excel." },
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

    fillMinimum();
    fireEvent.change(screen.getByTestId("work-import-q3-input"), {
      target: { value: "typed, then thought better of it" },
    });
    fireEvent.click(screen.getByTestId("work-import-q3-skip"));
    fireEvent.click(screen.getByTestId("work-import-start"));

    await waitFor(() => expect(startSession).toHaveBeenCalledTimes(1));
    const body = startSession.mock.calls[0][0];
    expect(body.interaction_wishes).toBeNull();
    expect(body.skipped).toContain("interaction_wishes");
    expect(validateWorkImportRequest(body)).toEqual([]);
  });

  it("cannot start without a provider when two are usable", async () => {
    renderDialog(ready(CLAUDE, CODEX));
    await settled();
    fillMinimum();
    // Neither provider is preselected, so the request would carry a blank
    // `provider` — which the backend rejects. The dialog blocks first.
    expect(screen.getByTestId("work-import-start")).toBeDisabled();
    expect(screen.getByTestId("work-import-blocking-reasons").textContent).toMatch(
      /Choose which agent runs the session/i,
    );
    fireEvent.change(screen.getByTestId("setup-provider-select"), { target: { value: "codex" } });
    expect(screen.getByTestId("work-import-start")).toBeEnabled();
  });

  it("surfaces a failed start and leaves the dialog open", async () => {
    const startSession = vi.fn<StartSession>(async () => {
      throw new Error("brief could not be written");
    });
    const { onClose } = renderDialog(ready(CLAUDE), { startSession });
    await settled();

    fillMinimum();
    fireEvent.click(screen.getByTestId("work-import-start"));
    await waitFor(() =>
      expect(screen.getByTestId("work-import-error").textContent).toContain(
        "brief could not be written",
      ),
    );
    expect(onClose).not.toHaveBeenCalled();
    expect(useAppStore.getState().terminalTabs).toHaveLength(0);
  });
});
