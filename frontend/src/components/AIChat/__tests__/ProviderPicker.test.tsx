/**
 * `ProviderPicker` — the shared provider `<select>` (ADR-034 FR-020, FR-021).
 *
 * AI Chat, the New MiniApp dialog, Convert to interactive block and Bring in my
 * work all render this one picker unchanged (#2454), so this file pins every
 * observable of it: which options exist, in what order, with what text, and
 * which are disabled.
 */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ProviderPicker, PROVIDER_PLACEHOLDER_LABEL } from "../SetupScreen.parts/ProviderPicker";
import type { ProviderStatus } from "../../../store/types";

function status(overrides: Partial<ProviderStatus> & { name: string }): ProviderStatus {
  return {
    label: overrides.name,
    available: true,
    version: null,
    logged_in: true,
    ...overrides,
  };
}

/**
 * One row per combination the two booleans can express, in an order where
 * "available first" is observable: the first entry is NOT available, so a
 * picker that preserved the input order would fail.
 */
const AI_CHAT_ROWS: ProviderStatus[] = [
  status({ name: "qoder", label: "Qoder CLI", available: false, logged_in: false }),
  status({ name: "claude-code", label: "Claude Code", version: "1.2.3" }),
  status({ name: "codex", label: "Codex", logged_in: false }),
  status({ name: "kimi-code", label: "Kimi Code" }),
];

/** The rendered options, in DOM order. */
function renderedOptions(): { value: string; text: string; disabled: boolean }[] {
  const select = screen.getByTestId("setup-provider-select") as HTMLSelectElement;
  return Array.from(select.querySelectorAll("option")).map((option) => ({
    value: option.value,
    text: option.textContent ?? "",
    disabled: option.disabled,
  }));
}

afterEach(cleanup);

describe("ProviderPicker — the AI chat's rendering", () => {
  it("lists every provider, available first, with the two-boolean hints", () => {
    render(
      <ProviderPicker
        tabId="t1"
        providers={AI_CHAT_ROWS}
        statusLoading={false}
        provider={null}
        onChange={vi.fn()}
      />,
    );

    // Every observable of the control, pinned exactly. ADR-034 FR-021b puts
    // available providers first with registry order preserved inside each
    // group; FR-021a's hints are `(not installed)` and `(not logged in)`, and
    // "not logged in" is deliberately NOT disqualifying in the chat, because
    // the CLI runs its own login flow inside the PTY.
    expect(renderedOptions()).toEqual([
      { value: "", text: PROVIDER_PLACEHOLDER_LABEL, disabled: true },
      { value: "claude-code", text: "Claude Code v1.2.3", disabled: false },
      { value: "codex", text: "Codex (not logged in)", disabled: false },
      { value: "kimi-code", text: "Kimi Code", disabled: false },
      { value: "qoder", text: "Qoder CLI (not installed)", disabled: true },
    ]);
  });

  it("keeps the loading affordance and the change contract", () => {
    const onChange = vi.fn();
    const { rerender } = render(
      <ProviderPicker
        tabId="t1"
        providers={[]}
        statusLoading
        provider={null}
        onChange={onChange}
      />,
    );
    expect(screen.getByTestId("setup-provider-select")).toBeDisabled();
    expect(screen.getByTestId("setup-provider-loading")).toBeTruthy();

    rerender(
      <ProviderPicker
        tabId="t1"
        providers={AI_CHAT_ROWS}
        statusLoading={false}
        provider={null}
        onChange={onChange}
      />,
    );
    expect(screen.queryByTestId("setup-provider-loading")).toBeNull();

    fireEvent.change(screen.getByTestId("setup-provider-select"), {
      target: { value: "codex" },
    });
    expect(onChange).toHaveBeenCalledWith("codex");
    // FR-020a — a key that is not in the payload is dropped, never defaulted.
    fireEvent.change(screen.getByTestId("setup-provider-select"), {
      target: { value: "not-a-provider" },
    });
    expect(onChange).toHaveBeenCalledTimes(1);
  });
});
