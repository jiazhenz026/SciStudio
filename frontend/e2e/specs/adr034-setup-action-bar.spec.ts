/**
 * ADR-034 User Story 6 / FR-021g / FR-021h — real-browser acceptance for the
 * pinned Setup action bar.
 *
 * WHY THIS FILE IS THE GATE. Spec §4.4 is explicit: the jsdom test
 * `keeps Cancel and Launch outside the scrollable setup body` asserts the class
 * strings `overflow-hidden` / `overflow-y-auto` / `shrink-0`, passes today, and
 * the button was still demonstrably below the fold in the running app. jsdom
 * performs no layout, so every assertion of that kind is structural only. The
 * acceptance evidence for User Story 6 must be a browser check at several panel
 * heights, and that is what this file is. It is not a smoke test; it is the
 * only thing that can tell the truth about FR-021g.
 *
 * WHAT THE BROWSER ACTUALLY SHOWED (Chromium, 1280x720, measured while
 * implementing T-011c). The spec's hypothesised root cause — a definite height
 * lost in the percentage chain threaded through the two `h-full` CSS-hiding
 * wrappers — did NOT reproduce. Converting both wrappers to
 * `flex min-h-0 flex-1 flex-col` produced byte-identical geometry at every
 * panel height from the collapsed size up to the default. The percentage chain
 * was resolving correctly.
 *
 * The measured defect is a crush, not a lost height: the chat surface has a
 * hard minimum content height of ~193px, and below it `SetupScreen`'s
 * `overflow-hidden` root clips its own action bar. The arithmetic, the two
 * acceptance scenarios that still fail because of it, and the out-of-scope
 * changes that would fix them are recorded at the `test.fail()` block below.
 *
 * The wrapper conversion is kept regardless: spec §4.2 mandates it, it makes
 * the chain independent of percentage-height resolution, and it is provably
 * side-effect-free here. It is NOT the fix, and this file does not pretend it
 * is.
 */
import { expect, test, type Page } from "@playwright/test";

import { installSystemMocks } from "../support/systemMocks";

/**
 * FR-020b — labels come from the payload, so the fixture supplies them. Two
 * available providers keep the picker in its normal (non-zero-install) branch
 * and let Launch become enabled, which is what makes `click({ trial: true })`
 * a real actionability check rather than a disabled-button no-op.
 */
const AI_STATUS = {
  providers: [
    {
      name: "claude-code",
      label: "Claude Code",
      available: true,
      version: "1.2.3",
      logged_in: true,
    },
    { name: "codex", label: "Codex", available: true, version: "0.9.0", logged_in: false },
    { name: "kimi", label: "Kimi Code", available: false, version: null, logged_in: false },
  ],
};

const BOTTOM_PANEL = 'section:has([data-testid="bottom-panel-pin-toggle"])';
const SEPARATOR = '[role="separator"][aria-orientation="horizontal"]';

/**
 * Boots the mocked app with a project open and the AI Chat surface showing a
 * Setup screen.
 *
 * `installSystemMocks` registers a `**\/*` catch-all, and Playwright matches
 * route handlers most-recently-registered first, so the two routes below must
 * be registered AFTER it to take precedence.
 */
async function openChatSetup(page: Page, seedStorage?: () => void): Promise<void> {
  await installSystemMocks(page);
  await page.route("**/api/ai/status", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(AI_STATUS),
    }),
  );
  // Two fixture gaps in the shared mocks, both of which take the whole app
  // down via the error boundary and would otherwise make the bottom-tab
  // regression check below unrunnable. Neither is a product defect:
  //   - the catch-all answers `GET /api/plots` with `{}`, so `PlotsTab`
  //     dereferences `plots.length` on undefined;
  //   - `GET /api/git/status` omits `modified` / `staged` / `untracked` /
  //     `conflicted`, so `GitStatusBadge` iterates undefined, and
  //     `GET /api/git/log` returns `refs` where `GraphLabels` reads
  //     `commit.branches`.
  // Patched here rather than in `support/systemMocks.ts` to keep this change
  // inside the files this spec owns.
  await page.route("**/api/plots**", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ plots: [], targets: [] }),
    }),
  );
  await page.route("**/api/git/status**", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        branch: "main",
        dirty: false,
        ahead: 0,
        behind: 0,
        modified: [],
        staged: [],
        untracked: [],
        conflicted: [],
        changed_files: [],
      }),
    }),
  );
  await page.route("**/api/git/log**", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([
        {
          sha: "1111111111111111111111111111111111111111",
          short_sha: "1111111",
          subject: "user: version A",
          author_name: "E2E",
          author_email: "e2e@example.test",
          author_date: "2026-05-22T12:00:00Z",
          parents: [],
          refs: ["HEAD", "main"],
          branches: ["main"],
        },
      ]),
    }),
  );
  if (seedStorage) await page.addInitScript(seedStorage);

  await page.goto("/");
  await page.getByRole("button", { name: "New Project" }).click();
  await page.getByLabel("Project name").fill("E2E Project");
  await page.locator('input[placeholder*="projects"]').fill("C:\\tmp");
  await page.getByLabel("Description").fill("fixture");
  await page.getByRole("button", { name: "Create project" }).click();

  await expect(page.locator(".react-flow")).toBeVisible();
  await page.getByRole("button", { name: "AI Chat" }).click();
  await expect(page.locator('[data-testid^="setup-screen-"]')).toBeVisible();
}

