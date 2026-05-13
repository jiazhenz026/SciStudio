/**
 * Unit tests for the generic row components introduced in issue #788
 * (display_class taxonomy).
 */

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import type { OtherEvent } from "../../../types/agentEvents";
import { CondensedToolRow } from "../genericRows/CondensedToolRow";
import { MetaEventRow } from "../genericRows/MetaEventRow";
import { RawEventRow } from "../genericRows/RawEventRow";
import { TextLikeRow } from "../genericRows/TextLikeRow";
import { ToolLikeRow } from "../genericRows/ToolLikeRow";

const mk = (kind: string, raw: Record<string, unknown>): OtherEvent =>
  ({ kind, raw }) as OtherEvent;

afterEach(() => cleanup());

describe("MetaEventRow", () => {
  it("renders a one-line [meta] label with the kind and summary", () => {
    render(<MetaEventRow event={mk("system/hook_started", { subtype: "hook_started" })} />);
    const row = screen.getByTestId("ev-meta");
    expect(row).toHaveTextContent("[meta]");
    expect(row).toHaveTextContent("system/hook_started");
    expect(row).toHaveTextContent("hook_started");
  });
});

describe("TextLikeRow", () => {
  it("renders the text content as a muted bubble", () => {
    render(<TextLikeRow event={mk("future_kind", { text: "hello there" })} />);
    expect(screen.getByTestId("ev-textlike")).toHaveTextContent("hello there");
  });

  it("returns null when no text-like field is present", () => {
    const { container } = render(<TextLikeRow event={mk("future_kind", { other: 1 })} />);
    expect(container.firstChild).toBeNull();
  });

  it("picks up `content` and `message` as fallbacks for text", () => {
    render(<TextLikeRow event={mk("k1", { content: "via content" })} />);
    expect(screen.getByTestId("ev-textlike")).toHaveTextContent("via content");
  });
});

describe("ToolLikeRow", () => {
  it("renders a CondensedToolRow for a future tool kind", () => {
    render(
      <ToolLikeRow event={mk("future_tool", { tool_name: "MagicTool", input: { x: 1 } })} />,
    );
    const row = screen.getByTestId("ev-toollike");
    expect(row).toHaveTextContent("MagicTool");
  });

  it("falls back to event.kind when no tool_name is present", () => {
    render(<ToolLikeRow event={mk("other_tool", { input: {} })} />);
    expect(screen.getByTestId("ev-toollike")).toHaveTextContent("other_tool");
  });
});

describe("RawEventRow", () => {
  it("renders a compact <kind> chip", () => {
    render(<RawEventRow event={mk("future_unknown", { random: 42 })} />);
    expect(screen.getByTestId("ev-raw")).toHaveTextContent("future_unknown");
  });
});

describe("CondensedToolRow", () => {
  it("is collapsed by default and shows ✔ on success", () => {
    render(<CondensedToolRow toolName="Bash" input={{ command: "ls" }} />);
    const row = screen.getByTestId("ev-condensed-tool");
    expect(row).toHaveAttribute("data-expanded", "false");
    expect(row).toHaveTextContent("Bash");
    expect(row).toHaveTextContent("✔");
  });

  it("flips to ✖ and red styling on error", () => {
    render(<CondensedToolRow toolName="Bash" input={{}} output="boom" isError />);
    const row = screen.getByTestId("ev-condensed-tool");
    expect(row).toHaveTextContent("✖");
    expect(row.className).toMatch(/red/);
  });

  it("expands on click and reveals input + output", () => {
    render(
      <CondensedToolRow toolName="Edit" input={{ file_path: "/x" }} output={{ ok: true }} />,
    );
    const row = screen.getByTestId("ev-condensed-tool");
    fireEvent.click(row.querySelector("button")!);
    expect(row).toHaveAttribute("data-expanded", "true");
    expect(screen.getByTestId("ev-condensed-tool-detail")).toBeInTheDocument();
    expect(screen.getByTestId("ev-condensed-tool-detail")).toHaveTextContent("file_path");
    expect(screen.getByTestId("ev-condensed-tool-detail")).toHaveTextContent("ok");
  });

  it("respects controlled `expanded` prop", () => {
    render(<CondensedToolRow toolName="Read" input={{ file: "/a" }} expanded />);
    const row = screen.getByTestId("ev-condensed-tool");
    expect(row).toHaveAttribute("data-expanded", "true");
    expect(screen.getByTestId("ev-condensed-tool-detail")).toBeInTheDocument();
  });
});
