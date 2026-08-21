/**
 * ADR-053 Learning Center — reading-page markdown rendering (#2084).
 *
 * The renderer covers exactly the subset tutorial pages are written in, and
 * its one safety property is that page content is only ever emitted as text
 * nodes — a page can style nothing and script nothing.
 */

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { PageMarkdown } from "../PageMarkdown";

afterEach(cleanup);

describe("PageMarkdown", () => {
  it("renders headings, paragraphs, and inline marks", () => {
    render(
      <PageMarkdown
        source={"# Title\n\nA paragraph with **bold**, *stress*, and `code`.\n\n## Sub"}
      />,
    );

    expect(screen.getByRole("heading", { level: 3, name: "Title" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 4, name: "Sub" })).toBeInTheDocument();
    expect(screen.getByText("bold").tagName).toBe("STRONG");
    expect(screen.getByText("stress").tagName).toBe("EM");
    expect(screen.getByText("code").tagName).toBe("CODE");
  });

  it("joins a paragraph wrapped across source lines", () => {
    render(<PageMarkdown source={"One line\nthat wraps."} />);
    expect(screen.getByText("One line that wraps.")).toBeInTheDocument();
  });

  it("renders a list, folding wrapped items back together", () => {
    render(
      <PageMarkdown
        source={"- **Tidy** writes only where\n  the nodes sit.\n- **Focus** dims the rest."}
      />,
    );

    const items = screen.getAllByRole("listitem");
    expect(items).toHaveLength(2);
    expect(items[0]).toHaveTextContent("Tidy writes only where the nodes sit.");
  });

  it("emits page content as text, never as markup", () => {
    const { container } = render(
      <PageMarkdown source={'<script>window.pwned = true</script><b onmouseover="x">hi</b>'} />,
    );

    expect(container.querySelector("script")).toBeNull();
    expect(container.querySelector("b")).toBeNull();
    expect(container.textContent).toContain("<script>");
  });
});
