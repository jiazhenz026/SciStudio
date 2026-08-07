/**
 * ADR-053 spec 2 (#2001) — the work-import session client and the request it
 * composes.
 *
 * Checklist §7.4 requires BOTH sides of the permission-mode boundary to pin the
 * mapping in a test. This is the frontend half: the dialog collects
 * `"safe" | "dangerous"` (ADR-034's spelling) and the backend PTY spawn takes
 * `"safe" | "bypass"`. A silent mismatch launches a long autonomous session in
 * the wrong mode, which is either a wall of prompts the user did not ask for or
 * an agent running unattended when they wanted to approve each step.
 */
import { describe, expect, it, vi } from "vitest";

import {
  buildRequest,
  INITIAL_FORM_STATE,
  blockingReasons,
  type WorkImportFormState,
} from "../BringInMyWorkDialog.parts/formState";
import {
  fromBackendPermissionMode,
  startWorkImportSession,
  toBackendPermissionMode,
  validateWorkImportRequest,
  type WorkImportSessionRequest,
} from "../../lib/api/workImport";

function form(overrides: Partial<WorkImportFormState> = {}): WorkImportFormState {
  return { ...INITIAL_FORM_STATE, provider: "claude-code", ...overrides };
}

/** A body the backend accepts, as a base for the one-rule-at-a-time cases. */
function validRequest(overrides: Partial<WorkImportSessionRequest> = {}): WorkImportSessionRequest {
  return {
    project_dir: "/projects/demo",
    source_location: "/home/ana/plate-reader",
    has_no_codebase: false,
    destination_tier: "project",
    data_kinds: ["Array"],
    data_kinds_other: null,
    workflow_description: null,
    interaction_wishes: null,
    other_software: null,
    skipped: ["workflow_description", "interaction_wishes", "other_software"],
    provider: "claude-code",
    permission_mode: "safe",
    ...overrides,
  };
}

describe("permission-mode boundary (checklist §7.4)", () => {
  it("maps the frontend spelling to the backend spelling", () => {
    expect(toBackendPermissionMode("safe")).toBe("safe");
    expect(toBackendPermissionMode("dangerous")).toBe("bypass");
  });

  it("maps the backend spelling back for the terminal tab", () => {
    expect(fromBackendPermissionMode("safe")).toBe("safe");
    expect(fromBackendPermissionMode("bypass")).toBe("dangerous");
  });

  it("FR-044: the chosen mode reaches the request in backend spelling", () => {
    expect(buildRequest(form({ permissionMode: "dangerous" }), "/p").permission_mode).toBe(
      "bypass",
    );
    expect(buildRequest(form({ permissionMode: "safe" }), "/p").permission_mode).toBe("safe");
  });
});

describe("buildRequest (FR-021, FR-023)", () => {
  it("carries every answer, and marks unanswered questions as skipped rather than dropping them", () => {
    const request = buildRequest(
      form({
        sourceLocation: "  /home/ana/plate-reader  ",
        dataKinds: ["Table / dataframe", "Time series"],
        dataKindsOther: " chromatograms ",
        workflowDescription: { text: "Load the export, drop blanks, normalise.", skipped: false },
        interactionWishes: { text: "", skipped: true },
        otherSoftware: { text: "", skipped: false },
      }),
      "/projects/demo",
    );

    expect(request).toEqual({
      project_dir: "/projects/demo",
      source_location: "/home/ana/plate-reader",
      has_no_codebase: false,
      destination_tier: "project",
      data_kinds: ["Table / dataframe", "Time series"],
      data_kinds_other: "chromatograms",
      workflow_description: "Load the export, drop blanks, normalise.",
      interaction_wishes: null,
      other_software: null,
      // An explicit skip and a box the user walked past are the same claim —
      // "they did not say" — and both must reach the agent as skipped.
      skipped: ["interaction_wishes", "other_software"],
      provider: "claude-code",
      permission_mode: "safe",
    });
  });

  it("an answered question is distinguishable from a skipped one", () => {
    const request = buildRequest(
      form({
        dataKinds: ["Image"],
        workflowDescription: { text: "", skipped: true },
        interactionWishes: { text: "Let me pick the background patch.", skipped: false },
        otherSoftware: { text: "Fiji", skipped: false },
      }),
      "/p",
    );
    expect(request.skipped).toEqual(["workflow_description"]);
    expect(request.interaction_wishes).toBe("Let me pick the background patch.");
    expect(request.other_software).toBe("Fiji");
  });

  it("FR-010: no-codebase mode sends a null source and leaves the destination in effect", () => {
    const request = buildRequest(
      form({
        hasNoCodebase: true,
        sourceLocation: "/ignored",
        destinationTier: "user_library",
        dataKinds: ["Table / dataframe"],
        workflowDescription: { text: "Open the export in Excel every Monday.", skipped: false },
      }),
      "/p",
    );
    expect(request.source_location).toBeNull();
    expect(request.has_no_codebase).toBe(true);
    expect(request.destination_tier).toBe("user_library");
    expect(request.skipped).not.toContain("workflow_description");
  });
});

