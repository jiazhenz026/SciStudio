/**
 * `ProviderPicker` — the shared provider `<select>` (ADR-034 FR-020, FR-021).
 *
 * This file exists because ADR-053 spec 2 (#2001) added an optional
 * `optionOverrides` prop so the work-import dialog can list four graded
 * availability states in the same control the AI chat uses, rather than forking
 * it (FR-042). The prop is additive, and the whole risk of an additive change to
 * a shared component is that "additive" is asserted in a comment and quietly
 * stops being true.
 *
 * SO THE FIRST BLOCK BELOW IS A REGRESSION TEST, NOT A FEATURE TEST. It renders
 * the picker exactly as the AI chat does — no `optionOverrides` at all — and
 * pins every observable: which options exist, in what order, with what text,
 * and which are disabled. If the override path ever leaks into the default
 * path, this fails before `SetupScreen` does.
 */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ProviderPicker, PROVIDER_PLACEHOLDER_LABEL } from "../SetupScreen.parts/ProviderPicker";
import type { ProviderOptionOverride } from "../SetupScreen.parts/ProviderPicker";
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

describe("without optionOverrides — the AI chat's rendering, unchanged", () => {
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

  it("is unaffected by an empty override map or one that names nobody", () => {
    // A partial map must fall back per provider rather than blanking the rest,
    // so a caller that knows about one provider cannot erase the others.
    render(
      <ProviderPicker
        tabId="t1"
        providers={AI_CHAT_ROWS}
        statusLoading={false}
        provider={null}
        onChange={vi.fn()}
        optionOverrides={{ "no-such-provider": { hint: "(nonsense)", selectable: false } }}
      />,
    );
    expect(renderedOptions()).toEqual([
      { value: "", text: PROVIDER_PLACEHOLDER_LABEL, disabled: true },
      { value: "claude-code", text: "Claude Code v1.2.3", disabled: false },
      { value: "codex", text: "Codex (not logged in)", disabled: false },
      { value: "kimi-code", text: "Kimi Code", disabled: false },
      { value: "qoder", text: "Qoder CLI (not installed)", disabled: true },
    ]);
  });
});

describe("with optionOverrides — a caller that knows more than two booleans", () => {
  const OVERRIDES: Record<string, ProviderOptionOverride> = {
    "claude-code": { hint: null, selectable: true },
    codex: { hint: "(call failed)", selectable: false },
    "kimi-code": { hint: "(not available)", selectable: false },
    qoder: { hint: "(not signed in)", selectable: false },
  };

  it("renders the caller's suffix and selectable set, and orders by it", () => {
    render(
      <ProviderPicker
        tabId="work-import"
        providers={[
          status({ name: "codex", label: "Codex", available: false }),
          status({ name: "claude-code", label: "Claude Code", available: true }),
          status({ name: "kimi-code", label: "Kimi Code", available: false }),
          status({ name: "qoder", label: "Qoder CLI", available: false }),
        ]}
        statusLoading={false}
        provider="claude-code"
        onChange={vi.fn()}
        optionOverrides={OVERRIDES}
      />,
    );

    // The one selectable provider sorts first, and every other option says why
    // it is not — none of them saying "(not installed)", which is the
    // misreport FR-034 forbids for a provider whose live call failed.
    expect(renderedOptions()).toEqual([
      { value: "", text: PROVIDER_PLACEHOLDER_LABEL, disabled: true },
      { value: "claude-code", text: "Claude Code", disabled: false },
      { value: "codex", text: "Codex (call failed)", disabled: true },
      { value: "kimi-code", text: "Kimi Code (not available)", disabled: true },
      { value: "qoder", text: "Qoder CLI (not signed in)", disabled: true },
    ]);
  });
});
