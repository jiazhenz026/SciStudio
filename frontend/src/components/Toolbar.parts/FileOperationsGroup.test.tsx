/**
 * ADR-054 Phase D (#2354) — New MiniApp in the toolbar New menu (FR-037).
 *
 * The third entry point into the one create dialog of FR-023. There is nothing
 * clever to assert: it is in the New menu, it calls back, and it is disabled
 * without a project — which is the requirement, and the thing a later edit to
 * this menu could silently drop.
 */
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { TooltipProvider } from "@/components/ui/tooltip";

import { resetAppStore } from "../../testUtils";

import { FileOperationsGroup } from "./FileOperationsGroup";

function renderGroup(options: { project?: boolean; onNewMiniApp?: () => void } = {}) {
  const onNewMiniApp = options.onNewMiniApp ?? vi.fn();
  render(
    <TooltipProvider>
      <FileOperationsGroup
        currentProject={options.project === false ? null : ({ id: "p1", name: "Proj" } as never)}
        isFileTab={false}
        onImport={vi.fn()}
        onInstallPackage={vi.fn()}
        onNewMiniApp={onNewMiniApp}
        onNewWorkflow={vi.fn()}
        onSave={vi.fn()}
        onSaveAs={vi.fn()}
      />
    </TooltipProvider>,
  );
  return { onNewMiniApp };
}

/*
 * Radix's DropdownMenu opens on the pointer sequence, which a plain
 * `fireEvent.click` does not emit under jsdom, and it reports
 * `pointer-events: none` on the portal while it transitions. Both worked
 * around exactly as `Toolbar.test.tsx` already works around them.
 */
function makeUser() {
  return userEvent.setup({ pointerEventsCheck: 0 });
}

afterEach(() => {
  cleanup();
  resetAppStore();
  vi.restoreAllMocks();
});

describe("New menu — New MiniApp (ADR-054 FR-037)", () => {
  it("offers New MiniApp and calls back", async () => {
    const user = makeUser();
    const harness = renderGroup();
    await user.click(screen.getByRole("button", { name: /^new$/i }));

    await user.click(await screen.findByRole("menuitem", { name: /new miniapp/i }));
    expect(harness.onNewMiniApp).toHaveBeenCalledTimes(1);
  });

  it("disables New MiniApp with no project open", async () => {
    const user = makeUser();
    const harness = renderGroup({ project: false });
    await user.click(screen.getByRole("button", { name: /^new$/i }));

    /*
     * The menu's disabled state is Radix's `data-disabled`, which the UI kit
     * styles `pointer-events-none` — the same mechanism every other entry in
     * this menu is disabled by. Asserting the marker rather than simulating a
     * click is deliberate: a synthetic click under jsdom bypasses the CSS that
     * does the blocking in a browser, so a click-based assertion would be
     * testing the runner, not the menu.
     */
    const entry = await screen.findByRole("menuitem", { name: /new miniapp/i });
    expect(entry).toHaveAttribute("aria-disabled", "true");
    expect(entry).toHaveAttribute("data-disabled");
    expect(harness.onNewMiniApp).not.toHaveBeenCalled();
  });
});
