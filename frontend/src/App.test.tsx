import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "./App";
import { resetAppStore } from "./testUtils";

function jsonResponse(data: unknown) {
  return Promise.resolve({
    ok: true,
    status: 200,
    json: async () => data,
  });
}

describe("App", () => {
  beforeEach(() => {
    resetAppStore();
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        const url = String(input);
        if (url.endsWith("/api/projects/")) {
          return jsonResponse([]);
        }
        if (url.endsWith("/api/blocks/")) {
          return jsonResponse({
            blocks: [
              {
                name: "Process Block",
                type_name: "process_block",
                category: "process",
                description: "Simple transform",
                version: "0.1.0",
                input_ports: [],
                output_ports: [],
              },
            ],
          });
        }
        if (url.endsWith("/api/blocks/process_block/schema")) {
          return jsonResponse({
            name: "Process Block",
            type_name: "process_block",
            category: "process",
            description: "Simple transform",
            version: "0.1.0",
            input_ports: [],
            output_ports: [],
            config_schema: { properties: {} },
            type_hierarchy: [],
          });
        }
        return jsonResponse({});
      }),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("boots to the welcome screen when no project is open", async () => {
    render(<App />);

    expect(await screen.findByText("New Project")).toBeInTheDocument();
    await waitFor(() => {
      // After SciEasy → SciStudio rename both the Toolbar header and
      // the WelcomeScreen subtitle render "SciStudio"; use
      // getAllByText to assert "the brand is visible somewhere"
      // without locking which surface renders it.
      expect(screen.getAllByText("SciStudio").length).toBeGreaterThan(0);
    });
  });
});
