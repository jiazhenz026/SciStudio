/**
 * #2378 — the icon-only X that closes a popup dialog from its header.
 */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { DialogCloseButton } from "../ui/DialogCloseButton";

afterEach(() => cleanup());

describe("DialogCloseButton (#2378)", () => {
  it("shows no visible text and is named by aria-label", () => {
    render(<DialogCloseButton onClick={vi.fn()} />);

    const button = screen.getByRole("button", { name: "Close" });
    expect(button.textContent).toBe("");
    expect(button).toHaveAttribute("type", "button");
    expect(button.querySelector("svg")).not.toBeNull();
  });

  it("accepts a more specific accessible label", () => {
    render(<DialogCloseButton label="Close package manager" onClick={vi.fn()} />);

    expect(screen.getByRole("button", { name: "Close package manager" })).toBeInTheDocument();
  });

  it("calls onClick and forwards testid and disabled", () => {
    const onClick = vi.fn();
    const { rerender } = render(<DialogCloseButton data-testid="x" onClick={onClick} />);

    fireEvent.click(screen.getByTestId("x"));
    expect(onClick).toHaveBeenCalledTimes(1);

    rerender(<DialogCloseButton data-testid="x" disabled onClick={onClick} />);
    expect(screen.getByTestId("x")).toBeDisabled();
  });
});
