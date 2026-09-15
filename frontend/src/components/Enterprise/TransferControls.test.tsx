/**
 * ADR-055 Spec 4 — laptop-to-server transfer controls (#2322; story 4, FR-005).
 *
 * Upload goes through the existing staged `POST /api/data/upload` with
 * progress and a working cancel, whatever the file's size; download sends the
 * browser to the capability's template with the URL-encoded project-relative
 * path. Both are checked at the root mount and under `/user/alice/scistudio`,
 * and neither control renders without the `transfer` capability.
 */

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { resetBasePathCacheForTests } from "../../lib/api/base-path";
import { ApiError } from "../../lib/api/core";
import { UploadCancelledError, dataApi } from "../../lib/api/data";
import { resetCapabilitiesCacheForTests } from "../../lib/capabilities";
import { ContextMenu } from "../ProjectTree.parts/ContextMenu";
import type { TreeNodeData } from "../ProjectTree.parts/types";
import { DownloadToComputerItem } from "./DownloadToComputerItem";
import { EnterpriseToolbarControls } from "./EnterpriseToolbarControls";

const TRANSFER = {
  inlineMaxBytes: 8 * 1024 * 1024,
  downloadUrlTemplate: "/api/test-edition/transfer/download?path={path}",
};
const MOUNTS = [
  ["the root mount", ""],
  ["a prefixed mount", "/user/alice/scistudio"],
] as const;

/** A scripted XMLHttpRequest: records the request, and a test drives the answer. */
class FakeXhr {
  static instances: FakeXhr[] = [];
  method = "";
  url = "";
  body: unknown = null;
  status = 0;
  responseText = "";
  aborted = false;
  upload: { onprogress: ((event: ProgressEvent) => void) | null } = { onprogress: null };
  onload: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onabort: (() => void) | null = null;

  constructor() {
    FakeXhr.instances.push(this);
  }

  open(method: string, url: string): void {
    this.method = method;
    this.url = url;
  }

  send(body: unknown): void {
    this.body = body;
  }

  abort(): void {
    this.aborted = true;
    this.onabort?.();
  }

  progress(loaded: number, total: number): void {
    this.upload.onprogress?.({ loaded, total, lengthComputable: true } as ProgressEvent);
  }

  respond(status: number, body: unknown): void {
    this.status = status;
    this.responseText = JSON.stringify(body);
    this.onload?.();
  }
}

function lastXhr(): FakeXhr {
  const xhr = FakeXhr.instances[FakeXhr.instances.length - 1];
  if (xhr === undefined) throw new Error("no upload request was sent");
  return xhr;
}

function declare(value: unknown): void {
  if (value === undefined) {
    delete window.__SCISTUDIO_CAPABILITIES__;
  } else {
    window.__SCISTUDIO_CAPABILITIES__ = value;
  }
  resetCapabilitiesCacheForTests();
}

function mountAt(prefix: string): void {
  if (prefix) {
    window.__SCISTUDIO_BASE_PATH__ = prefix;
  } else {
    delete window.__SCISTUDIO_BASE_PATH__;
  }
  resetBasePathCacheForTests();
}

function fileNamed(name: string, size?: number): File {
  const file = new File(["scan bytes"], name, { type: "image/tiff" });
  if (size !== undefined) Object.defineProperty(file, "size", { value: size });
  return file;
}

function pick(file: File): void {
  fireEvent.change(screen.getByTestId("enterprise-upload-input"), { target: { files: [file] } });
}

function treeNode(overrides: Partial<TreeNodeData>): TreeNodeData {
  return {
    name: "scan 1 & 2.tif",
    path: "data/raw/scan 1 & 2.tif",
    type: "file",
    loaded: false,
    expanded: false,
    ...overrides,
  };
}

beforeEach(() => {
  FakeXhr.instances = [];
  vi.stubGlobal("XMLHttpRequest", FakeXhr);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  declare(undefined);
  mountAt("");
});

describe("uploadDataWithProgress", () => {
  it.each(MOUNTS)("sends the staged upload under %s and reports progress", async (_m, prefix) => {
    mountAt(prefix);
    const onProgress = vi.fn();
    const file = fileNamed("scan.tif");
    const pending = dataApi.uploadDataWithProgress(file, { onProgress });

    const xhr = lastXhr();
    expect(xhr.method).toBe("POST");
    expect(xhr.url).toBe(`${prefix}/api/data/upload`);
    expect((xhr.body as FormData).get("file")).toBe(file);

    xhr.progress(5, 10);
    expect(onProgress).toHaveBeenCalledWith({ loaded: 5, total: 10 });
    xhr.respond(200, { ref: "data-1", type_name: "Image", metadata: {} });
    await expect(pending).resolves.toEqual({ ref: "data-1", type_name: "Image", metadata: {} });
  });

  it("cancels through the signal", async () => {
    const abort = new AbortController();
    const pending = dataApi.uploadDataWithProgress(fileNamed("scan.tif"), { signal: abort.signal });
    abort.abort();
    await expect(pending).rejects.toBeInstanceOf(UploadCancelledError);
    expect(lastXhr().aborted).toBe(true);
  });

  it("sends nothing for a signal that is already aborted", async () => {
    const abort = new AbortController();
    abort.abort();
    await expect(
      dataApi.uploadDataWithProgress(fileNamed("scan.tif"), { signal: abort.signal }),
    ).rejects.toBeInstanceOf(UploadCancelledError);
    expect(FakeXhr.instances).toHaveLength(0);
  });

  it("rejects with the backend's reason", async () => {
    const pending = dataApi.uploadDataWithProgress(fileNamed("scan.tif"));
    lastXhr().respond(413, { detail: "File too large (max 2 GB)" });
    await expect(pending).rejects.toEqual(new ApiError("File too large (max 2 GB)", 413));
  });
});

