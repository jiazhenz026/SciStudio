/**
 * ADR-054 spec 4 (T-005) — the output renderer (FR-011, SC-003).
 *
 * One fixture per MIME type the shell claims to support, plus the two ways an
 * unsupported one ends: the bundle's own `text/plain`, or a note that says so.
 *
 * The ANSI cases are here in force because the parser is ours. A traceback is
 * the output a person reads when something has already gone wrong, and the two
 * ways to get it wrong are to print the escapes as text and to hang on one that
 * never terminates — so both are asserted, on a real IPython traceback.
 */

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import type { ExploreOutput } from "../types/api";

import { OutputRenderer, parseAnsi, pickMimeType } from "./OutputRenderer";

const ESC = "\u001b";

/** IPython 8's own traceback for `1/0`, escapes and all. */
const IPYTHON_TRACEBACK = [
  `${ESC}[0;31m---------------------------------------------------------------------------${ESC}[0m`,
  `${ESC}[0;31mZeroDivisionError${ESC}[0m                         Traceback (most recent call last)`,
  `Cell ${ESC}[0;32mIn[3], line 1${ESC}[0m`,
  `${ESC}[0;32m----> 1${ESC}[0m ${ESC}[38;5;241m1${ESC}[39m${ESC}[38;5;241m/${ESC}[39m${ESC}[38;5;241m0${ESC}[39m`,
  "",
  `${ESC}[0;31mZeroDivisionError${ESC}[0m: division by zero`,
];

function renderOutputs(outputs: ExploreOutput[]) {
  return render(<OutputRenderer cellId="c1" outputs={outputs} />);
}

afterEach(cleanup);

describe("parseAnsi", () => {
  it("returns one unstyled run for text with no escapes", () => {
    expect(parseAnsi("just text")).toEqual([{ text: "just text", style: {} }]);
  });

  it("colours a run and resets it", () => {
    const segments = parseAnsi(`${ESC}[31mred${ESC}[0mplain`);
    expect(segments.map((segment) => segment.text)).toEqual(["red", "plain"]);
    expect(segments[0].style.color).toBe("#b91c1c");
    expect(segments[1].style).toEqual({});
  });

  it("reads the 256-colour cube and truecolor", () => {
    expect(parseAnsi(`${ESC}[38;5;196mx`)[0].style.color).toBe("rgb(255, 0, 0)");
    expect(parseAnsi(`${ESC}[38;2;1;2;3mx`)[0].style.color).toBe("rgb(1, 2, 3)");
  });

  it("carries bold, italic, underline and dim, and turns them off again", () => {
    const [on, off] = parseAnsi(`${ESC}[1;3;4mloud${ESC}[22;23;24mquiet`);
    expect(on.style).toMatchObject({ bold: true, italic: true, underline: true });
    expect(off.style.bold).toBeUndefined();
    expect(off.style.italic).toBeUndefined();
    expect(off.style.underline).toBeUndefined();
  });

  it("drops an escape that never terminates rather than printing it", () => {
    // The adversarial case: a traceback truncated mid-escape.
    expect(parseAnsi(`before${ESC}[31`)).toEqual([{ text: "before", style: {} }]);
    expect(parseAnsi(`${ESC}[`)).toEqual([]);
    expect(parseAnsi(ESC)).toEqual([]);
  });

  it("consumes a CSI that is not SGR, and a bare escape", () => {
    expect(parseAnsi(`a${ESC}[2Kb`).map((segment) => segment.text)).toEqual(["a", "b"]);
    expect(parseAnsi(`a${ESC}b`).map((segment) => segment.text)).toEqual(["a", "b"]);
  });

  it("survives a malformed parameter list without looping", () => {
    expect(parseAnsi(`${ESC}[;;;mx`).map((segment) => segment.text)).toEqual(["x"]);
    expect(parseAnsi(`${ESC}[38;5mx`).map((segment) => segment.text)).toEqual(["x"]);
    expect(parseAnsi(`${ESC}[99999mx`).map((segment) => segment.text)).toEqual(["x"]);
  });
});

describe("pickMimeType", () => {
  it("prefers the richest representation the shell can draw", () => {
    expect(pickMimeType({ "image/png": "x", "text/plain": "y" })).toBe("image/png");
    expect(pickMimeType({ "text/html": "x", "text/plain": "y" })).toBe("text/html");
    expect(pickMimeType({ "text/plain": "y" })).toBe("text/plain");
  });

  it("falls back to the bundle's plain text for an unknown type", () => {
    expect(pickMimeType({ "application/vnd.custom+json": {}, "text/plain": "y" })).toBe(
      "text/plain",
    );
  });

  it("answers null when the bundle carries nothing renderable", () => {
    expect(pickMimeType({ "application/vnd.custom+json": {} })).toBeNull();
    expect(pickMimeType({})).toBeNull();
  });
});

