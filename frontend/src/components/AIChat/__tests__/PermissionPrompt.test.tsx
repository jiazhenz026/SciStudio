import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useAppStore } from "../../../store";
import { PermissionPrompt } from "../PermissionPrompt";

describe("PermissionPrompt", () => {
  beforeEach(() => {
    useAppStore.setState({
      pendingPermissions: {},
      alwaysAllowedTools: {},
    });
  });
  afterEach(() => cleanup());

  it("renders nothing when no pending permission", () => {
    const onDecide = vi.fn();
    render(<PermissionPrompt chatId="c1" onDecide={onDecide} />);
    expect(screen.queryByTestId("permission-modal")).toBeNull();
  });

  it("renders modal when a permission is pending", () => {
    useAppStore.getState().setPendingPermission("c1", {
      requestId: "req-1",
      toolName: "Edit",
      toolInput: { file_path: "/x" },
    });
    render(<PermissionPrompt chatId="c1" onDecide={vi.fn()} />);
    expect(screen.getByTestId("permission-modal")).toBeInTheDocument();
    expect(screen.getByText(/Edit/)).toBeInTheDocument();
  });

  it("calls onDecide(approve) and clears pending on Approve", () => {
    useAppStore.getState().setPendingPermission("c1", {
      requestId: "req-2",
      toolName: "Read",
      toolInput: {},
    });
    const onDecide = vi.fn();
    render(<PermissionPrompt chatId="c1" onDecide={onDecide} />);
    fireEvent.click(screen.getByTestId("permission-allow-once"));
    expect(onDecide).toHaveBeenCalledWith("req-2", "approve");
    expect(useAppStore.getState().pendingPermissions["c1"]).toBeNull();
  });

  it("calls onDecide(deny) on Deny", () => {
    useAppStore.getState().setPendingPermission("c1", {
      requestId: "req-3",
      toolName: "Bash",
      toolInput: {},
    });
    const onDecide = vi.fn();
    render(<PermissionPrompt chatId="c1" onDecide={onDecide} />);
    fireEvent.click(screen.getByTestId("permission-deny"));
    expect(onDecide).toHaveBeenCalledWith("req-3", "deny");
  });

  it("Always-allow records the tool name + approves", () => {
    useAppStore.getState().setPendingPermission("c1", {
      requestId: "req-4",
      toolName: "Read",
      toolInput: {},
    });
    const onDecide = vi.fn();
    render(<PermissionPrompt chatId="c1" onDecide={onDecide} />);
    fireEvent.click(screen.getByTestId("permission-allow-always"));
    expect(onDecide).toHaveBeenCalledWith("req-4", "approve");
    expect(useAppStore.getState().alwaysAllowedTools["Read"]).toBe(true);
  });
});
