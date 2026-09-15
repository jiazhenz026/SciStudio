/**
 * #2454 (owner directive) — AI Chat and every other surface that starts an
 * agent session are one implementation.
 *
 * AI Chat's setup screen, New MiniApp, Convert to interactive block and Bring in
 * my work render the same `AgentLaunchSetup` over the same `useAgentStatus`
 * hook, and the Learning Center's provider introduction reads that same hook.
 * None of them may request the removed graded `/api/ai/availability` report.
 * The source check pins the imports so a second picker or a second status
 * fetch cannot come back quietly; the render check proves each surface actually
 * mounts the shared setup against `GET /api/ai/status`.
 */
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import type { ReactElement } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { BringInMyWorkDialog } from "../../BringInMyWorkDialog";
import { ProviderIntro } from "../../LearningCenter.parts/ProviderIntro";
import { ConvertToBlockDialog } from "../../../miniapps/ConvertToBlockDialog";
import { CreateMiniAppDialog } from "../../../miniapps/CreateMiniAppDialog";
import { useAppStore } from "../../../store";
import type { ProjectResponse } from "../../../types/api";
import { SetupScreen } from "../SetupScreen";
import { CLAUDE_STATUS, CODEX_STATUS, mockAgentStatus } from "./agentStatusFixture";

// vitest runs with the frontend package as its working directory.
const SRC_DIR = join(process.cwd(), "src");

const SESSION_SURFACES = [
  "components/AIChat/SetupScreen.tsx",
  "miniapps/CreateMiniAppDialog.tsx",
  "miniapps/ConvertToBlockDialog.tsx",
  "components/BringInMyWorkDialog.tsx",
];

const PROJECT: ProjectResponse = {
  id: "proj",
  name: "Project",
  description: "",
  path: "/abs/path/to/project",
  current_workflow_id: null,
  workflows: [],
  workflow_count: 0,
};

function read(relative: string): string {
  return readFileSync(join(SRC_DIR, relative), "utf8");
}

/** Drop comments — prose about an endpoint is not a request to it. */
function stripComments(text: string): string {
  return text.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");
}

function sourceFiles(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) {
      return entry.name === "node_modules" || entry.name === "__tests__" ? [] : sourceFiles(full);
    }
    if (/\.(test|spec)\.tsx?$/.test(entry.name)) return [];
    return /\.tsx?$/.test(entry.name) ? [full] : [];
  });
}

describe("one agent-session setup implementation", () => {
  it.each(SESSION_SURFACES)("%s renders AI Chat's AgentLaunchSetup over useAgentStatus", (file) => {
    const text = read(file);
    expect(text).toMatch(
      /import \{ AgentLaunchSetup \} from "[^"]*SetupScreen\.parts\/AgentLaunchSetup"/,
    );
    expect(text).toMatch(/useAgentStatus[\s\S]*from "[^"]*SetupScreen\.parts\/agentStatus"/);
    expect(text).toContain("<AgentLaunchSetup");
    expect(text).not.toContain("<ProviderPicker");
    expect(text).not.toContain("<PermissionModePicker");
  });

  it("the Learning Center provider introduction reads the same status hook", () => {
    const text = read("components/LearningCenter.parts/ProviderIntro.tsx");
    expect(text).toMatch(/import \{ useAgentStatus \} from "[^"]*SetupScreen\.parts\/agentStatus"/);
    expect(text).not.toContain("apiFetch");
  });

  it("only the shared status module fetches /api/ai/status, and nothing asks for availability", () => {
    for (const file of sourceFiles(SRC_DIR)) {
      const text = stripComments(readFileSync(file, "utf8"));
      expect(text, file).not.toContain("/api/ai/availability");
      if (!file.endsWith(join("SetupScreen.parts", "agentStatus.ts"))) {
        expect(text, file).not.toMatch(/["'`]\/api\/ai\/status["'`]/);
      }
    }
  });
});

describe("every surface mounts the shared setup against /api/ai/status", () => {
  beforeEach(() => {
    useAppStore.setState({ currentProject: PROJECT });
  });
  afterEach(() => {
    cleanup();
    useAppStore.setState({ currentProject: null });
  });

  const surfaces: Array<[string, () => ReactElement]> = [
    ["AI Chat", () => <SetupScreen tabId="t" onLaunch={vi.fn()} onCancel={vi.fn()} />],
    ["New MiniApp", () => <CreateMiniAppDialog open onOpenChange={vi.fn()} onCreated={vi.fn()} />],
    [
      "Convert to interactive block",
      () => (
        <ConvertToBlockDialog open onOpenChange={vi.fn()} panelId="lab.thing" onStarted={vi.fn()} />
      ),
    ],
    ["Bring in my work", () => <BringInMyWorkDialog onClose={vi.fn()} />],
  ];

  it.each(surfaces)("%s", async (_name, element) => {
    const backend = mockAgentStatus([CLAUDE_STATUS, CODEX_STATUS]);
    render(element());

    const setup = await screen.findByTestId("agent-launch-setup");
    await waitFor(() => expect(screen.getByTestId("setup-provider-option-codex")).toBeTruthy());
    expect(setup.contains(screen.getByTestId("setup-provider-select"))).toBe(true);
    expect(setup.contains(screen.getByTestId("setup-permission-group"))).toBe(true);
    expect(backend.statusCalls.length).toBeGreaterThan(0);
    expect(backend.availabilityCalls).toEqual([]);
  });

  it("Learning Center provider introduction", async () => {
    const backend = mockAgentStatus([CLAUDE_STATUS, CODEX_STATUS]);
    render(<ProviderIntro onContinue={vi.fn()} onOpenInstallGuide={vi.fn()} />);

    expect(await screen.findByTestId("provider-intro-codex")).toBeTruthy();
    expect(backend.statusCalls.length).toBeGreaterThan(0);
    expect(backend.availabilityCalls).toEqual([]);
  });
});