/** Height of the bottom panel's outer `<section>`, in CSS px. */
async function panelHeight(page: Page): Promise<number> {
  return Math.round((await page.locator(BOTTOM_PANEL).boundingBox())!.height);
}

/**
 * The bottom-panel size the app has persisted, in the same percent units
 * `uiSlice.panelSizes.bottom` uses. `ProjectWorkspace`'s `onLayoutChanged`
 * writes it on every drag, so it is the app's own measure of "how tall is the
 * bottom panel" and the natural unit for the restored-session scenario.
 */
async function storedBottomPercent(page: Page): Promise<number> {
  return page.evaluate(() => {
    const raw = window.localStorage.getItem("scistudio-studio-ui");
    return raw ? (JSON.parse(raw).state?.panelSizes?.bottom ?? NaN) : NaN;
  });
}

/** Drags the vertical separator by `deltaY` px. Positive shrinks the panel. */
async function dragSeparator(page: Page, deltaY: number): Promise<void> {
  const sep = page.locator(SEPARATOR);
  const box = (await sep.boundingBox())!;
  const x = box.x + box.width / 2;
  const y = box.y + box.height / 2;
  await page.mouse.move(x, y);
  await page.mouse.down();
  await page.mouse.move(x, y + deltaY, { steps: 12 });
  await page.mouse.up();
  await expect(sep).toBeVisible();
  // `onLayoutChanged` -> `setPanelSize` -> zustand persist is asynchronous;
  // let the persisted percent catch up before it is read back.
  await page.waitForTimeout(150);
}

/**
 * Drives the bottom panel to `targetPercent` of the app's persisted scale and
 * returns the pixel height actually reached.
 *
 * Iterative rather than one-shot: the group's percent scale is not the same as
 * the panel's pixel fraction of the viewport (the separator and the sibling
 * panel's own minimum both participate), so a single computed drag overshoots.
 * Converging on the app's own persisted number keeps this independent of the
 * library's internal accounting.
 */
async function resizeBottomPanelToPercent(page: Page, targetPercent: number): Promise<number> {
  for (let attempt = 0; attempt < 6; attempt += 1) {
    const currentPercent = await storedBottomPercent(page);
    const currentPx = await panelHeight(page);
    if (!Number.isFinite(currentPercent) || currentPercent <= 0) break;
    if (Math.abs(currentPercent - targetPercent) < 0.75) break;
    // Pixel height is proportional to the persisted percent.
    await dragSeparator(page, currentPx * (1 - targetPercent / currentPercent));
  }
  return panelHeight(page);
}

/**
 * The FR-021g assertion.
 *
 * "Inside the visible panel viewport" is checked three ways, because any one of
 * them alone can be satisfied by an element that the user still cannot use:
 *
 *   1. the Launch box lies inside the bottom panel's own rect — an element
 *      clipped by an `overflow-hidden` ancestor reports a box outside it;
 *   2. the Launch box lies inside the browser viewport, fully;
 *   3. no ancestor between the panel and the button has anything to scroll,
 *      which is the "without requiring the user to scroll any ancestor
 *      container" clause of FR-021g. This is the one a screenshot cannot show.
 */
