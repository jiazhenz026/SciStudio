/**
 * ADR-034 User Story 7, frontend half — issue #1994.
 *
 * The Python half lives in `tests/api/test_provider_registry_extensibility.py`:
 * it appends a fixture descriptor to the registry and proves `_VALID_PROVIDERS`,
 * `/api/ai/status`, and the AI Block config enum all pick it up with no other
 * source edit. The two halves meet at the status payload, which is the only
 * channel by which the frontend can learn a provider exists.
 *
 * So the frontend assertion is deliberately phrased as ignorance: a provider key
 * and label this codebase has *never seen* must render, sort, annotate, and
 * launch correctly, purely from the payload. If any of that required knowing the
 * key in advance — a literal union, a label map, an ordering table, a per-key
 * branch — these tests fail, and User Story 7's "one registry row" promise is
 * false regardless of what the backend does.
 *
 * The fixture keys here (`fixture-agent`, `second-fixture-agent`) exist nowhere
 * in `src/`. That is the point, and `tests/architecture/`
 * `test_adr_034_provider_single_source.py` guards it from the other direction by
 * failing if provider keys reappear in frontend source at all.
 *
 * Scope note: `SetupScreen.test.tsx` (A5) covers the picker's own FR-021
 * behaviour against the real five providers and is not edited here.
 */
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useAppStore } from "../../../store";
import { SetupScreen, _resetSetupStatusCache } from "../SetupScreen";
import { isKnownAgentProvider } from "../SetupScreen.parts/types";

import type { ProviderStatus } from "../SetupScreen.parts/types";
import type { ProjectResponse } from "../../../types/api";

const fakeProject: ProjectResponse = {
  id: "proj",
  name: "Project",
  description: "",
  path: "/abs/path/to/project",
  current_workflow_id: null,
  workflows: [],
  workflow_count: 0,
};

/**
 * A status payload from a backend whose registry has grown two rows the
 * frontend has never heard of. Ordering is deliberately hostile: the unknown
 * available provider arrives *after* an unavailable known one, so a component
 * that echoed payload order rather than applying FR-021b would pass by luck.
 */
const PAYLOAD_WITH_UNKNOWN_PROVIDERS: ProviderStatus[] = [
  { name: "claude-code", available: false, version: null, logged_in: false, label: "Claude Code" },
  {
    name: "fixture-agent",
    available: true,
    version: "9.9.9",
    logged_in: true,
    label: "Fixture Agent CLI",
  },
  {
    name: "second-fixture-agent",
    available: false,
    version: null,
    logged_in: false,
    label: "Second Fixture Agent",
  },
];

function mockStatusOnce(payload: unknown) {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => payload,
  });
  (global as unknown as { fetch: typeof fetch }).fetch = fetchMock as unknown as typeof fetch;
  return fetchMock;
}

async function renderWith(providers: ProviderStatus[]) {
  mockStatusOnce({ providers });
  const onLaunch = vi.fn();
  render(<SetupScreen tabId="us7" onLaunch={onLaunch} onCancel={vi.fn()} />);
  // FR-021c replaces the picker with the notice when nothing is available, so
  // wait on whichever branch this payload selects rather than assuming one.
  const expectsPicker = providers.some((p) => p.available);
  await waitFor(() =>
    expect(
      expectsPicker
        ? screen.queryByTestId(`setup-provider-option-${providers[0].name}`)
        : screen.queryByTestId("setup-no-providers-notice"),
    ).toBeTruthy(),
  );
  return { onLaunch };
}

function selectProvider(name: string) {
  act(() => {
    fireEvent.change(screen.getByTestId("setup-provider-select"), { target: { value: name } });
  });
}

function choosePermission(mode: "safe" | "dangerous") {
  act(() => {
    fireEvent.click(screen.getByTestId(`setup-permission-${mode}`));
  });
}

