/**
 * #2112 — the "open as" picker and the flow that raises it.
 *
 * Covers the three decisions `openDataFileAsPreview` makes in order: a
 * remembered choice opens without asking, a single candidate is not a
 * question, and anything else raises the picker — plus what cancelling and
 * un-remembering do.
 */

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type * as ApiModule from "../../lib/api";

vi.mock("../../lib/api", async () => {
  const actual = await vi.importActual<typeof ApiModule>("../../lib/api");
  return {
    ...actual,
    api: {
      ...actual.api,
      getOpenAsCandidates: vi.fn(),
      registerDataPath: vi.fn(),
      clearOpenAsType: vi.fn(),
    },
  };
});

import { api } from "../../lib/api";
import { openDataFileAsPreview } from "../../lib/openDataFile";
import { useAppStore } from "../../store";
import { OpenAsDialog } from "../OpenAsDialog";

const getOpenAsCandidatesMock = vi.mocked(api.getOpenAsCandidates);
const registerDataPathMock = vi.mocked(api.registerDataPath);
const clearOpenAsTypeMock = vi.mocked(api.clearOpenAsType);

function candidate(name: string, origin: string, packageName: string | null = null) {
  return {
    name,
    base_type: "DataObject",
    description: `${name} description`,
    origin,
    package_name: packageName,
    loadable: true,
  };
}

/** Radios are found by value: the accessible names overlap by design
 *  ("SRSImage description" contains "Image description"). */
function radioFor(typeName: string): HTMLInputElement {
  const radio = screen
    .getAllByRole("radio")
    .find((el) => (el as HTMLInputElement).value === typeName);
  if (radio === undefined) throw new Error(`no radio for ${typeName}`);
  return radio as HTMLInputElement;
}

const AMBIGUOUS = {
  path: "data/img.tif",
  extension: ".tif",
  candidates: [
    candidate("SRSImage", "project"),
    candidate("Image", "package", "scistudio-blocks-imaging"),
    candidate("Artifact", "core"),
  ],
  remembered: null,
};

let openPreviewTab: ReturnType<typeof useAppStore.getState>["openPreviewTab"] &
  ReturnType<typeof vi.fn>;