async function expectLaunchReachable(page: Page): Promise<void> {
  const launch = page.getByTestId("setup-launch");
  await expect(launch).toBeVisible();

  const geometry = await page.evaluate((panelSel) => {
    const panel = document.querySelector(panelSel) as HTMLElement;
    const button = document.querySelector('[data-testid="setup-launch"]') as HTMLElement;
    const panelRect = panel.getBoundingClientRect();
    const buttonRect = button.getBoundingClientRect();

    const scrollable: { cls: string; scrollH: number; clientH: number }[] = [];
    let node: HTMLElement | null = button;
    while (node && node !== panel.parentElement) {
      if (node.scrollHeight - node.clientHeight > 1) {
        // The setup body is DESIGNED to scroll (it holds the pickers). Only
        // ancestors of the action bar matter for FR-021g.
        if (node.dataset.testid !== "setup-scroll-body") {
          scrollable.push({
            cls: node.className.toString().slice(0, 60),
            scrollH: node.scrollHeight,
            clientH: node.clientHeight,
          });
        }
      }
      node = node.parentElement;
    }
    return {
      panelTop: panelRect.top,
      panelBottom: panelRect.bottom,
      buttonTop: buttonRect.top,
      buttonBottom: buttonRect.bottom,
      viewportHeight: window.innerHeight,
      scrollable,
    };
  }, BOTTOM_PANEL);

  expect(
    geometry.scrollable,
    "FR-021g: no ancestor of the action bar may need scrolling to reach Launch",
  ).toEqual([]);
  expect(geometry.buttonBottom, "Launch must not extend below the panel").toBeLessThanOrEqual(
    geometry.panelBottom + 1,
  );
  expect(geometry.buttonTop, "Launch must not sit above the panel").toBeGreaterThanOrEqual(
    geometry.panelTop - 1,
  );
  expect(geometry.buttonBottom, "Launch must be inside the browser viewport").toBeLessThanOrEqual(
    geometry.viewportHeight,
  );
  await expect(launch).toBeInViewport({ ratio: 1 });
}

/** Selects a provider + permission mode so Launch becomes enabled. */
async function enableLaunch(page: Page): Promise<void> {
  await page.getByTestId("setup-provider-select").selectOption("claude-code");
  await page.getByTestId("setup-permission-safe").check();
  await expect(page.getByTestId("setup-launch")).toBeEnabled();
}

test("Launch stays inside the panel viewport at the default bottom-panel height", async ({
  page,
}) => {
  await openChatSetup(page);

  // `ProjectWorkspace` gives the bottom panel `defaultSize="45%"`.
  expect(await panelHeight(page), "sanity: panel is at its default height").toBeGreaterThan(200);

  await expectLaunchReachable(page);

  // FR-021h — the bar must be opaque, because the setup body scrolls behind it.
  const background = await page
    .getByTestId("setup-actions")
    .evaluate((el) => getComputedStyle(el).backgroundColor);
  expect(background, "FR-021h: the action bar must be fully opaque").toBe("rgb(255, 255, 255)");

  // Clickability, not just visibility: a trial click runs Playwright's full
  // actionability check (visible, stable, enabled, and receives pointer events
  // at its hit point) without launching a PTY.
  await enableLaunch(page);
  await page.getByTestId("setup-launch").click({ trial: true });

  await page.screenshot({ path: "e2e/artifacts/adr034-action-bar-default.png" });
});

/*
 * ---------------------------------------------------------------------------
 * The two acceptance scenarios below FAIL. They are marked `test.fail()` so the
 * gap is machine-checked instead of described in prose: Playwright reports an
 * error if either starts passing, which forces the annotation to be removed
 * rather than letting a fixed defect quietly keep a "known broken" label.
 *
 * THE MEASURED FLOOR. The Setup surface needs ~193px of bottom-panel height
 * before the action bar is fully inside the panel:
 *
 *     BottomPanel tab strip        61px   (min-content; no `shrink-0`)
 *   + content wrapper `py-2`       16px
 *   + TerminalTabs tab strip       37px
 *   + SetupScreen `py-3`           24px
 *   + SetupScreen action bar       55px   (`shrink-0`)
 *
 * Below that, `SetupScreen`'s root — which is `overflow-hidden` — is handed
 * less height than its own action bar occupies and clips the bar's lower edge.
 * At the persisted 30 the root measures clientHeight 69 against scrollHeight
 * 79, so the last ~10px of the bar (including ~3px of the Launch button) are
 * cut off. `sticky bottom-0` cannot rescue it: a sticky box may not be moved
 * outside its containing block, and by then the containing block is shorter
 * than the bar.
 *
 * NEITHER IS FIXABLE FROM THIS CHANGE'S OWNED FILES (`BottomPanel.tsx` and
 * `TerminalTabs.tsx`). What would fix them:
 *   - `App.parts/ProjectWorkspace.tsx`: give the bottom panel a pixel `minSize`
 *     around 200px instead of `10%`, so it cannot be dragged shorter than the
 *     surface it hosts;
 *   - `AIChat/SetupScreen.tsx`: drop the root `overflow-hidden` that clips the
 *     action bar once the root is shorter than the bar;
 *   - `BottomPanel.parts/TabBar.tsx` + `AIChat/TerminalTabs.parts/TabStrip.tsx`:
 *     let the two tab strips compress.
 * ---------------------------------------------------------------------------
 */

