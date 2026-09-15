import { readFile } from "node:fs/promises";
import { expect, test } from "@playwright/test";

test.beforeEach(async ({ context, baseURL }) => {
  await context.addCookies([
    { name: "scistudio-test-session", value: "fake-guard-session-ok", url: baseURL! },
  ]);
});

for (const host of ["frame", "preview"]) {
  test(`${host}: opaque SDK reads artifact bytes, saves download and revokes mount`, async ({
    page,
    request,
    baseURL,
  }) => {
    const create = page.waitForResponse(
      (response) =>
        response.url().endsWith("/api/panels/contexts") && response.request().method() === "POST",
    );
    const grants: string[] = [];
    page.on("request", (req) => {
      if (/\/t\/[^/]+\/artifact\//.test(req.url())) grants.push(req.url());
    });
    await page.goto(`${baseURL}__panel_test__/host?host=${host}`);
    const created = await create;
    expect(created.status()).toBe(200);
    const mount = await created.json();
    const frame = page.frameLocator("iframe");
    await expect(frame.locator("#status")).toContainText('"artifact":"hello panel"');
    await expect(frame.locator("#status")).toContainText('"origin":"null"');
    await expect(frame.locator("#status")).toContainText('"text":"hello panel"');
    await expect(page.getByRole("status")).toHaveCount(0);
    expect(await page.locator("iframe").getAttribute("sandbox")).toBe("allow-scripts");
    const downloadEvent = page.waitForEvent("download");
    await frame.getByRole("button", { name: "Save bytes" }).click();
    const download = await downloadEvent;
    expect(download.suggestedFilename()).toBe("panel-download.txt");
    expect(await readFile((await download.path())!, "utf8")).toBe("hello panel");
    expect(grants).toHaveLength(1);
    const prefix = new URL(baseURL!).pathname.replace(/\/$/, "");
    expect(mount.entry_url).toMatch(new RegExp(`^${prefix}/api/panels/t/`));
    expect((await request.get(new URL(mount.sdk_url, baseURL).href)).status()).toBe(200);
    const closed = page.waitForResponse(
      (response) =>
        response.request().method() === "DELETE" && response.url().endsWith(mount.context_id),
    );
    await page.getByRole("button", { name: "Unmount" }).click();
    expect((await closed).status()).toBe(204);
    expect((await request.get(new URL(mount.entry_url, baseURL).href)).status()).toBe(403);
    expect((await request.get(grants[0])).status()).toBe(403);
  });
}

test("opaque browser mutation is refused by global middleware", async ({ page, baseURL }) => {
  await page.goto(`${baseURL}__panel_test__/host?panel=reader`);
  await expect(page.frameLocator("iframe").locator("#status")).toContainText(
    '"artifact":"hello panel"',
  );
  // This document lacks panel CSP so the request reaches Origin:null middleware.
  const destination = `${baseURL}api/panels/contexts`;
  const rejected = page.waitForResponse(
    (response) => response.url() === destination && response.status() === 403,
  );
  await page.evaluate((url) => {
    const frame = document.createElement("iframe");
    frame.sandbox.add("allow-scripts", "allow-forms");
    frame.srcdoc = `<form method="POST" action="${url}"></form><script>document.forms[0].submit()</script>`;
    document.body.appendChild(frame);
  }, destination);
  const response = await rejected;
  expect(response.status()).toBe(403);
  expect((await response.request().allHeaders()).origin).toBe("null");
  expect(await response.text()).toContain("Opaque Origin null");
});

for (const mode of ["early", "later"]) {
  test(`${mode} navigation never transfers authorized init to successor`, async ({
    page,
    request,
    baseURL,
  }) => {
    const successorAuthority: unknown[] = [];
    await page.exposeFunction("observePanelAuthority", (payload: unknown) =>
      successorAuthority.push(payload),
    );
    await page.addInitScript(() => {
      if (window === window.top) return;
      addEventListener("message", (event) => {
        if (location.pathname.endsWith("next.html") && event.data?.type === "init") {
          void (
            window as unknown as { observePanelAuthority: (value: unknown) => Promise<void> }
          ).observePanelAuthority(event.data.payload);
        }
      });
    });
    const create = page.waitForResponse(
      (response) =>
        response.url().endsWith("/api/panels/contexts") && response.request().method() === "POST",
    );
    const successorLoaded = page.waitForResponse((response) =>
      response.url().endsWith("next.html"),
    );
    await page.goto(`${baseURL}__panel_test__/host?panel=${mode}`);
    const mount = await (await create).json();
    if (mode === "later") {
      const frame = page.frameLocator("iframe");
      await expect(frame.locator("body")).toHaveAttribute("data-ready", "yes");
      await frame.getByRole("button", { name: "Navigate" }).click();
    }
    expect((await successorLoaded).status()).toBe(200);
    await expect(page.getByRole("alert")).toContainText(/navigated|ready\(\)|entry handshake/, {
      timeout: 15000,
    });
    expect(successorAuthority).toEqual([]);
    await expect
      .poll(async () => (await request.get(new URL(mount.entry_url, baseURL).href)).status())
      .toBe(403);
  });
}

test("composite opens legacy renderer, returns, and maximizes a panel child independently", async ({
  page,
  baseURL,
}) => {
  const mounts: { context_id: string; entry_url: string }[] = [];
  page.on("response", async (response) => {
    if (
      response.url().endsWith("/api/panels/contexts") &&
      response.request().method() === "POST" &&
      response.ok()
    )
      mounts.push(await response.json());
  });
  await page.goto(`${baseURL}__panel_test__/host?host=preview&panel=navigator&target=comp`);
  await expect(page.frameLocator("iframe").locator("#status")).toHaveText("navigator ready");
  await page.frameLocator("iframe").getByRole("button", { name: "Open legacy" }).click();
  await expect(page.getByText("legacy child text", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "← Back", exact: true }).click();
  await page.frameLocator("iframe").getByRole("button", { name: "Open table" }).click();
  const child = page.frameLocator('iframe[title="browser.table"]');
  await expect(child.locator("#status")).toContainText('"total_rows":2');
  expect(mounts).toHaveLength(2);
  const parentClose = page.waitForResponse(
    (response) =>
      response.request().method() === "DELETE" && response.url().endsWith(mounts[0].context_id),
  );
  await page.getByRole("button", { name: "Maximize child" }).click();
  expect((await parentClose).status()).toBe(204);
  await expect(page.locator("iframe")).toHaveCount(1);
  await expect(child.locator("#status")).toContainText('"total_rows":2');
  const read = page.waitForResponse(
    (response) => response.url().endsWith("/read") && response.request().method() === "POST",
  );
  await child.getByRole("button", { name: "Read again" }).click();
  expect((await read).status()).toBe(200);
  expect(mounts).toHaveLength(3);
  expect(new Set(mounts.map((mount) => mount.context_id)).size).toBe(3);
});
