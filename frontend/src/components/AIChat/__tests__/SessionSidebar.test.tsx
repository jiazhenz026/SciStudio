import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { useAppStore } from "../../../store";
import { SessionSidebar } from "../SessionSidebar";

describe("SessionSidebar", () => {
  beforeEach(() => {
    useAppStore.setState({
      activeChatId: null,
      sessions: [],
      eventsByChat: {},
      pendingPermissions: {},
    });
  });
  afterEach(() => cleanup());

  it("renders empty state when no sessions", () => {
    render(<SessionSidebar />);
    expect(screen.getByText(/No chats yet/i)).toBeInTheDocument();
  });

  it("creates a new chat on click", () => {
    render(<SessionSidebar />);
    fireEvent.click(screen.getByTestId("session-new"));
    expect(useAppStore.getState().sessions.length).toBe(1);
    expect(useAppStore.getState().activeChatId).toBe(useAppStore.getState().sessions[0]?.id);
  });

  it("switches active chat on click", () => {
    useAppStore.getState().createSession("a", "Alpha");
    useAppStore.getState().createSession("b", "Beta");
    render(<SessionSidebar />);
    fireEvent.click(screen.getByText("Beta"));
    expect(useAppStore.getState().activeChatId).toBe("b");
  });

  it("renames a session via double-click + enter", () => {
    useAppStore.getState().createSession("r", "Old");
    render(<SessionSidebar />);
    fireEvent.doubleClick(screen.getByText("Old"));
    const input = screen.getByTestId("session-rename-input-r") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "Renamed" } });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(useAppStore.getState().sessions.find((s) => s.id === "r")?.title).toBe("Renamed");
  });

  it("removes a session via × button", () => {
    useAppStore.getState().createSession("z", "Z");
    render(<SessionSidebar />);
    fireEvent.click(screen.getByTestId("session-delete-z"));
    expect(useAppStore.getState().sessions.find((s) => s.id === "z")).toBeUndefined();
  });
});
