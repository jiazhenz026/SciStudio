/**
 * The left-panel tip pool (#1997).
 *
 * Interactive blocks, custom previewers, and custom data types have close to
 * zero surface area in the product, so a user who has never heard of them has
 * no moment at which they could learn they exist. The tip overlay is the
 * cheapest surface that reaches every user in every session, and this module
 * owns everything it says, so the pool can grow without touching the overlay
 * or the rotation.
 *
 * Every tip is shown on every left-panel tab (owner directive, #1997): a user
 * on the Blocks tab has as much to gain from a tip about the Git tab as from
 * one about blocks, and per-tab filtering would only shrink what each user
 * ever sees.
 *
 * Selection goes through `resolveTip` exclusively. ADR-053 §9.2 defers
 * condition-driven hints (detecting the situation from the workflow graph and
 * offering the matching capability) rather than rejecting them; keeping the
 * one selection function as the only entry point is what leaves that door
 * open — a later trigger mechanism widens its inputs and nothing else moves.
 */

export interface PaletteTip {
  /** Stable identity; used as the React key and in tests. */
  readonly id: string;
  /** Short label — what this tip is about, scannable in one glance. */
  readonly title: string;
  /** Two clamped lines of body copy, expandable when it does not fit. */
  readonly body: string;
}

export const PALETTE_TIPS: readonly PaletteTip[] = [
  {
    id: "what-is-a-block",
    title: "Blocks",
    body: "A block is one step of your analysis, with its own inputs and outputs.",
  },
  {
    id: "what-is-a-workflow",
    title: "Workflows",
    body: "A workflow is your analysis pipeline, run in dependency order.",
  },
  {
    id: "what-is-a-data-type",
    title: "Data types",
    body: "A data type is what your data modality really is — an image, a table, a sequence.",
  },
  {
    id: "multimodal-branches",
    title: "Multimodal",
    body: "Multimodal data runs in parallel — independent branches go at the same time.",
  },
  {
    id: "custom-data-types",
    title: "Custom types",
    body: "You can define your own data type on top of a built-in one: an image is a kind of array.",
  },
  {
    id: "formats-at-the-boundary",
    title: "File formats",
    body: "File formats matter at Load and Save. In between, data uses SciStudio's own types.",
  },
  {
    id: "formats-per-type",
    title: "Type formats",
    body: "The Data types tab lists the file formats each type can load from and save to.",
  },
  {
    id: "io-blocks",
    title: "Load and Save",
    body: "Load is where your files come in. Save is where your results go back out.",
  },
  {
    id: "custom-blocks",
    title: "Custom blocks",
    body: "You can write your own block for an analysis step nothing else covers.",
  },
  {
    id: "block-colour-and-icon",
    title: "Colour and icon",
    body: "A block of your own can set its own colour and icon on the canvas.",
  },
  {
    id: "custom-io-blocks",
    title: "Custom IO",
    body: "You can write your own IO block for an instrument format nothing else reads.",
  },
  {
    id: "process-blocks",
    title: "Process blocks",
    body: "Most blocks are process blocks: they take data, transform it, hand it on.",
  },
  {
    id: "code-blocks",
    title: "Code blocks",
    body: "A code block runs a script you already have — Python, R, shell, MATLAB, notebook.",
  },
  {
    id: "app-blocks",
    title: "App blocks",
    body: "An app block hands your data to an outside tool and picks its results back up.",
  },
  {
    id: "ai-blocks",
    title: "AI blocks",
    body: "An AI block runs an agent as one step of the workflow, on data you hand it.",
  },
  {
    id: "subworkflow-blocks",
    title: "Subworkflows",
    body: "A subworkflow packs a whole pipeline into one node you can reuse anywhere.",
  },
  {
    id: "interactive-blocks",
    title: "Interactive blocks",
    body: "A block can be interactive — it pauses, opens a window, and resumes with your decisions.",
  },
  {
    id: "one-step-per-block",
    title: "One step per block",
    body: "Give each block one small step, rather than stacking several into one.",
  },
  {
    id: "batches",
    title: "Many at once",
    body: "A block can take many items at once and work through them one by one.",
  },
  {
    id: "partial-reruns",
    title: "Partial re-runs",
    body: "Hover a node and hit Run block: it starts from there, reusing earlier results.",
  },
  {
    id: "variadic-ports",
    title: "Adding ports",
    body: "Some blocks take as many inputs as you need — look for the + beside their ports.",
  },
  {
    id: "tidy-layout",
    title: "Tidy your canvas",
    body: "Use Tidy to prevent your workflow canvas from turning into spaghetti.",
  },
  {
    id: "view-source",
    title: "View source",
    body: "View source shows the source code behind the canvas or a selected block.",
  },
  {
    id: "port-colours",
    title: "Port colours",
    body: "Each port's colour on the canvas tells you which data type it carries.",
  },
  {
    id: "type-mismatch",
    title: "Type mismatch",
    body: "Two blocks refuse to connect? Their data types disagree.",
  },
  {
    id: "block-config",
    title: "Block config",
    body: "Put values you keep changing into the block's config.",
  },
  {
    id: "save-to-my-library",
    title: "My Library",
    body: "Add a block you use often to My Library, and every project can use it.",
  },
  {
    id: "agent-does-the-work",
    title: "More than chat",
    body: "The agent does more than talk: it builds, runs, and fixes things in your project.",
  },
  {
    id: "agent-project-context",
    title: "Knows your project",
    body: "The agent already knows your project — its workflows, its blocks, its data.",
  },
  {
    id: "agent-builds-workflows",
    title: "Agent builds",
    body: "The agent can build and edit workflows itself, through the same runtime you use.",
  },
  {
    id: "agent-writes-blocks",
    title: "Ask for a block",
    body: "Ask the agent to write a custom block, and it scaffolds and registers it for you.",
  },
  {
    id: "agent-writes-types",
    title: "Ask for a type",
    body: "Ask the agent to write a data type of your own for the modality you work on.",
  },
  {
    id: "agent-writes-previewers",
    title: "Ask for a viewer",
    body: "Ask the agent for a previewer, and look at your own data your own way.",
  },
  {
    id: "agent-imports-existing-work",
    title: "Bring in my work",
    body: "Ask the agent to bring the analysis you already run into SciStudio. Start in the toolbar.",
  },
  {
    id: "agent-reads-data",
    title: "Knows your data",
    body: "The agent can look at your data and your results. It cannot edit your data directly.",
  },
  {
    id: "agent-tunes-settings",
    title: "Tune my analysis",
    body: "Show the agent a result you are unhappy with, and it can improve the analysis behind it.",
  },
  {
    id: "agent-scheduled-runs",
    title: "Scheduled runs",
    body: "Ask the agent to set up a scheduled run, and your workflow repeats on its own.",
  },
  {
    id: "agent-slash-commands",
    title: "Slash commands",
    body: "Type / in the agent to reach its own commands, where its settings live.",
  },
  {
    id: "agent-resume-session",
    title: "Resume a chat",
    body: "Type /resume in the agent to pick an earlier conversation back up.",
  },
  {
    id: "agent-reads-logs",
    title: "Debug a failure",
    body: "A block failed? The agent can read its logs and fix what broke.",
  },
  {
    id: "agent-writes-plots",
    title: "Ask for a plot",
    body: "Ask the agent to plot a result, and it writes the plot card for you.",
  },
  {
    id: "agent-runs-workflows",
    title: "The agent can run",
    body: "The agent can run a workflow for you and watch how it goes.",
  },
  {
    id: "agent-explains-workflows",
    title: "Explain this to me",
    body: "Open a workflow you did not build, and ask the agent what it does.",
  },
  {
    id: "agent-many-sessions",
    title: "More than one agent",
    body: "You can keep several agent sessions open, each on its own tab.",
  },
  {
    id: "agent-answers-questions",
    title: "Ask the agent",
    body: "Not sure how something here works? The agent knows SciStudio itself.",
  },
  {
    id: "agent-writes-interactive",
    title: "Agent writes UI",
    body: "The agent can write an interactive block, one that pauses for your decision.",
  },
  {
    id: "builtin-data-router",
    title: "Data Router",
    body: "Data Router opens a window where you drag each item to the output it belongs in.",
  },
  {
    id: "builtin-pair-editor",
    title: "Pair Editor",
    body: "Pair Editor reorders items in a collection so the right ones line up together.",
  },
  {
    id: "builtin-merge-collection",
    title: "Merge Collection",
    body: "Merge Collection joins several collections of the same type into a single one.",
  },
  {
    id: "project-is-a-folder",
    title: "Just a folder",
    body: "A project is an ordinary folder on your disk.",
  },
  {
    id: "project-raw-data",
    title: "Your raw data",
    body: "data/raw is yours to fill: put the files you want to analyse in there.",
  },
  {
    id: "project-save-outputs",
    title: "Where results go",
    body: "Save the results you want to keep in a folder of your own, such as data/processed.",
  },
  {
    id: "project-exchange",
    title: "Handing files over",
    body: "data/exchange is where files go out to an outside tool and come back.",
  },
  {
    id: "project-workflows-on-disk",
    title: "Workflows on disk",
    body: "Each workflow is one file in workflows/ — plain text you can read and share.",
  },
  {
    id: "project-your-own-code",
    title: "In your project",
    body: "The blocks, types, previewers and plots you write sit in folders of their own.",
  },
  {
    id: "project-user-guide",
    title: "The User Guide",
    body: "Stuck? Every project carries the user guide with it, in the user-guide folder.",
  },
  {
    id: "learning-center",
    title: "Learning Center",
    body: "The Learning Center in the toolbar holds the tutorials and the ideas behind SciStudio.",
  },
  {
    id: "preview-outputs",
    title: "See your outputs",
    body: "Select a block and the preview panel shows what came out of it.",
  },
  {
    id: "preview-per-type",
    title: "A view per type",
    body: "Each data type gets the viewer it deserves: tables paginate, arrays show as heatmaps.",
  },
  {
    id: "preview-custom",
    title: "Your own previewer",
    body: "You can write a previewer for your own data type, and the preview panel picks it up.",
  },
  {
    id: "plot-cards",
    title: "Plot cards",
    body: "A plot card ties a figure of your own to any block's output.",
  },
  {
    id: "plot-languages",
    title: "Plot in Python, R",
    body: "Write the figure as a Python or an R function — matplotlib, seaborn, ggplot2.",
  },
  {
    id: "plot-many-per-output",
    title: "One output, many plots",
    body: "Bind as many plot cards to the same output as you want to see.",
  },
  {
    id: "plot-relink",
    title: "Relink a plot",
    body: "Moved a block? Relink the plot card and it draws from the new output.",
  },
  {
    id: "plot-export-formats",
    title: "Take it to the paper",
    body: "A plot renders to svg, png, pdf or jpeg, ready to go into your figure.",
  },
  {
    id: "packages-what-they-are",
    title: "Packages",
    body: "A package brings a set of blocks for one field, ready to drop into a workflow.",
  },
  {
    id: "packages-manager",
    title: "The Packages button",
    body: "Packages in the toolbar installs, updates and rolls back what you have.",
  },
  {
    id: "packages-bring-types",
    title: "Inside a package",
    body: "A package can bring its data types and its viewers, along with its blocks.",
  },
  {
    id: "packages-share",
    title: "Share with your lab",
    body: "Blocks you wrote can be packaged up and installed by everyone in your lab.",
  },
  {
    id: "notes-on-canvas",
    title: "Note on the canvas",
    body: "Note in the toolbar drops a sticky note on the canvas, next to the step it explains.",
  },
  {
    id: "notes-markdown-file",
    title: "Keep a notebook",
    body: "New note starts a markdown file, for the thinking and findings you write as you go.",
  },
  {
    id: "history-keeps-runs",
    title: "Every run is kept",
    body: "The History tab records every run: the workflow it used and the settings it ran with.",
  },
  {
    id: "history-restore-run",
    title: "Restore your run",
    body: "Restore puts your project back the way it was at any run you have kept.",
  },
  {
    id: "git-commit-snapshot",
    title: "Take a snapshot",
    body: "Commit in the Git tab to keep a snapshot of your project you can return to.",
  },
  {
    id: "git-diff-versions",
    title: "See what changed",
    body: "The Git tab shows what changed between two versions of your work.",
  },
  {
    id: "git-branch-per-batch",
    title: "A branch per batch",
    body: "Two batches that need different settings? Give each its own branch in the Git tab.",
  },
];

