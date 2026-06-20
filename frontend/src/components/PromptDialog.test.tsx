import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { PromptDialog, type PromptRequest } from "./PromptDialog";

afterEach(() => {
  cleanup();
});

function makeRequest(overrides: Partial<PromptRequest> = {}): PromptRequest {
  return {
    title: "New workflow",
    label: "Workflow name",
    defaultValue: "Untitled",
    resolve: vi.fn(),
    ...overrides,
  };
}

describe("PromptDialog (bug#1 — window.prompt replacement)", () => {
  it("renders nothing when there is no active request", () => {
    const { container } = render(<PromptDialog request={null} onClose={vi.fn()} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("resolves with the trimmed entered value on submit", () => {
    const resolve = vi.fn();
    const onClose = vi.fn();
    render(<PromptDialog request={makeRequest({ resolve })} onClose={onClose} />);

    const input = screen.getByTestId("prompt-dialog-input");
    fireEvent.change(input, { target: { value: "  My Flow  " } });
    fireEvent.click(screen.getByTestId("prompt-dialog-submit"));

    expect(resolve).toHaveBeenCalledWith("My Flow");
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("resolves with null when cancelled", () => {
    const resolve = vi.fn();
    render(<PromptDialog request={makeRequest({ resolve })} onClose={vi.fn()} />);

    fireEvent.click(screen.getByRole("button", { name: /cancel/i }));
    expect(resolve).toHaveBeenCalledWith(null);
  });

  it("blocks submit and shows the validation error, keeping the dialog open", () => {
    const resolve = vi.fn();
    render(
      <PromptDialog
        request={makeRequest({
          resolve,
          validate: (value) => (value ? null : "Filename must not be empty."),
        })}
        onClose={vi.fn()}
      />,
    );

    fireEvent.change(screen.getByTestId("prompt-dialog-input"), { target: { value: "  " } });
    fireEvent.click(screen.getByTestId("prompt-dialog-submit"));

    expect(resolve).not.toHaveBeenCalled();
    expect(screen.getByText("Filename must not be empty.")).toBeInTheDocument();
  });
});
