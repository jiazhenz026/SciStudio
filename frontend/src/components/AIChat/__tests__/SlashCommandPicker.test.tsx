import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SlashCommandPicker } from "../SlashCommandPicker";

describe("SlashCommandPicker (#786)", () => {
  beforeEach(() => {
    global.fetch = vi.fn(async (url: string) => {
      if (typeof url === "string" && url.includes("/api/ai/slash_commands")) {
        return new Response(
          JSON.stringify({
            commands: [
              { name: "scieasy_test", description: "test cmd", source: "user-commands" },
              { name: "rdkit", description: "Cheminformatics", source: "user-skills" },
              { name: "deploy", description: "Deploy", source: "project" },
            ],
          }),
          { status: 200, headers: { "content-type": "application/json" } },
        );
      }
      throw new Error(`unexpected fetch: ${url}`);
    }) as unknown as typeof fetch;
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("does not render when input does not start with /", () => {
    render(
      <SlashCommandPicker
        projectDir="/proj"
        inputValue="hello"
        onPick={() => {}}
        onClose={() => {}}
      />,
    );
    expect(screen.queryByTestId("slash-picker")).toBeNull();
  });

  it("filters commands by typed prefix and groups by source", async () => {
    render(
      <SlashCommandPicker
        projectDir="/proj"
        inputValue="/sciea"
        onPick={() => {}}
        onClose={() => {}}
      />,
    );
    await waitFor(() => screen.getByTestId("slash-picker"));
    expect(screen.getByTestId("slash-item-scieasy_test")).toBeInTheDocument();
    expect(screen.queryByTestId("slash-item-rdkit")).toBeNull();
    expect(screen.queryByTestId("slash-item-deploy")).toBeNull();
  });

  it("calls onPick when an item is clicked", async () => {
    const onPick = vi.fn();
    render(
      <SlashCommandPicker
        projectDir="/proj"
        inputValue="/"
        onPick={onPick}
        onClose={() => {}}
      />,
    );
    await waitFor(() => screen.getByTestId("slash-picker"));
    fireEvent.mouseDown(screen.getByTestId("slash-item-rdkit"));
    expect(onPick).toHaveBeenCalledWith("rdkit");
  });
});
