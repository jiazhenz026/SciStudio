// ADR-053 FR-011b — reading a step's `prefill`.
//
// The lookup itself, away from any dialog: what it finds, and what it declines
// to find. `newDropinFile.test.tsx` covers the one consumer end to end.

import { describe, expect, it } from "vitest";

import type {
  TutorialPrefillView,
  TutorialSessionResponse,
} from "../../../lib/api/learningCenter";
import { tutorialPrefillArgs, tutorialPrefillValue } from "../prefill";

function session(prefill: TutorialPrefillView[]): TutorialSessionResponse {
  return {
    source_kind: "core",
    source_id: "",
    tutorial_id: "welcome-to-scistudio",
    title: "Welcome to SciStudio",
    project_id: "p1",
    project_path: "/proj",
    step: {
      id: "create-the-block",
      index: 4,
      total: 15,
      title: null,
      say: "Press New, choose New custom block.",
      highlight: null,
      route_to: "canvas",
      prefill,
      awaiting_continue: false,
      satisfied: false,
    },
    satisfied_step_ids: [],
    status: "active",
    error: null,
    replay: null,
  };
}

describe("tutorialPrefillArgs", () => {
  it("finds the values the step declared for a target", () => {
    const payload = session([{ target: "new_custom_block", args: { filename: "normalize_fluorescence" } }]);

    expect(tutorialPrefillArgs(payload, "new_custom_block")).toEqual({
      filename: "normalize_fluorescence",
    });
  });

  it("finds nothing for a target this step does not seed", () => {
    const payload = session([{ target: "new_custom_block", args: { filename: "x" } }]);

    expect(tutorialPrefillArgs(payload, "some_other_dialog")).toBeNull();
  });

  it("finds nothing when no tutorial is running", () => {
    expect(tutorialPrefillArgs(null, "new_custom_block")).toBeNull();
    expect(tutorialPrefillArgs(undefined, "new_custom_block")).toBeNull();
  });
});

describe("tutorialPrefillValue", () => {
  it("returns undefined rather than an empty string, so `??` falls through to the product default", () => {
    const payload = session([{ target: "new_custom_block", args: { filename: "" } }]);

    expect(tutorialPrefillValue(payload, "new_custom_block", "filename")).toBeUndefined();
  });

  it("returns undefined for a value the target does not carry", () => {
    const payload = session([{ target: "new_custom_block", args: { filename: "x" } }]);

    expect(tutorialPrefillValue(payload, "new_custom_block", "destination")).toBeUndefined();
  });
});
