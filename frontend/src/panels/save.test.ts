import { afterEach, describe, expect, it, vi } from "vitest";
import { filesystemApi } from "../lib/api/filesystem";
import { panelsApi } from "../lib/api/panels";
import { DEFAULT_PANEL_SAVE_LIMIT, savePanelBytes } from "./save";
afterEach(() => vi.restoreAllMocks());
describe("panel generated-byte save", () => {
  it("enforces the 100 MiB default and supports configured smaller limits", async () => {
    expect(DEFAULT_PANEL_SAVE_LIMIT).toBe(104857600);
    await expect(
      savePanelBytes(
        { name: "figure.png", mime: "image/png", data: new ArrayBuffer(9) },
        undefined,
        8,
      ),
    ).rejects.toMatchObject({ code: "size_limit" });
    await expect(
      savePanelBytes({ name: "figure.png", mime: "image/png", data: { path: "/server/project" } }),
    ).rejects.toMatchObject({ code: "invalid_request" });
  });
  it("downloads bytes to a sanitized local filename without a backend write", async () => {
    URL.createObjectURL = vi.fn().mockReturnValue("blob:figure");
    URL.revokeObjectURL = vi.fn();
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (
      this: HTMLAnchorElement,
    ) {
      expect(this.download).toBe("figure.png");
      expect(this.href).toBe("blob:figure");
    });
    await savePanelBytes({
      name: "/remote/project/figure.png",
      mime: "image/png",
      data: new Uint8Array([1, 2]),
    });
    expect(click).toHaveBeenCalledOnce();
  });
  it("writes to the path the native dialog returned, starting in the project root", async () => {
    const dialog = vi
      .spyOn(filesystemApi, "openNativeSaveDialog")
      .mockResolvedValue({ paths: ["/Users/me/project/figure.png"], available: true });
    const save = vi.spyOn(panelsApi, "save").mockResolvedValue({
      saved: true,
      destination: "file",
      path: "/Users/me/project/figure.png",
    });
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click");
    const result = await savePanelBytes(
      { name: "figure.png", mime: "image/png", data: new Uint8Array([1, 2]) },
      "pc-1",
    );
    // No initial directory: the dialog route starts in the active project root.
    expect(dialog).toHaveBeenCalledWith({
      defaultFilename: "figure.png",
      fileFilter: "PNG (*.png)|*.png|All files (*.*)|*.*",
    });
    expect(save).toHaveBeenCalledWith("pc-1", "/Users/me/project/figure.png", expect.any(Blob));
    expect(click).not.toHaveBeenCalled();
    expect(result).toEqual({
      saved: true,
      destination: "file",
      path: "/Users/me/project/figure.png",
    });
  });
  it("saves nothing when the reader cancels the native dialog", async () => {
    vi.spyOn(filesystemApi, "openNativeSaveDialog").mockResolvedValue({
      paths: [],
      available: true,
    });
    const save = vi.spyOn(panelsApi, "save");
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click");
    const result = await savePanelBytes(
      { name: "figure.png", mime: "image/png", data: "x" },
      "pc-1",
    );
    expect(result).toEqual({ saved: false, destination: "cancelled" });
    expect(save).not.toHaveBeenCalled();
    expect(click).not.toHaveBeenCalled();
  });
  it("downloads when no native dialog is available", async () => {
    vi.spyOn(filesystemApi, "openNativeSaveDialog").mockRejectedValue(new Error("no dialog"));
    URL.createObjectURL = vi.fn().mockReturnValue("blob:figure");
    URL.revokeObjectURL = vi.fn();
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    const result = await savePanelBytes(
      { name: "figure.png", mime: "image/png", data: "x" },
      "pc-1",
    );
    expect(result).toEqual({ saved: true, destination: "download" });
    expect(click).toHaveBeenCalledOnce();
  });
});