beforeEach(() => {
  _resetSetupStatusCache();
  useAppStore.setState({ currentProject: fakeProject });
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("ADR-034 User Story 7 — a provider the frontend has never heard of", () => {
  it("appears in the picker with the backend-supplied label and version", async () => {
    await renderWith(PAYLOAD_WITH_UNKNOWN_PROVIDERS);

    const option = screen.getByTestId("setup-provider-option-fixture-agent");
    // FR-020b: the label came from the payload. A frontend label map would have
    // no entry for this key and would fall back to the raw key or to blank.
    expect(option.textContent).toContain("Fixture Agent CLI");
    expect(option.textContent).toContain("9.9.9");
    expect((option as HTMLOptionElement).disabled).toBe(false);
  });

  it("annotates an unknown provider that is not installed, without hiding it", async () => {
    await renderWith(PAYLOAD_WITH_UNKNOWN_PROVIDERS);

    const option = screen.getByTestId("setup-provider-option-second-fixture-agent");
    expect(option.textContent).toContain("Second Fixture Agent");
    expect(option.textContent).toContain("(not installed)");
    expect((option as HTMLOptionElement).disabled).toBe(true);
  });

  it("sorts an unknown available provider above a known unavailable one (FR-021b)", async () => {
    await renderWith(PAYLOAD_WITH_UNKNOWN_PROVIDERS);

    const select = screen.getByTestId("setup-provider-select");
    const keys = within(select)
      .getAllByRole("option")
      .map((o) => (o as HTMLOptionElement).value)
      .filter((v) => v !== "");

    // Availability decides the grouping; familiarity plays no part in it.
    expect(keys[0]).toBe("fixture-agent");
    expect(keys).toEqual(["fixture-agent", "claude-code", "second-fixture-agent"]);
  });

  it("launches with the unknown key forwarded verbatim", async () => {
    const { onLaunch } = await renderWith(PAYLOAD_WITH_UNKNOWN_PROVIDERS);

    selectProvider("fixture-agent");
    choosePermission("dangerous");
    act(() => {
      fireEvent.click(screen.getByTestId("setup-launch"));
    });

    // The key reaches the launch payload unmodified — not normalised, not
    // mapped, not replaced by a default the frontend recognises.
    expect(onLaunch).toHaveBeenCalledWith({ provider: "fixture-agent", dangerous: true });
  });

  it("keeps Launch disabled for an unknown provider that is not installed", async () => {
    await renderWith(PAYLOAD_WITH_UNKNOWN_PROVIDERS);

    selectProvider("second-fixture-agent");
    choosePermission("safe");

    // `isKnownAgentProvider` rejects the disabled key, so nothing is selected
    // and Launch stays disabled. The user cannot launch an absent CLI just
    // because the frontend does not recognise the name.
    expect((screen.getByTestId("setup-launch") as HTMLButtonElement).disabled).toBe(true);
  });

  it("names unknown providers in the zero-install notice by product name (FR-021c)", async () => {
    await renderWith([
      {
        name: "fixture-agent",
        available: false,
        version: null,
        logged_in: false,
        label: "Fixture Agent CLI",
      },
      {
        name: "second-fixture-agent",
        available: false,
        version: null,
        logged_in: false,
        label: "Second Fixture Agent",
      },
    ]);

    const notice = await screen.findByTestId("setup-no-providers-notice");
    // FR-021c requires product names, and the only source of a product name for
    // a provider the frontend has never seen is the payload's `label`.
    expect(notice.textContent).toContain("Fixture Agent CLI");
    expect(notice.textContent).toContain("Second Fixture Agent");
    expect(notice.textContent).not.toContain("fixture-agent");
    expect(screen.queryByTestId("setup-provider-select")).toBeNull();
  });

  it("shows no provider-specific UI note for an unknown provider", async () => {
    // The one surviving provider-specific branch in SetupScreen is the #1859
    // Codex trust-hooks note, allowlisted by name in
    // `tests/architecture/test_adr_034_provider_single_source.py`. It must be
    // the *only* one: a second branch would mean the picker had started
    // accumulating per-provider knowledge again.
    await renderWith(PAYLOAD_WITH_UNKNOWN_PROVIDERS);

    selectProvider("fixture-agent");
    expect(screen.queryByTestId("setup-codex-trust-note")).toBeNull();
  });
});

describe("ADR-034 FR-020a — provider keys are validated against the payload", () => {
  it("accepts any key the payload lists and rejects any key it does not", () => {
    // The runtime guard is what replaces the deleted TypeScript literal union.
    // If it consulted a hardcoded list instead of the payload, the first
    // assertion would fail and the second would pass for the wrong reason.
    expect(isKnownAgentProvider("fixture-agent", PAYLOAD_WITH_UNKNOWN_PROVIDERS)).toBe(true);
    expect(isKnownAgentProvider("claude-code", PAYLOAD_WITH_UNKNOWN_PROVIDERS)).toBe(true);
    expect(isKnownAgentProvider("not-in-the-payload", PAYLOAD_WITH_UNKNOWN_PROVIDERS)).toBe(false);
    // An empty payload knows nothing, including the historical default.
    expect(isKnownAgentProvider("claude-code", [])).toBe(false);
  });

  it("drops an unknown selection rather than defaulting it", async () => {
    const { onLaunch } = await renderWith(PAYLOAD_WITH_UNKNOWN_PROVIDERS);

    selectProvider("a-key-the-backend-never-sent");
    choosePermission("safe");

    expect((screen.getByTestId("setup-launch") as HTMLButtonElement).disabled).toBe(true);
    expect(onLaunch).not.toHaveBeenCalled();
  });
});