describe("upload picker", () => {
  it("does not render without the transfer capability", () => {
    declare({ version: 1, identity: { user: "alice" } });
    render(<EnterpriseToolbarControls projectOpen />);
    expect(screen.queryByTestId("enterprise-upload")).toBeNull();
  });

  it("is disabled until a project is open", () => {
    declare({ version: 1, transfer: TRANSFER });
    render(<EnterpriseToolbarControls projectOpen={false} />);
    expect(screen.getByTestId("enterprise-upload")).toBeDisabled();
  });

  it.each(MOUNTS)(
    "uploads a picked file under %s with progress, whatever its size",
    async (_m, prefix) => {
      mountAt(prefix);
      declare({ version: 1, transfer: TRANSFER });
      render(<EnterpriseToolbarControls projectOpen />);

      // 200 MB is far over inlineMaxBytes: the picker still uses the staged route.
      pick(fileNamed("big-scan.tif", 200 * 1024 * 1024));

      const xhr = lastXhr();
      expect(xhr.url).toBe(`${prefix}/api/data/upload`);
      expect(screen.getByTestId("enterprise-upload")).toBeDisabled();
      xhr.progress(50 * 1024 * 1024, 200 * 1024 * 1024);
      expect(await screen.findByText("25%")).toBeInTheDocument();

      xhr.respond(200, { ref: "data-1", type_name: "Image", metadata: {} });
      expect(await screen.findByTestId("enterprise-upload-result")).toHaveTextContent(
        "Uploaded big-scan.tif",
      );
    },
  );

  it("cancels an upload in progress", async () => {
    declare({ version: 1, transfer: TRANSFER });
    render(<EnterpriseToolbarControls projectOpen />);
    pick(fileNamed("scan.tif"));

    fireEvent.click(await screen.findByTestId("enterprise-upload-cancel"));

    expect(lastXhr().aborted).toBe(true);
    expect(await screen.findByTestId("enterprise-upload-result")).toHaveTextContent(/cancelled/i);
    expect(screen.getByTestId("enterprise-upload")).toBeEnabled();
  });

  it("reports a failed upload", async () => {
    declare({ version: 1, transfer: TRANSFER });
    render(<EnterpriseToolbarControls projectOpen />);
    pick(fileNamed("scan.tif"));
    lastXhr().respond(400, { detail: "No project is open" });
    expect(await screen.findByRole("alert")).toHaveTextContent("No project is open");
  });
});

describe("download to this computer", () => {
  function captureDownloads(): Array<{ href: string | null; download: string }> {
    const downloads: Array<{ href: string | null; download: string }> = [];
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (
      this: HTMLAnchorElement,
    ) {
      downloads.push({ href: this.getAttribute("href"), download: this.download });
    });
    return downloads;
  }

  it("does not render without the transfer capability", () => {
    declare(undefined);
    render(<DownloadToComputerItem item={treeNode({})} onDone={vi.fn()} />);
    expect(screen.queryByTestId("enterprise-download")).toBeNull();
  });

  it("does not render for a directory", () => {
    declare({ version: 1, transfer: TRANSFER });
    render(
      <DownloadToComputerItem
        item={treeNode({ type: "directory", name: "raw", path: "data/raw" })}
        onDone={vi.fn()}
      />,
    );
    expect(screen.queryByTestId("enterprise-download")).toBeNull();
  });

  it.each(MOUNTS)("sends the browser to the template under %s", async (_m, prefix) => {
    mountAt(prefix);
    declare({ version: 1, transfer: TRANSFER });
    const downloads = captureDownloads();
    const onDone = vi.fn();
    render(<DownloadToComputerItem item={treeNode({})} onDone={onDone} />);

    fireEvent.click(screen.getByTestId("enterprise-download"));

    expect(downloads).toEqual([
      {
        href: `${prefix}/api/test-edition/transfer/download?path=data%2Fraw%2Fscan%201%20%26%202.tif`,
        download: "scan 1 & 2.tif",
      },
    ]);
    await waitFor(() => expect(onDone).toHaveBeenCalled());
  });

  it("appears in the project tree's context menu only with the capability", () => {
    const menu = { x: 0, y: 0, node: treeNode({}) };
    const handlers = {
      onClose: vi.fn(),
      onCopyName: vi.fn(),
      onCopyPath: vi.fn(),
      onReveal: vi.fn(),
    };

    declare(undefined);
    const { unmount } = render(<ContextMenu contextMenu={menu} {...handlers} />);
    expect(screen.queryByText("Download to this computer")).toBeNull();
    unmount();

    declare({ version: 1, transfer: TRANSFER });
    const downloads = captureDownloads();
    render(<ContextMenu contextMenu={menu} {...handlers} />);
    fireEvent.click(screen.getByText("Download to this computer"));
    expect(downloads).toHaveLength(1);
    expect(handlers.onClose).toHaveBeenCalled();
  });
});