test.fail(
  "KNOWN FAILING - Launch stays inside the panel viewport at a restored persisted height below the default",
  async ({ page }) => {
    // `uiSlice` seeds `panelSizes.bottom` at 30 and the store persists whatever
    // the user last dragged to, so a session restored from an older snapshot
    // opens the panel below today's default (which measures 39.13 in the same
    // units). 30 lands at 183px — 10px under the floor above — so the Launch
    // button is clipped.
    //
    // Second recorded finding, verified in the browser: that persisted value is
    // currently WRITE-ONLY. `ProjectWorkspace` hardcodes the bottom panel's
    // `defaultSize="45%"` and never reads `panelSizes.bottom`, so seeding
    // localStorage does not move the panel and would make this test vacuous.
    // The panel is therefore driven to the persisted size directly, which is
    // the height the user is looking at whenever they drag the panel down —
    // and the height every session would open at once the restore is wired up.
    // TODO(#1994): a bottom-panel height below ~193px clips the Setup action
    //   bar, and `panelSizes.bottom` is persisted by `uiSlice` /
    //   `store/index.ts` but never applied to the bottom `ResizablePanel`.
    //   Both out of scope per the ADR-034 A6 dispatch (`ProjectWorkspace.tsx`
    //   and `SetupScreen.tsx` are not owned files).
    //   Followup: https://github.com/jiazhenz026/SciStudio/issues/1994
    await openChatSetup(page);

    const asOpened = await panelHeight(page);
    const asOpenedPercent = await storedBottomPercent(page);
    expect(
      asOpenedPercent,
      "sanity: today's default is larger than the persisted 30",
    ).toBeGreaterThan(30);

    const restored = await resizeBottomPanelToPercent(page, 30);
    expect(restored, "sanity: the panel really is smaller than the default").toBeLessThan(asOpened);
    expect(await storedBottomPercent(page), "the panel reached the restored size").toBeCloseTo(
      30,
      0,
    );

    await page.screenshot({ path: "e2e/artifacts/adr034-action-bar-restored.png" });
    await expectLaunchReachable(page);
  },
);

test.fail(
  "KNOWN FAILING - Launch stays inside the panel viewport at the panel's minimum height",
  async ({ page }) => {
    // User Story 6: "Given the bottom panel is dragged to its minimum height
    // ... then Launch remains visible and clickable."
    //
    // WHY IT FAILS, MEASURED: the bottom `ResizablePanel` declares
    // `minSize="10%"` and `collapsedSize="8%"`, which are ~64px and ~49px of a
    // 1280x720 viewport. `BottomPanel`'s own tab strip alone is 61px, so at the
    // floor essentially nothing reaches the chat surface. No arrangement of
    // layout classes inside the owned files can show a 36px button there; the
    // panel's permitted minimum is simply below the surface's minimum.
    // TODO(#1994): FR-021g ("visible at every bottom-panel height the panel
    //   permits") is unsatisfiable while the panel permits heights under the
    //   ~193px floor. Out of scope per the ADR-034 A6 dispatch.
    //   Followup: https://github.com/jiazhenz026/SciStudio/issues/1994
    await openChatSetup(page);

    // Drag well past the minimum; the panel clamps to `minSize` (or snaps to
    // `collapsedSize`, which is smaller still).
    const before = await panelHeight(page);
    await dragSeparator(page, 2000);
    const minimum = await panelHeight(page);
    expect(minimum, "sanity: the panel really is at its floor").toBeLessThan(before / 2);

    await page.screenshot({ path: "e2e/artifacts/adr034-action-bar-minimum.png" });
    await expectLaunchReachable(page);
  },
);