describe("blockingReasons (FR-017, FR-020)", () => {
  it("requires a source or the no-codebase option, and question 1", () => {
    const reasons = blockingReasons(form(), { projectDir: "/p", agentUsable: true });
    expect(reasons.some((r) => /I don't have a codebase/.test(r))).toBe(true);
    expect(reasons.some((r) => /at least one kind of data/.test(r))).toBe(true);
  });

  it("questions 3 and 4 never block", () => {
    const reasons = blockingReasons(form({ sourceLocation: "/repo", dataKinds: ["Array"] }), {
      projectDir: "/p",
      agentUsable: true,
    });
    expect(reasons).toEqual([]);
  });

  it("question 2 blocks in no-codebase mode only", () => {
    const withSource = blockingReasons(form({ sourceLocation: "/repo", dataKinds: ["Array"] }), {
      projectDir: "/p",
      agentUsable: true,
    });
    expect(withSource).toEqual([]);

    const noCodebase = blockingReasons(form({ hasNoCodebase: true, dataKinds: ["Array"] }), {
      projectDir: "/p",
      agentUsable: true,
    });
    expect(noCodebase.some((r) => /only description of your work/.test(r))).toBe(true);
  });
});

describe("validateWorkImportRequest — A2's ImportSessionContext rules", () => {
  it("accepts a well-formed body", () => {
    expect(validateWorkImportRequest(validRequest())).toEqual([]);
  });

  it("requires a non-blank provider", () => {
    expect(validateWorkImportRequest(validRequest({ provider: "" }))).toContain(
      "No agent was chosen to run the session.",
    );
    expect(validateWorkImportRequest(validRequest({ provider: "   " }))).toHaveLength(1);
  });

  it("requires the backend permission-mode spelling", () => {
    expect(validateWorkImportRequest(validRequest({ permission_mode: "safe" }))).toEqual([]);
    expect(validateWorkImportRequest(validRequest({ permission_mode: "bypass" }))).toEqual([]);
    // The frontend spelling must have been mapped before this point (§7.4).
    const leaked = validateWorkImportRequest(
      validRequest({ permission_mode: "dangerous" as never }),
    );
    expect(leaked.some((p) => /not a valid permission mode/.test(p))).toBe(true);
  });

  it("requires exactly one of source_location and has_no_codebase", () => {
    expect(
      validateWorkImportRequest(validRequest({ source_location: "/repo", has_no_codebase: true })),
    ).toEqual([expect.stringMatching(/cannot both be sent/)]);
    expect(
      validateWorkImportRequest(validRequest({ source_location: null, has_no_codebase: false })),
    ).toEqual([expect.stringMatching(/Say where your work is/)]);
    expect(
      validateWorkImportRequest(validRequest({ source_location: null, has_no_codebase: true })),
    ).toEqual([]);
    // A whitespace-only path is not a path.
    expect(
      validateWorkImportRequest(validRequest({ source_location: "   ", has_no_codebase: false })),
    ).toEqual([expect.stringMatching(/Say where your work is/)]);
  });

  it("rejects a skipped key the backend does not know", () => {
    const problems = validateWorkImportRequest(
      validRequest({ skipped: ["workflow_description", "data_kinds" as never] }),
    );
    expect(problems.some((p) => /"data_kinds" is not a question that can be skipped/.test(p))).toBe(
      true,
    );
  });

  it("rejects a duplicated skip", () => {
    const problems = validateWorkImportRequest(
      validRequest({
        skipped: [
          "workflow_description",
          "workflow_description",
          "interaction_wishes",
          "other_software",
        ],
      }),
    );
    expect(problems).toContain('"workflow_description" is marked as skipped more than once.');
  });

  it("rejects a question that is both skipped and answered", () => {
    const problems = validateWorkImportRequest(
      validRequest({ other_software: "Fiji" }), // still listed in `skipped`
    );
    expect(problems).toContain('"other_software" is marked as skipped but also carries an answer.');
  });

  it("rejects a blank answer that is not marked as skipped", () => {
    const problems = validateWorkImportRequest(
      validRequest({ skipped: ["workflow_description", "interaction_wishes"] }),
    );
    expect(problems).toContain('"other_software" has no answer and is not marked as skipped.');
  });

  it("treats a whitespace-only answer as no answer", () => {
    const problems = validateWorkImportRequest(
      validRequest({
        other_software: "   ",
        skipped: ["workflow_description", "interaction_wishes"],
      }),
    );
    expect(problems).toContain('"other_software" has no answer and is not marked as skipped.');
  });
});

describe("buildRequest always satisfies A2's rules", () => {
  const reachable: Array<[string, WorkImportFormState]> = [
    ["every optional question skipped", form({ sourceLocation: "/repo", dataKinds: ["Array"] })],
    [
      "every optional question answered",
      form({
        sourceLocation: "/repo",
        dataKinds: ["Array"],
        workflowDescription: { text: "in, out", skipped: false },
        interactionWishes: { text: "background patch", skipped: false },
        otherSoftware: { text: "Fiji", skipped: false },
      }),
    ],
    [
      "no-codebase mode",
      form({
        hasNoCodebase: true,
        dataKinds: ["Table / dataframe"],
        workflowDescription: { text: "Excel, every Monday", skipped: false },
      }),
    ],
    [
      "no-codebase mode with a stale source still typed in the box",
      form({
        hasNoCodebase: true,
        sourceLocation: "/repo/typed/before/ticking",
        dataKinds: ["Image"],
        workflowDescription: { text: "Excel, every Monday", skipped: false },
      }),
    ],
    [
      "an answer typed and then skipped",
      form({
        sourceLocation: "/repo",
        dataKinds: ["Array"],
        interactionWishes: { text: "typed then abandoned", skipped: true },
      }),
    ],
    [
      "bypass permission mode",
      form({ sourceLocation: "/repo", dataKinds: ["Array"], permissionMode: "dangerous" }),
    ],
  ];

  it.each(reachable)("%s", (_label, state) => {
    expect(validateWorkImportRequest(buildRequest(state, "/projects/demo"))).toEqual([]);
  });
});

describe("startWorkImportSession (contract C3)", () => {
  it("POSTs the context to /api/work-import/sessions", async () => {
    const fetchMock = vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => ({
        tab_id: "a1b2c3d4e5f6",
        title: "Bring in my work",
        brief_path: ".scistudio/work-import/s1.md",
        provider: "claude-code",
        permission_mode: "safe",
      }),
    }));
    vi.stubGlobal("fetch", fetchMock);

    const request = buildRequest(form({ sourceLocation: "/repo", dataKinds: ["Array"] }), "/p");
    const response = await startWorkImportSession(request);

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("/api/work-import/sessions");
    expect(init.method).toBe("POST");
    expect(JSON.parse(String(init.body))).toEqual(request);
    expect(response.tab_id).toBe("a1b2c3d4e5f6");

    vi.unstubAllGlobals();
  });

  it("refuses to send a body the backend would reject", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      startWorkImportSession(validRequest({ source_location: "/repo", has_no_codebase: true })),
    ).rejects.toThrow(/cannot both be sent/i);
    // The point of the guard: no request was made at all.
    expect(fetchMock).not.toHaveBeenCalled();

    vi.unstubAllGlobals();
  });
});
