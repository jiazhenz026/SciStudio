// The prompts every entry point shares (ADR-053 FR-018, FR-023, FR-024).
//
// `dialogChannel` is what makes "one prompt" true rather than merely intended,
// so the questions are driven through the real channel and the real mounted
// `UserLibraryDialogs` — the same pair the palette, the canvas, and the editor
// toolbar all reach.

import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import {
  askCollisionResolution,
  askPromotionConfirmation,
  resetDialogChannel,
} from "../dialogChannel";
import { promotableBlock } from "../promotable";
import type { CollisionAnswer, PromotionAnswer, PromotionPlan } from "../promoteToUserLibrary";
import { UserLibraryDialogs } from "../UserLibraryDialogs";
import { makeBlock, projectType } from "./fixtures";

const item = promotableBlock(makeBlock({ type_name: "n", name: "Normalize", origin: "project" }));
const spectrum = projectType("Spectrum", "spectrum");
const trace = projectType("Trace", "trace");

function plan(overrides: Partial<PromotionPlan["cascade"]> = {}): PromotionPlan {
  return {
    item,
    filename: "normalize.py",
    cascade: {
      dependencies: overrides.dependencies ?? [],
      secondLevel: overrides.secondLevel ?? [],
      unreadable: overrides.unreadable ?? [],
    },
  };
}

beforeEach(() => {
  resetDialogChannel();
});

afterEach(() => {
  cleanup();
});

describe("the cascade offer — FR-023 / FR-024", () => {
  it("offers the dependencies checked, as one confirmed action", async () => {
    render(<UserLibraryDialogs />);
    let answer: PromotionAnswer | null = null;
    const pending = askPromotionConfirmation(
      plan({ dependencies: [{ type: spectrum, module: "spectrum" }] }),
    ).then((value) => {
      answer = value;
    });

    await screen.findByTestId("promotion-confirm-dialog");
    expect(screen.getByTestId("promotion-cascade-dependency")).toHaveTextContent("Spectrum");
    fireEvent.click(screen.getByTestId("promotion-confirm-submit"));
    await act(async () => {
      await pending;
    });

    expect(answer).toEqual({ action: "promote", includeDependencies: true });
  });

  it("warns explicitly the moment the cascade is unchecked", async () => {
    render(<UserLibraryDialogs />);
    const pending = askPromotionConfirmation(
      plan({ dependencies: [{ type: spectrum, module: "spectrum" }] }),
    );
    await screen.findByTestId("promotion-confirm-dialog");

    const checkbox = screen.getByTestId("promotion-cascade-toggle").querySelector("input")!;
    fireEvent.click(checkbox);
    expect(screen.getByTestId("promotion-cascade-decline-warning")).toHaveTextContent(
      "fail to load in other projects",
    );

    fireEvent.click(screen.getByTestId("promotion-confirm-submit"));
    await act(async () => {
      expect(await pending).toEqual({ action: "promote", includeDependencies: false });
    });
  });

  it("reports the second level rather than hiding it (FR-024)", async () => {
    render(<UserLibraryDialogs />);
    const pending = askPromotionConfirmation(
      plan({
        dependencies: [{ type: spectrum, module: "spectrum" }],
        secondLevel: [{ type: trace, via: spectrum }],
      }),
    );
    await screen.findByTestId("promotion-confirm-dialog");

    const notice = screen.getByTestId("promotion-second-level");
    expect(notice).toHaveTextContent("one level deep");
    expect(notice).toHaveTextContent("Trace");
    expect(notice).toHaveTextContent("Spectrum");

    fireEvent.click(screen.getByTestId("promotion-confirm-cancel"));
    await act(async () => {
      expect(await pending).toEqual({ action: "cancel" });
    });
  });

  it("shows no cascade controls when there are no project-level dependencies", async () => {
    render(<UserLibraryDialogs />);
    const pending = askPromotionConfirmation(plan());
    await screen.findByTestId("promotion-confirm-dialog");
    expect(screen.queryByTestId("promotion-cascade-toggle")).not.toBeInTheDocument();
    expect(screen.queryByTestId("promotion-second-level")).not.toBeInTheDocument();
    fireEvent.click(screen.getByTestId("promotion-confirm-cancel"));
    await act(async () => {
      await pending;
    });
  });
});

describe("the collision prompt — FR-018", () => {
  const request = {
    target: "blocks" as const,
    filename: "normalize.py",
    label: "Normalize",
    detail: "normalize.py already exists in the user library blocks directory.",
  };

  // Wrapped, because an `async` function returning a promise would await it
  // and the whole point is to hold the unanswered question.
  async function open(): Promise<{ pending: Promise<CollisionAnswer> }> {
    render(<UserLibraryDialogs />);
    const pending = askCollisionResolution(request);
    await screen.findByTestId("promotion-collision-dialog");
    return { pending };
  }

  it("offers overwrite AND save-as-new-name, and neither happens on its own", async () => {
    const { pending } = await open();
    expect(screen.getByTestId("promotion-collision-dialog")).toHaveTextContent(request.detail);
    expect(screen.getByTestId("promotion-collision-overwrite")).toBeInTheDocument();
    expect(screen.getByTestId("promotion-collision-rename")).toBeInTheDocument();

    fireEvent.click(screen.getByTestId("promotion-collision-cancel"));
    await act(async () => {
      expect(await pending).toEqual({ action: "cancel" });
    });
  });

  it("returns overwrite only when Overwrite is clicked", async () => {
    const { pending } = await open();
    fireEvent.click(screen.getByTestId("promotion-collision-overwrite"));
    await act(async () => {
      expect(await pending).toEqual({ action: "overwrite" });
    });
  });

  it("collects a new name and validates it as a Python identifier", async () => {
    const { pending } = await open();
    fireEvent.click(screen.getByTestId("promotion-collision-rename"));

    const input = screen.getByTestId("promotion-collision-rename-input");
    fireEvent.change(input, { target: { value: "2bad" } });
    expect(screen.getByTestId("promotion-collision-rename-submit")).toBeDisabled();

    fireEvent.change(input, { target: { value: "normalize_v2" } });
    fireEvent.click(screen.getByTestId("promotion-collision-rename-submit"));
    await act(async () => {
      expect(await pending).toEqual({ action: "rename", filename: "normalize_v2.py" });
    });
  });
});
