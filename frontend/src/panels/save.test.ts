import { afterEach, describe, expect, it, vi } from "vitest";
import { DEFAULT_PANEL_SAVE_LIMIT, savePanelBytes } from "./save";
afterEach(() => vi.restoreAllMocks());
describe("panel generated-byte save", () => {
  it("enforces the 100 MiB default and supports configured smaller limits", async () => {
    expect(DEFAULT_PANEL_SAVE_LIMIT).toBe(104857600);
    await expect(savePanelBytes({ name: "figure.png", mime: "image/png", data: new ArrayBuffer(9) }, 8)).rejects.toMatchObject({ code: "size_limit" });
    await expect(savePanelBytes({ name: "figure.png", mime: "image/png", data: { path: "/server/project" } })).rejects.toMatchObject({ code: "invalid_request" });
  });
  it("downloads bytes to a sanitized local filename without a backend write", async () => {
    URL.createObjectURL = vi.fn().mockReturnValue("blob:figure"); URL.revokeObjectURL = vi.fn();
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) {
      expect(this.download).toBe("figure.png"); expect(this.href).toBe("blob:figure");
    });
    await savePanelBytes({ name: "/remote/project/figure.png", mime: "image/png", data: new Uint8Array([1, 2]) });
    expect(click).toHaveBeenCalledOnce();
  });
});