test("switching surfaces and tabs with a live agent keeps its PTY connected", async ({ page }) => {
  // Spec §4.5: the CSS-hiding wrappers exist so `TerminalTabs` stays mounted
  // across tab and surface switches. Unmounting fires `usePtyWebSocket`'s
  // cleanup, which calls `ws.close()` and kills the agent subprocess, losing
  // the user's conversation. This test is the guard on the layout change: it
  // asserts the wrappers still hide rather than unmount.
  await openChatSetup(page);
  await enableLaunch(page);
  await page.getByTestId("setup-launch").click();

  const running = page.locator('[data-testid^="terminal-tab-running-"]');
  await expect(running).toBeVisible();

  // Stamp the live tab's DOM node. React would drop the marker if the element
  // were unmounted and recreated, so its survival proves the node persisted.
  await running.evaluate((el) => {
    el.setAttribute("data-e2e-liveness-marker", "original");
  });
  const socketsBefore = await page.evaluate(
    () => (window.WebSocket as unknown as { instances: { readyState: number }[] }).instances.length,
  );
  expect(socketsBefore, "the agent opened a PTY WebSocket").toBeGreaterThan(0);

  // Surface switch: AI Chat -> Terminal -> AI Chat. Scoped to the bottom
  // panel's own tab strip: the running TerminalView also exposes a button
  // whose accessible name contains "terminal".
  const bottomTab = (name: string) =>
    page.locator(BOTTOM_PANEL).getByRole("button", { name, exact: true });
  await bottomTab("Terminal").click();
  await expect(page.locator('[data-testid="terminal-tabs-strip"]:visible')).toHaveCount(1);
  await bottomTab("AI Chat").click();

  // Tab switch within the chat surface: open a second chat tab and come back.
  const chatStrip = page.getByTestId("terminal-tabs-strip").first();
  await chatStrip.getByTestId("terminal-tabs-add").click();
  await expect(page.locator('[data-testid^="setup-screen-"]')).toBeVisible();
  await chatStrip.getByRole("button").first().click();

  await expect(
    page.locator('[data-e2e-liveness-marker="original"]'),
    "the live tab's DOM node survived every switch (it was hidden, not unmounted)",
  ).toHaveCount(1);

  const closed = await page.evaluate(
    () =>
      (window.WebSocket as unknown as { instances: { readyState: number }[] }).instances.filter(
        (s) => s.readyState === 3,
      ).length,
  );
  expect(closed, "no PTY WebSocket was closed by a surface or tab switch").toBe(0);
});

test("the inactive surface wrapper is display:none, not a zero-height flex box", async ({
  page,
}) => {
  // The CSS-hiding wrappers now carry both `flex` and `hidden`. Which display
  // value wins depends on the order Tailwind emits those utilities, not on the
  // order they appear in the class attribute. If `flex` ever won, the inactive
  // surface would render on top of the active one and both `TerminalTabs`
  // would fight for the same space. Assert the resolved value, not the class.
  await openChatSetup(page);

  const displays = await page.evaluate((panelSel) => {
    const panel = document.querySelector(panelSel) as HTMLElement;
    const wrap = panel.querySelector(":scope > div:nth-child(2)") as HTMLElement;
    return [...wrap.children]
      .slice(0, 2)
      .map((child) => getComputedStyle(child as HTMLElement).display);
  }, BOTTOM_PANEL);

  expect(displays, "chat surface visible, terminal surface hidden").toEqual(["flex", "none"]);
});

test("every other bottom tab still renders inside the panel after the wrapper change", async ({
  page,
}) => {
  // Spec §4.5: `BottomPanel`'s content wrapper hosts Config, Logs, Plots,
  // Lineage and Git as well as the two chat surfaces, and Lineage is the
  // reference that already worked — a regression there is the clearest signal
  // the change went too far. Checked at the default height and at a small
  // height, asserting each tab's content is laid out inside the panel rather
  // than pushed past its bottom edge.
  await openChatSetup(page);

  for (const percent of [null, 25]) {
    if (percent !== null) await resizeBottomPanelToPercent(page, percent);
    const height = await panelHeight(page);

    for (const tab of ["Config", "Logs", "Plots", "History", "Git"]) {
      await page.getByRole("button", { name: tab, exact: false }).first().click();
      // Tab content settles asynchronously (each tab fetches on mount), so let
      // it land before asserting the panel is still standing.
      await page.waitForTimeout(250);
      await expect(
        page.locator(BOTTOM_PANEL),
        `${tab} mounts without taking down the app at ${height}px`,
      ).toBeVisible();

      const result = await page.evaluate((panelSel) => {
        const panel = document.querySelector(panelSel) as HTMLElement;
        const wrap = panel.querySelector(":scope > div:nth-child(2)") as HTMLElement;
        const visible = [...wrap.children].filter(
          (child) => getComputedStyle(child as HTMLElement).display !== "none",
        ) as HTMLElement[];
        const wrapRect = wrap.getBoundingClientRect();
        return {
          count: visible.length,
          overflowingTop: visible.filter((el) => el.getBoundingClientRect().top > wrapRect.bottom)
            .length,
        };
      }, BOTTOM_PANEL);

      expect(result.count, `${tab} renders exactly one visible child at ${height}px`).toBe(1);
      expect(result.overflowingTop, `${tab}'s content starts inside the panel at ${height}px`).toBe(
        0,
      );
    }
  }
});