function gcd(a: number, b: number): number {
  return b === 0 ? a : gcd(b, a % b);
}

/**
 * Step size the rotation walks the pool with.
 *
 * The pool is authored chapter by chapter, so walking it one entry at a time
 * would spend a whole session on plot cards and never mention the Git tab
 * (owner directive, #1997 — tips should come out mixed). Striding by a number
 * coprime with the pool length scatters consecutive tips across chapters while
 * still visiting every tip exactly once before any of them repeats, which is
 * what a per-step `Math.random()` would not give. The starting point near
 * `size * 0.618` is the golden-ratio choice: it spreads the walk evenly rather
 * than landing on a short cycle of nearby entries.
 */
const TIP_STRIDE: number = (() => {
  const size = PALETTE_TIPS.length;
  if (size < 3) {
    return 1;
  }
  let stride = Math.max(2, Math.round(size * 0.618));
  while (gcd(stride, size) !== 1) {
    stride += 1;
  }
  return stride;
})();

/**
 * The tip at rotation position `index`.
 *
 * `index` grows without bound as the rotation advances, so it is taken modulo
 * the pool before it is scaled by the stride — multiplying first would leave
 * the safe integer range after a long session. Returns `null` only for an
 * empty pool.
 */
export function resolveTip(index: number): PaletteTip | null {
  const size = PALETTE_TIPS.length;
  if (size === 0) {
    return null;
  }
  const start = ((index % size) + size) % size;
  return PALETTE_TIPS[(start * TIP_STRIDE) % size];
}