beforeEach(() => {
  openPreviewTab = vi.fn() as typeof openPreviewTab;
  useAppStore.setState({ openPreviewTab });
  getOpenAsCandidatesMock.mockReset();
  registerDataPathMock.mockReset();
  clearOpenAsTypeMock.mockReset();
  registerDataPathMock.mockResolvedValue({
    ref: "data-1",
    recorded_type: "Image",
    type_chain: ["DataObject", "Array", "Image"],
    display_name: "img.tif",
    extension: ".tif",
    remembered: true,
  });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("OpenAsDialog (#2112)", () => {
  it("lists every candidate with its tier and preselects the most specific", async () => {
    getOpenAsCandidatesMock.mockResolvedValue(AMBIGUOUS as any);
    render(<OpenAsDialog />);

    void openDataFileAsPreview("proj-1", "data/img.tif", "img.tif");
    await screen.findByTestId("open-as-dialog");

    for (const name of ["SRSImage", "Image", "Artifact"]) {
      expect(screen.getByText(name)).toBeInTheDocument();
    }
    // Tier is shown, so a candidate's provenance is legible.
    expect(screen.getByText("this project")).toBeInTheDocument();
    expect(screen.getByText("scistudio-blocks-imaging")).toBeInTheDocument();
    expect(screen.getByText("built in")).toBeInTheDocument();

    // First candidate (project tier) is preselected.
    expect(radioFor("SRSImage").checked).toBe(true);
  });

  it("opens the file as the picked type and remembers it when the box is checked", async () => {
    getOpenAsCandidatesMock.mockResolvedValue(AMBIGUOUS as any);
    render(<OpenAsDialog />);

    const opening = openDataFileAsPreview("proj-1", "data/img.tif", "img.tif");
    await screen.findByTestId("open-as-dialog");

    fireEvent.click(radioFor("Image"));
    fireEvent.click(screen.getByTestId("open-as-submit"));
    await opening;

    expect(registerDataPathMock).toHaveBeenCalledWith({
      projectId: "proj-1",
      path: "data/img.tif",
      typeName: "Image",
      remember: true,
    });
    expect(openPreviewTab).toHaveBeenCalledWith(
      expect.objectContaining({ ref: "data-1", recorded_type: "Image" }),
      "img.tif",
      undefined,
      { path: "data/img.tif", extension: ".tif", typeName: "Image", remembered: true },
    );
  });

  it("registers nothing and opens no tab when the picker is cancelled", async () => {
    getOpenAsCandidatesMock.mockResolvedValue(AMBIGUOUS as any);
    render(<OpenAsDialog />);

    const opening = openDataFileAsPreview("proj-1", "data/img.tif", "img.tif");
    await screen.findByTestId("open-as-dialog");
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    await opening;

    expect(registerDataPathMock).not.toHaveBeenCalled();
    expect(openPreviewTab).not.toHaveBeenCalled();
  });

  it("does not ask when a choice is already remembered", async () => {
    getOpenAsCandidatesMock.mockResolvedValue({ ...AMBIGUOUS, remembered: "Image" } as any);
    render(<OpenAsDialog />);

    await openDataFileAsPreview("proj-1", "data/img.tif", "img.tif");

    expect(screen.queryByTestId("open-as-dialog")).not.toBeInTheDocument();
    expect(registerDataPathMock).toHaveBeenCalledWith({
      projectId: "proj-1",
      path: "data/img.tif",
      typeName: undefined,
      remember: false,
    });
  });

  it("does not ask when only one type can open the extension", async () => {
    getOpenAsCandidatesMock.mockResolvedValue({
      path: "data/scan.nd2",
      extension: ".nd2",
      candidates: [candidate("Image", "package", "scistudio-blocks-imaging")],
      remembered: null,
    } as any);
    render(<OpenAsDialog />);

    await openDataFileAsPreview("proj-1", "data/scan.nd2", "scan.nd2");

    expect(screen.queryByTestId("open-as-dialog")).not.toBeInTheDocument();
    expect(openPreviewTab).toHaveBeenCalled();
  });

  it("forceAsk reopens the picker on a remembered extension, seeded with the choice", async () => {
    getOpenAsCandidatesMock.mockResolvedValue({ ...AMBIGUOUS, remembered: "Image" } as any);
    render(<OpenAsDialog />);

    const opening = openDataFileAsPreview("proj-1", "data/img.tif", "img.tif", { forceAsk: true });
    await screen.findByTestId("open-as-dialog");

    // Seeded with what is remembered, not with the first candidate.
    expect(radioFor("Image").checked).toBe(true);

    fireEvent.click(screen.getByTestId("open-as-submit"));
    await opening;
    expect(registerDataPathMock).toHaveBeenCalledWith(
      expect.objectContaining({ typeName: "Image", remember: true }),
    );
  });

  it("unchecking remember clears the stored choice — the reset path", async () => {
    getOpenAsCandidatesMock.mockResolvedValue({ ...AMBIGUOUS, remembered: "Image" } as any);
    clearOpenAsTypeMock.mockResolvedValue({ entries: [] } as any);
    render(<OpenAsDialog />);

    const opening = openDataFileAsPreview("proj-1", "data/img.tif", "img.tif", { forceAsk: true });
    await screen.findByTestId("open-as-dialog");

    fireEvent.click(screen.getByTestId("open-as-remember"));
    fireEvent.click(screen.getByTestId("open-as-submit"));
    await opening;

    await waitFor(() =>
      expect(clearOpenAsTypeMock).toHaveBeenCalledWith({ projectId: "proj-1", extension: ".tif" }),
    );
    expect(registerDataPathMock).toHaveBeenCalledWith(expect.objectContaining({ remember: false }));
  });

  it("falls through to the backend's own resolution when no dialog is mounted", async () => {
    getOpenAsCandidatesMock.mockResolvedValue(AMBIGUOUS as any);
    // No <OpenAsDialog /> rendered: an unanswerable question must not become a
    // refusal to open the file.
    await openDataFileAsPreview("proj-1", "data/img.tif", "img.tif");

    expect(registerDataPathMock).toHaveBeenCalledWith({
      projectId: "proj-1",
      path: "data/img.tif",
      typeName: undefined,
      remember: false,
    });
    expect(openPreviewTab).toHaveBeenCalled();
  });
});