describe("every supported MIME type renders from its fixture (SC-003)", () => {
  it("renders stream output, and marks stderr apart from stdout", () => {
    renderOutputs([
      { output_type: "stream", name: "stdout", text: "hello\n" },
      { output_type: "stream", name: "stderr", text: "warning\n" },
    ]);
    expect(screen.getByTestId("explore-output-c1-0-stream").textContent).toBe("hello\n");
    expect(screen.getByTestId("explore-output-c1-1-stream").className).toContain("text-red-800");
  });

  it("renders a traceback with colour rather than with escapes", () => {
    renderOutputs([
      {
        output_type: "error",
        ename: "ZeroDivisionError",
        evalue: "division by zero",
        traceback: IPYTHON_TRACEBACK,
      },
    ]);
    const traceback = screen.getByTestId("explore-output-c1-0-traceback");
    expect(traceback.textContent).toContain("ZeroDivisionError");
    expect(traceback.textContent).toContain("division by zero");
    // Neither the escape byte nor its parameters reach the page.
    expect(traceback.textContent).not.toContain(ESC);
    expect(traceback.textContent).not.toContain("[0;31m");
    // And the colour is really there: the first run is IPython's red.
    const coloured = [...traceback.querySelectorAll("span")].filter(
      (span) => span.style.color !== "",
    );
    expect(coloured.length).toBeGreaterThan(0);
    expect(coloured[0].style.color).toBe("rgb(185, 28, 28)");
  });

  it("falls back to the error's name and value when there is no traceback", () => {
    renderOutputs([{ output_type: "error", ename: "ValueError", evalue: "bad input" }]);
    expect(screen.getByTestId("explore-output-c1-0-traceback").textContent).toBe(
      "ValueError: bad input",
    );
  });

  it("renders an execute_result's plain text", () => {
    renderOutputs([
      { output_type: "execute_result", data: { "text/plain": "42" }, execution_count: 3 },
    ]);
    expect(screen.getByTestId("explore-output-c1-0-text").textContent).toBe("42");
  });

  it("renders an image from the bundle, in preference to its plain text", () => {
    renderOutputs([
      {
        output_type: "display_data",
        data: { "image/png": "iVBORw0KGgo=\n", "text/plain": "<Figure size 640x480>" },
      },
    ]);
    const image = screen.getByTestId("explore-output-c1-0-image") as HTMLImageElement;
    expect(image.getAttribute("src")).toBe("data:image/png;base64,iVBORw0KGgo=");
    expect(screen.queryByTestId("explore-output-c1-0-text")).toBeNull();
  });

  it("renders HTML in a frame that is granted nothing (FR-011)", () => {
    renderOutputs([
      {
        output_type: "execute_result",
        data: { "text/html": "<table><tr><td>1</td></tr></table>", "text/plain": "  a" },
      },
    ]);
    const frame = screen.getByTestId("explore-output-c1-0-frame");
    expect(frame.tagName).toBe("IFRAME");
    expect(frame.getAttribute("srcdoc")).toContain("<table>");
    // The attribute is present and empty: present means sandboxed, empty means
    // no permission at all. An absent attribute would mean the opposite.
    expect(frame.getAttribute("sandbox")).toBe("");
    const granted = (frame.getAttribute("sandbox") ?? "").split(/\s+/).filter(Boolean);
    expect(granted).toEqual([]);
    expect(granted).not.toContain("allow-scripts");
    expect(granted).not.toContain("allow-same-origin");
  });

  it("renders SVG in the same frame, because SVG can carry script too", () => {
    renderOutputs([{ output_type: "display_data", data: { "image/svg+xml": "<svg/>" } }]);
    expect(screen.getByTestId("explore-output-c1-0-frame").getAttribute("sandbox")).toBe("");
  });

  it("renders markdown with the renderer already in the bundle", () => {
    renderOutputs([{ output_type: "display_data", data: { "text/markdown": "# Heading" } }]);
    expect(
      screen.getByTestId("explore-output-c1-0-markdown").querySelector("h1")?.textContent,
    ).toBe("Heading");
  });

  it("joins nbformat's multiline lists", () => {
    renderOutputs([
      {
        output_type: "execute_result",
        data: { "text/plain": ["one\n", "two\n"] as unknown as string },
      },
    ]);
    expect(screen.getByTestId("explore-output-c1-0-text").textContent).toBe("one\ntwo\n");
  });
});

describe("unknown types (FR-011)", () => {
  it("falls back to the plain text the bundle carries", () => {
    renderOutputs([
      {
        output_type: "display_data",
        data: { "application/vnd.plotly.v1+json": { data: [] }, "text/plain": "FigureWidget()" },
      },
    ]);
    expect(screen.getByTestId("explore-output-c1-0-text").textContent).toBe("FigureWidget()");
  });

  it("says so plainly when there is nothing it can draw", () => {
    renderOutputs([
      { output_type: "display_data", data: { "application/vnd.plotly.v1+json": { data: [] } } },
    ]);
    expect(screen.getByTestId("explore-output-c1-0-unrenderable").textContent).toContain(
      "application/vnd.plotly.v1+json",
    );
  });

  it("handles an output_type the shell has never heard of", () => {
    renderOutputs([{ output_type: "update_display_data", text: "still readable" }]);
    expect(screen.getByTestId("explore-output-c1-0-text").textContent).toBe("still readable");

    cleanup();
    renderOutputs([{ output_type: "future_thing" }]);
    expect(screen.getByTestId("explore-output-c1-0-unrenderable").textContent).toContain(
      "future_thing",
    );
  });
});

describe("a very long output", () => {
  it("truncates it with a control that shows all of it", () => {
    const long = "x".repeat(9000);
    renderOutputs([{ output_type: "stream", name: "stdout", text: long }]);
    const stream = screen.getByTestId("explore-output-c1-0-stream");
    expect(stream.textContent?.length).toBe(4000);

    fireEvent.click(screen.getByTestId("explore-output-c1-0-stream-show-all"));
    expect(screen.getByTestId("explore-output-c1-0-stream").textContent?.length).toBe(9000);
  });
});

describe("nothing to render", () => {
  it("renders nothing at all for a cell with no outputs", () => {
    const { container } = renderOutputs([]);
    expect(container.innerHTML).toBe("");
  });
});
