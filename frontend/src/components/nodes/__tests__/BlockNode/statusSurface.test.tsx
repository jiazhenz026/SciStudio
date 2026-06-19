// ADR-050 §2.5 (#1698) — unified node status surface.
//
// Covers:
//   - FR-011: runtime state + problem severity render through ONE fixed-
//     geometry surface (a single corner glyph), never a body text row.
//   - §2.5 priority table: error (runtime or problem) > warning > runtime.
//   - FR-012: error activation calls onErrorClick (select node + open Logs).
//   - FR-013: warning activation calls onWarningClick (select node + open
//     Config).

import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";

import { NodeStatusSurface } from "../../BlockNode.parts/NodeStatusSurface";
import { openNativeDialogMock, renderNode } from "./test-utils";

afterEach(() => {
  cleanup();
  openNativeDialogMock.mockReset();
});

describe("BlockNode — single status surface (FR-011)", () => {
  it("renders exactly one status surface on the node", () => {
    const { container } = renderNode({ status: "running" });
    expect(container.querySelectorAll('[data-testid="node-status-surface"]')).toHaveLength(1);
  });

  it("reflects the runtime status on the surface dataset", () => {
    renderNode({ status: "running" });
    expect(screen.getByTestId("node-status-surface").getAttribute("data-status")).toBe("running");
  });
});

describe("NodeStatusSurface — §2.5 priority table", () => {
  it("renders the runtime indicator when there is no problem", () => {
    render(<NodeStatusSurface status="running" problemSeverity="none" />);
    expect(screen.getByTestId("node-status-surface").getAttribute("data-surface-kind")).toBe(
      "runtime",
    );
  });

  it("overlays a warning on a non-error runtime state (done + warning)", () => {
    render(<NodeStatusSurface status="done" problemSeverity="warning" />);
    expect(screen.getByTestId("node-status-surface").getAttribute("data-surface-kind")).toBe(
      "warning",
    );
  });

  it("error problem severity wins over the runtime state", () => {
    render(<NodeStatusSurface status="running" problemSeverity="error" />);
    expect(screen.getByTestId("node-status-surface").getAttribute("data-surface-kind")).toBe(
      "error",
    );
  });

  it("error runtime status renders the error surface even when severity=none", () => {
    render(<NodeStatusSurface status="error" problemSeverity="none" />);
    expect(screen.getByTestId("node-status-surface").getAttribute("data-surface-kind")).toBe(
      "error",
    );
  });

  it("paused renders the paused runtime indicator", () => {
    render(<NodeStatusSurface status="paused" problemSeverity="none" />);
    const surface = screen.getByTestId("node-status-surface");
    expect(surface.getAttribute("data-surface-kind")).toBe("runtime");
    expect(surface.getAttribute("data-status")).toBe("paused");
  });

  it("uses a translucent white circular badge background", () => {
    render(<NodeStatusSurface status="running" problemSeverity="none" />);
    const surface = screen.getByTestId("node-status-surface");
    expect(surface.getAttribute("style")).toContain("background-color: rgba(255, 255, 255, 0.86)");
    expect(surface.className).toContain("rounded-full");
  });

  it("renders done as a green check icon", () => {
    render(<NodeStatusSurface status="done" problemSeverity="none" />);
    const surface = screen.getByTestId("node-status-surface");
    expect(surface.getAttribute("data-icon")).toBe("check");
    expect(surface.getAttribute("style")).toContain("color: rgb(22, 163, 74)");
  });

  it("renders failed states as a red X icon", () => {
    render(<NodeStatusSurface status="failed" problemSeverity="none" />);
    const surface = screen.getByTestId("node-status-surface");
    expect(surface.getAttribute("data-surface-kind")).toBe("error");
    expect(surface.getAttribute("data-icon")).toBe("x");
    expect(surface.getAttribute("style")).toContain("color: rgb(220, 38, 38)");
  });
});

describe("NodeStatusSurface — activation (FR-012 / FR-013)", () => {
  it("calls onErrorClick when the error surface is activated", () => {
    const onErrorClick = vi.fn();
    render(<NodeStatusSurface status="error" onErrorClick={onErrorClick} />);
    fireEvent.click(screen.getByTestId("node-status-surface-button"));
    expect(onErrorClick).toHaveBeenCalledTimes(1);
  });

  it("calls onWarningClick when the warning surface is activated", () => {
    const onWarningClick = vi.fn();
    render(
      <NodeStatusSurface status="done" problemSeverity="warning" onWarningClick={onWarningClick} />,
    );
    fireEvent.click(screen.getByTestId("node-status-surface-button"));
    expect(onWarningClick).toHaveBeenCalledTimes(1);
  });

  it("does not call the error handler from a warning surface", () => {
    const onErrorClick = vi.fn();
    const onWarningClick = vi.fn();
    render(
      <NodeStatusSurface
        status="done"
        problemSeverity="warning"
        onErrorClick={onErrorClick}
        onWarningClick={onWarningClick}
      />,
    );
    fireEvent.click(screen.getByTestId("node-status-surface-button"));
    expect(onWarningClick).toHaveBeenCalledTimes(1);
    expect(onErrorClick).not.toHaveBeenCalled();
  });

  it("renders a non-interactive badge for a plain runtime state", () => {
    render(<NodeStatusSurface status="idle" />);
    expect(screen.queryByTestId("node-status-surface-button")).toBeNull();
    expect(screen.getByTestId("node-status-surface")).toBeInTheDocument();
  });

  it("surfaces the error detail through the tooltip, not a body row", () => {
    render(
      <NodeStatusSurface status="error" errorSummary="Division by zero" onErrorClick={vi.fn()} />,
    );
    const button = screen.getByTestId("node-status-surface-button");
    expect(button.getAttribute("title")).toBe("Division by zero");
    // The detail text is not present as a standalone text node.
    expect(screen.queryByText("Division by zero")).toBeNull();
  });
});

describe("BlockNode — status surface wires the node handlers", () => {
  it("invokes onErrorClick from the rendered node when status=error", () => {
    const onErrorClick = vi.fn();
    renderNode({ status: "error", onErrorClick });
    fireEvent.click(screen.getByTestId("node-status-surface-button"));
    expect(onErrorClick).toHaveBeenCalledTimes(1);
  });

  it("invokes onWarningClick from the rendered node when problemSeverity=warning", () => {
    const onWarningClick = vi.fn();
    renderNode({ status: "done", problemSeverity: "warning", onWarningClick });
    fireEvent.click(screen.getByTestId("node-status-surface-button"));
    expect(onWarningClick).toHaveBeenCalledTimes(1);
  });
});
