// ADR-054 FR-028 / FR-029 — when the host offers to revert, and when it must
// not.
//
// The route's precondition has two clauses: the panel must resolve from a tier
// that can hold an override, and it must shadow something. Both are checked
// here rather than left to the route, so the control is offered exactly when it
// will work — an affordance whose only outcome is a refusal is worse than none.

import { describe, expect, it } from "vitest";

import type { PanelSpecSummary } from "../../types/api";
import { panelRevertTarget } from "../usePanelRevert";

function panel(overrides: Partial<PanelSpecSummary> = {}): PanelSpecSummary {
  return {
    panel_id: "core.plot.basic",
    display_name: "core.plot.basic",
    owner_kind: "project",
    owner_name: "demo",
    target_type: "PlotArtifact",
    target_types: ["PlotArtifact"],
    supports_collection: false,
    priority: 0,
    features: [],
    capability: "displaying",
    backend_provider: null,
    frontend_manifest: null,
    api_version: "1",
    tier: "project",
    shadows: "core",
    ...overrides,
  };
}

describe("panelRevertTarget", () => {
  it("names the tier a project copy would restore", () => {
    expect(panelRevertTarget(panel())).toBe("core");
  });

  it("names it for a user-library copy too", () => {
    expect(panelRevertTarget(panel({ tier: "user", shadows: "package" }))).toBe("package");
  });

  it("offers nothing for a panel that shadows nothing", () => {
    expect(panelRevertTarget(panel({ shadows: null }))).toBeNull();
  });

  it("offers nothing for a core or package panel", () => {
    // Those tiers hold no override to delete; the route refuses them, and the
    // interface must not put a control in front of a refusal.
    expect(panelRevertTarget(panel({ tier: "core", shadows: "package" }))).toBeNull();
    expect(panelRevertTarget(panel({ tier: "package", shadows: "core" }))).toBeNull();
  });

  it("offers nothing before the catalogue has an entry for the panel", () => {
    expect(panelRevertTarget(null)).toBeNull();
    expect(panelRevertTarget(undefined)).toBeNull();
  });
});
