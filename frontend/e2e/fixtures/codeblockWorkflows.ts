import type { E2EWorkflow } from "./workflows";

export type CodeBlockRuntimeId =
  | "python"
  | "notebook"
  | "r"
  | "rmarkdown"
  | "quarto"
  | "shell"
  | "matlab"
  | "matlab-live";

export type CodeBlockFormatFixture = {
  id: CodeBlockRuntimeId;
  label: string;
  extension: string;
  scriptPath: string;
  scriptBody: string;
  promptPath: string;
  expectedOutputPath: string;
  expectedContent: string;
  workflow: E2EWorkflow;
};

const promptPath = "data/raw/codeblock-prompt.txt";
const promptText = "hello from load";

function workflowFor(id: CodeBlockRuntimeId, scriptPath: string): E2EWorkflow {
  const workflowId = `codeblock-${id}`;
  const expectedOutputPath = `data/artifacts/${workflowId}.txt`;
  return {
    workflowId,
    workflowPath: `workflows/${workflowId}.yaml`,
    expectedOutputPath,
    workflow: {
      id: workflowId,
      version: "1.0.0",
      description: `E2E CodeBlock ${id} LoadData -> CodeBlock -> SaveData workflow.`,
      nodes: [
        {
          id: "load_prompt",
          block_type: "load_data",
          layout: { x: 80, y: 120 },
          config: { params: { core_type: "Text", path: promptPath } },
        },
        {
          id: "run_code",
          block_type: "code_block",
          layout: { x: 380, y: 120 },
          config: {
            params: {
              script_path: scriptPath,
              exchange_root: "exchange",
              inputs: [{ name: "data", direction: "input", data_type: "Text", extension: ".txt" }],
              outputs: [{ name: "result", direction: "output", data_type: "Text", extension: ".txt" }],
            },
          },
        },
        {
          id: "save_result",
          block_type: "save_data",
          layout: { x: 700, y: 120 },
          config: { params: { core_type: "Text", path: expectedOutputPath } },
        },
      ],
      edges: [
        { source: "load_prompt:data", target: "run_code:data" },
        { source: "run_code:result", target: "save_result:data" },
      ],
      metadata: { fixture: "codeblock-format-e2e", codeblock_format: id },
    },
  };
}

function fixture(
  id: CodeBlockRuntimeId,
  label: string,
  extension: string,
  scriptBody: string,
): CodeBlockFormatFixture {
  const scriptPath = `scripts/codeblock-${id}${extension}`;
  const workflow = workflowFor(id, scriptPath);
  return {
    id,
    label,
    extension,
    scriptPath,
    scriptBody,
    promptPath,
    expectedOutputPath: workflow.expectedOutputPath,
    expectedContent: `${promptText} | ${id}`,
    workflow,
  };
}

export const codeBlockPromptText = promptText;

export const codeBlockFormatFixtures: CodeBlockFormatFixture[] = [
  fixture(
    "python",
    "Python script",
    ".py",
    `
from pathlib import Path

source = sorted(Path("inputs/data").glob("*.txt"))[0]
target = Path("outputs/result/result.txt")
target.parent.mkdir(parents=True, exist_ok=True)
target.write_text(source.read_text(encoding="utf-8").strip() + " | python\\n", encoding="utf-8")
`.trimStart(),
  ),
  fixture(
    "notebook",
    "Jupyter notebook",
    ".ipynb",
    `${JSON.stringify(
      {
        cells: [
          {
            cell_type: "code",
            execution_count: null,
            metadata: {},
            outputs: [],
            source: [
              "from pathlib import Path\n",
              "source = next(path for folder in [Path('inputs/data'), Path('../inputs/data'), Path('../../inputs/data')] for path in sorted(folder.glob('*.txt')))\n",
              "target_dir = next((folder for folder in [Path('outputs/result'), Path('../result'), Path('../../outputs/result')] if folder.parent.exists()), Path('outputs/result'))\n",
              "target = target_dir / 'result.txt'\n",
              "target.parent.mkdir(parents=True, exist_ok=True)\n",
              "target.write_text(source.read_text(encoding='utf-8').strip() + ' | notebook\\n', encoding='utf-8')\n",
            ],
          },
        ],
        metadata: {
          kernelspec: {
            display_name: "Python 3",
            language: "python",
            name: "python3",
          },
          language_info: {
            name: "python",
            version: "3.x",
          },
        },
        nbformat: 4,
        nbformat_minor: 5,
      },
      null,
      2,
    )}\n`,
  ),
  fixture(
    "r",
    "R script",
    ".R",
    `
input <- list.files("inputs/data", pattern = "\\\\.txt$", full.names = TRUE)[1]
dir.create("outputs/result", recursive = TRUE, showWarnings = FALSE)
writeLines(paste0(trimws(readLines(input, warn = FALSE)), " | r"), "outputs/result/result.txt")
`.trimStart(),
  ),
  fixture(
    "rmarkdown",
    "R Markdown document",
    ".Rmd",
    `
---
title: "CodeBlock R Markdown E2E"
output: html_document
---

\`\`\`{r}
out_dir <- file.path(Sys.getenv("SCISTUDIO_OUTPUTS_DIR"), "result")
dir.create(out_dir, recursive = TRUE, showWarnings = FALSE)
input <- list.files(file.path(Sys.getenv("SCISTUDIO_INPUTS_DIR"), "data"), pattern = "\\\\.txt$", full.names = TRUE)[1]
writeLines(paste0(trimws(readLines(input, warn = FALSE)), " | rmarkdown"), file.path(out_dir, "result.txt"))
\`\`\`
`.trimStart(),
  ),
  fixture(
    "quarto",
    "Quarto document",
    ".qmd",
    `
---
title: "CodeBlock Quarto E2E"
format: html
---

\`\`\`{python}
import os
from pathlib import Path

source = sorted(Path(os.environ["SCISTUDIO_INPUTS_DIR"], "data").glob("*.txt"))[0]
target = Path(os.environ["SCISTUDIO_OUTPUTS_DIR"], "result", "result.txt")
target.parent.mkdir(parents=True, exist_ok=True)
target.write_text(source.read_text(encoding="utf-8").strip() + " | quarto\\n", encoding="utf-8")
\`\`\`
`.trimStart(),
  ),
  fixture(
    "shell",
    "POSIX shell script",
    ".sh",
    `
set -eu
mkdir -p outputs/result
input_file="$(find inputs/data -name '*.txt' | sort | sed -n '1p')"
printf '%s | shell\\n' "$(cat "$input_file")" > outputs/result/result.txt
`.trimStart(),
  ),
  fixture(
    "matlab",
    "MATLAB or Octave script",
    ".m",
    `
input_files = dir(fullfile('inputs', 'data', '*.txt'));
input_path = fullfile(input_files(1).folder, input_files(1).name);
content = strtrim(fileread(input_path));
out_dir = fullfile('outputs', 'result');
if ~exist(out_dir, 'dir')
    mkdir(out_dir);
end
fid = fopen(fullfile(out_dir, 'result.txt'), 'w');
fprintf(fid, '%s | matlab\\n', content);
fclose(fid);
`.trimStart(),
  ),
  fixture(
    "matlab-live",
    "MATLAB live script",
    ".mlx",
    "SciStudio CodeBlock .mlx placeholder; valid live-script authoring requires MATLAB.\n",
  ),
];
