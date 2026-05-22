import { spawnSync } from "node:child_process";
import path from "node:path";

import { expect, test } from "../../support/scistudio";
import {
  codeBlockFormatFixtures,
  codeBlockPromptText,
  type CodeBlockFormatFixture,
  type CodeBlockRuntimeId,
} from "../../fixtures/codeblockWorkflows";

type RuntimeAvailability = {
  runnable: boolean;
  reason?: string;
};

const repoRoot = path.resolve(process.cwd(), "..");
const pythonPath = [
  path.join(repoRoot, "src"),
  path.join(repoRoot, "packages", "scistudio-blocks-imaging", "src"),
  path.join(repoRoot, "packages", "scistudio-blocks-srs", "src"),
  process.env.PYTHONPATH,
]
  .filter(Boolean)
  .join(path.delimiter);

const missingRuntimePatterns: Record<CodeBlockRuntimeId, RegExp> = {
  python: /python|interpreter|not found/i,
  notebook: /notebook|jupyter|nbconvert|requires/i,
  r: /Rscript|R executable|not found/i,
  rmarkdown: /R Markdown|rmarkdown|Rscript|not found/i,
  quarto: /quarto|not found/i,
  shell: /POSIX shell|shell executable|not found/i,
  matlab: /MATLAB|Octave|not found/i,
  "matlab-live": /\.mlx|MATLAB|live scripts/i,
};

function spawnOk(command: string, args: string[], timeout = 10_000): boolean {
  const result = spawnSync(command, args, {
    encoding: "utf-8",
    shell: false,
    timeout,
    windowsHide: true,
  });
  return result.status === 0;
}

function commandExists(command: string): boolean {
  if (process.platform === "win32") {
    return spawnOk("where.exe", [command], 5_000);
  }
  return spawnOk("sh", ["-lc", `command -v ${shellQuote(command)} >/dev/null 2>&1`], 5_000);
}

function shellQuote(value: string): string {
  return `'${value.replace(/'/g, "'\\''")}'`;
}

function hasCompatibleShell(): boolean {
  const result = spawnSync(process.env.PYTHON ?? "python", [
    "-c",
    [
      "from scistudio.blocks.code.backends.shell import _resolve_shell_executable",
      "_resolve_shell_executable(mode='auto', interpreter_path=None, environment_config={})",
    ].join("; "),
  ], {
    encoding: "utf-8",
    env: { ...process.env, PYTHONPATH: pythonPath },
    shell: false,
    timeout: 10_000,
    windowsHide: true,
  });
  return result.status === 0;
}

function detectRuntime(id: CodeBlockRuntimeId): RuntimeAvailability {
  switch (id) {
    case "python":
      return { runnable: true };
    case "notebook":
      if (spawnOk("jupyter-nbconvert", ["--version"], 10_000)) return { runnable: true };
      if (spawnOk("jupyter", ["nbconvert", "--version"], 10_000)) return { runnable: true };
      return { runnable: false, reason: "Jupyter nbconvert is not available" };
    case "r":
      return commandExists("Rscript")
        ? { runnable: true }
        : { runnable: false, reason: "Rscript is not available" };
    case "rmarkdown":
      if (!commandExists("Rscript")) return { runnable: false, reason: "Rscript is not available" };
      return spawnOk(
        "Rscript",
        ["-e", "if (!requireNamespace('rmarkdown', quietly = TRUE)) quit(status = 42)"],
        20_000,
      )
        ? { runnable: true }
        : { runnable: false, reason: "R package rmarkdown is not available" };
    case "quarto":
      return commandExists("quarto")
        ? { runnable: true }
        : { runnable: false, reason: "quarto is not available" };
    case "shell":
      return hasCompatibleShell()
        ? { runnable: true }
        : { runnable: false, reason: "POSIX shell is not available" };
    case "matlab":
      return commandExists("matlab") || commandExists("octave")
        ? { runnable: true }
        : { runnable: false, reason: "MATLAB or Octave is not available" };
    case "matlab-live":
      return commandExists("matlab")
        ? { runnable: true }
        : { runnable: false, reason: "MATLAB is not available for .mlx live scripts" };
  }
}

async function installCodeBlockCase(studio: any, fixture: CodeBlockFormatFixture) {
  await studio.projectTree.writeFile(fixture.promptPath, `${codeBlockPromptText}\n`);
  await studio.projectTree.writeFile(fixture.scriptPath, fixture.scriptBody);
}

async function runDetailText(studio: any, runId: string): Promise<string> {
  const detail = await studio.api.getRun(runId);
  return JSON.stringify(detail);
}

test.describe("SciStudio CodeBlock format E2E @codeblock", () => {
  for (const fixture of codeBlockFormatFixtures) {
    test(`CBF-${fixture.id} @codeblock runs Load -> Code -> Save for ${fixture.label} (${fixture.extension})`, async ({
      studio,
    }, testInfo) => {
      test.slow();
      const availability = detectRuntime(fixture.id);
      testInfo.annotations.push({
        type: "codeblock-runtime",
        description: availability.runnable ? "runtime available" : availability.reason,
      });
      test.skip(
        fixture.id === "matlab-live" && availability.runnable,
        ".mlx live-script fixture generation requires MATLAB authoring tooling; CI normally validates the missing-runtime diagnostic.",
      );

      const project = await studio.createProject({ namePrefix: `codeblock-${fixture.id}` });
      await installCodeBlockCase(studio, fixture);
      await studio.installWorkflowFixture(project, fixture.workflow);
      await studio.openProject(project);
      await studio.loadWorkflowFromTree(fixture.workflow.workflowId);

      const result = await studio.runWorkflowAndWait(fixture.workflow.workflowId, {
        expectedStatus: /completed|failed/ as any,
        timeoutMs: fixture.id === "notebook" ? 45_000 : 15_000,
      });
      const detailText = await runDetailText(studio, result.runId);

      if (!availability.runnable) {
        expect(result.status, detailText).toBe("failed");
        await studio.expectCanvasNodeStatus("load_prompt", "done");
        await studio.expectCanvasNodeStatus("run_code", "error");
        expect(detailText).not.toMatch(/Block 'code_block' is not registered|not in registry/i);
        expect(detailText).toMatch(missingRuntimePatterns[fixture.id]);
        return;
      }

      expect(result.status, detailText).toBe("completed");
      await studio.expectCanvasNodeStatus("load_prompt", "done");
      await studio.expectCanvasNodeStatus("run_code", "done");
      await studio.expectCanvasNodeStatus("save_result", "done");
      await studio.expectProjectTreeContains(fixture.expectedOutputPath);
      await expect
        .poll(async () => studio.projectTree.readFile(fixture.expectedOutputPath), {
          message: `${fixture.expectedOutputPath} should contain the script output`,
        })
        .toContain(fixture.expectedContent);
    });
  }
});
