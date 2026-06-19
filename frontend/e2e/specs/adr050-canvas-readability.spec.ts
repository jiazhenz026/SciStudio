/**
 * ADR-050 browser e2e — workflow canvas readability controls.
 *
 * Boots the real app surface (mocked backend via systemMocks) in Chromium and
 * verifies the shipped ADR-050 canvas readability controls are wired into the
 * running workflow editor:
 *   - the ReactFlow canvas renders;
 *   - the Tidy layout action is exposed near the canvas controls (FR-020);
 *   - the Focus control is exposed and is disabled until a node is selected,
 *     so focus mode cannot enter an ambiguous state (FR-017 / spec §3.1 edge
 *     case "Focus mode with no selected node").
 *
 * The fixed 104×104 square node geometry, the no-config node body, the unified
 * status surface, focus-set computation, and deterministic tidy layout are
 * covered authoritatively by the component/unit suites (BlockNode compactNode/
 * statusSurface/ports, focusMode, applyFocus, autoLayout, ConfigPanel). This
 * spec is the browser-level smoke that the controls reach the assembled app.
 *
 * Screenshot evidence is written to e2e/artifacts/.
 */
import { expect, test } from "@playwright/test";

import { openMockProject } from "../support/systemMocks";

test("ADR-050 canvas exposes Focus + Tidy readability controls in the running app", async ({
  page,
}) => {
  await openMockProject(page);

  // The workflow canvas is mounted.
  await expect(page.locator(".react-flow")).toBeVisible();

  // ADR-050 §3 readability controls are wired into the canvas.
  const tidy = page.getByRole("button", { name: "Tidy layout" });
  const focus = page.getByRole("button", { name: "Focus on selection" });
  await expect(tidy).toBeVisible();
  await expect(focus).toBeVisible();

  // FR-017 / spec §3.1 edge case — Focus is disabled with no selection.
  await expect(focus).toBeDisabled();

  await page.screenshot({ path: "e2e/artifacts/adr050-canvas-controls.png", fullPage: false });
});
