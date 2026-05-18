# ADR-042 to ADR-044 Tool Reality Audit

Date: 2026-05-18
Mode: review
Scope: `docs/adr/ADR-042.md`, `docs/adr/ADR-043.md`, `docs/adr/ADR-044.md`
Audit question: wrong tool usage and points that are not achievable in
practice.

## Scope Correction

This audit treats ADR-042, ADR-043, and ADR-044 as new Draft ADRs. Missing
implementation files, missing `tests/qa/**`, missing workflows, and missing
future docs directories are not findings by themselves. Those are expected
while the ADRs are still design artifacts.

The only valid findings here are:

- A proposed mechanism uses a tool incorrectly.
- A proposed hard gate depends on a platform capability that does not exist.
- Two proposed mechanisms contradict each other.
- A proposed mandatory check is too broad to be objectively enforced.
- A snippet is presented as executable/config-ready but is not valid for the
  referenced tool.

## Source Documents Checked

Primary or closest-available tool documentation:

- Sphinx `extensions` config:
  https://www.sphinx-doc.org/en/master/usage/configuration.html#confval-extensions
- Sphinx built-in extensions:
  https://www.sphinx-doc.org/en/master/usage/extensions/index.html
- Sphinx builders / `linkcheck` builder:
  https://www.sphinx-doc.org/en/master/usage/builders/index.html
- Sphinx AutoAPI extension example:
  https://sphinx-autoapi.readthedocs.io/en/stable/reference/directives.html
- autodoc-pydantic installation / extension name:
  https://autodoc-pydantic.readthedocs.io/en/main-1.x/users/installation.html
- sphinx-substitution-extensions package docs:
  https://pypi.org/project/sphinx-substitution-extensions/
- pytest-examples package docs:
  https://pypi.org/project/pytest-examples/
- Claude Code hooks reference:
  https://docs.anthropic.com/en/docs/claude-code/hooks
- GitHub branch protection:
  https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches
- GitHub CODEOWNERS:
  https://docs.github.com/articles/about-code-owners
- GitHub `GITHUB_TOKEN` behavior:
  https://docs.github.com/en/actions/concepts/security/github_token
- GitHub token permissions in workflows:
  https://docs.github.com/en/actions/how-tos/writing-workflows/choosing-what-your-workflow-does/controlling-permissions-for-github_token
- Hypothesis property-based testing guidance:
  https://hypothesis.readthedocs.io/en/latest/tutorial/introduction.html
- mutmut package docs:
  https://pypi.org/project/mutmut/

## Executive Summary

The ADR direction is viable, but several parts should not be accepted as hard
requirements without revision.

Critical corrections:

- Do not claim deterministic cross-runtime hook parity. Claude Code hooks are
  documented, but the same hook lifecycle is not a universal agent runtime
  contract, and `InstructionsLoaded` is not in the Claude hook reference.
- Do not make local pre-commit responsible for proving GitHub PR approval. That
  is a PR/CI/GitHub App concern.
- Do not use direct pushes from docs/translation bots if the repo policy is
  PR-only and branch protection is meant to be authoritative.
- Do not claim all ADR fenced code is executable while keeping pseudocode in
  executable fences.
- Fix Sphinx extension names before any docs-build implementation.
- Soften absolute test-quality claims: property tests, mutation testing, and
  commit-order analysis are useful, but cannot automatically prove all the
  semantics ADR-043 assigns to them.

## Findings

### P0.1 Cross-Runtime Hook Parity Is Overclaimed

ADR claims:

- ADR-042 says every supported AI runtime must receive identical discipline,
  and no hook/provisioning may be implemented for one runtime and deferred for
  others.
- ADR-043 defines rule carriers including `PreToolUse`, `PostToolUse`,
  `UserPromptSubmit`, `Stop`, and `InstructionsLoaded`.
- ADR-044 Appendix A says Codex hook parity reverses an ADR-040 deferral.

Tool reality:

- Claude Code documents hooks such as `PreToolUse`, `PostToolUse`,
  `Notification`, `UserPromptSubmit`, `Stop`, `SubagentStop`, `PreCompact`,
  `SessionStart`, and `SessionEnd`.
- The Claude hook reference does not list `InstructionsLoaded`.
- Claude hook names and matcher behavior are not a cross-runtime standard for
  Codex, Cursor, Aider, and Gemini.

Why this matters:

The ADRs use hooks as deterministic enforcement. That is only valid inside a
runtime that actually supports the specific lifecycle event. It is not valid as
a universal repo guarantee.

Required fix:

- Replace "identical hooks across runtimes" with "identical merge-time
  enforcement across runtimes."
- Move hard guarantees to Git hooks, CI, branch protection, workflow-gate
  validators, and server-side/runtime validation.
- Treat per-agent hooks as best-effort local guardrails.
- Remove `InstructionsLoaded`, or map it to a documented event such as
  `SessionStart` if that is the intended behavior.

### P0.2 Direct-Push Docs/Translation Bots Conflict With PR-Only Governance

ADR claims:

- ADR-042 proposes `docs-agent.yml` that runs after CI on `main`, edits docs,
  commits, and pushes.
- ADR-042 proposes `translation.yml` that auto-generates `docs/zh-CN/**`,
  commits, and pushes.

Tool reality:

- GitHub branch protection can require pull requests, reviews, status checks,
  and restrict direct pushes to protected branches.
- GitHub documents that workflow pushes made with the repository
  `GITHUB_TOKEN` do not trigger normal workflow runs, except for selected
  manual/repository dispatch events.
- `GITHUB_TOKEN` write permissions must be explicitly granted with
  `permissions: contents: write` or equivalent.

Why this matters:

If branch protection is configured to require PRs, these bots either fail to
push or require an explicit bypass. If they bypass, they contradict the ADR's
own governance posture. Also, pushes made with `GITHUB_TOKEN` will not
naturally re-run the normal push-triggered audit cascade.

Additional snippet issue:

The proposed snippets use `git diff --name-only HEAD~1` after scripts modify
the working tree. That compares committed history, not necessarily the current
uncommitted edits. The snippets also use `git commit -am`, which will not add
new translation files.

Required fix:

- Make docs-agent and translation jobs create PRs instead of pushing to `main`.
- Use explicit path guards over working-tree, staged, and untracked files:
  `git diff --name-only`, `git diff --cached --name-only`, and
  `git ls-files --others --exclude-standard`.
- Use explicit `git add -- <allowed paths>` after guard validation.
- Let the generated PR pass the same required checks as any other PR.

### P0.3 Local Governance Hooks Cannot Prove PR Approval

ADR claim:

- ADR-043 says `governance_mod_guard.py` runs before commit and, for agent
  commits, verifies through the GitHub API that a Tier-2 handle approved the PR.

Tool reality:

- Pre-commit runs before a commit exists and often before a PR exists.
- Local hooks do not reliably know the PR number, have a GitHub token, or have
  access to current remote review state.
- CODEOWNERS and required review are PR/branch-protection mechanisms, not
  local filesystem facts.

Why this matters:

The proposed local hook is assigned a remote authorization responsibility it
cannot reliably fulfill.

Required fix:

- Local hook: validate staged governance paths, reject missing approval
  trailers, and print remediation instructions.
- CI/GitHub App: verify the trailer against real PR reviews, CODEOWNERS, and
  branch-protection state.
- Keep authority separation explicit: local hooks enforce local facts; CI
  enforces remote PR facts.

### P0.4 `pytest-examples` Is Overclaimed Against Current ADR Prose

ADR claim:

- ADR-042 states that all fenced code blocks in the main ADR body are
  executable and that pseudocode has been moved to a companion file.

Tool reality:

- `pytest-examples` is documented as a plugin for testing Python examples in
  docstrings and Markdown files.
- ADR-042 through ADR-044 contain many Python fences that are design sketches:
  ellipses, omitted imports, `raise NotImplementedError`, placeholder return
  values, shell snippets with placeholders, YAML workflow sketches, and
  incomplete class bodies.

Why this matters:

The tool can run examples, but only examples that are intentionally runnable or
explicitly skipped. The ADR currently treats many explanatory design snippets
as if they were executable examples.

Required fix:

- Use `text` fences for pseudocode and illustrative snippets.
- Add explicit skip markers for any non-executable example if the project keeps
  `pytest-examples`.
- Reserve `python` fences for examples that can run in isolation in the docs
  test environment.

### P1.1 Sphinx Extension Names Are Wrong in ADR-044

ADR claim:

- ADR-044 section 10.4 lists Sphinx extensions including
  `"sphinx_autoapi"`, `"autodoc_pydantic"`, and `"sphinx.ext.linkcheck"`.

Tool reality:

- Sphinx `extensions` entries are Python module names.
- Sphinx AutoAPI's docs enable it as `autoapi.extension`.
- autodoc-pydantic's docs enable it as `sphinxcontrib.autodoc_pydantic`.
- `linkcheck` is a Sphinx builder selected with `sphinx-build -b linkcheck`,
  not a built-in extension named `sphinx.ext.linkcheck`.
- `sphinx_substitution_extensions` is the correct module name for
  sphinx-substitution-extensions.

Required fix:

Use this corrected shape:

```python
extensions = [
    "autoapi.extension",
    "myst_parser",
    "sphinx_needs",
    "sphinx_substitution_extensions",
    "sphinx.ext.intersphinx",
    "sphinx.ext.autodoc",
    "sphinx.ext.autosummary",
    "sphinx.ext.doctest",
    "sphinx.ext.linkcode",
    "sphinx.ext.viewcode",
    "sphinx.ext.graphviz",
    "sphinx_click",
    "sphinxcontrib.openapi",
    "sphinxcontrib.autodoc_pydantic",
    "sphinx_gallery.gen_gallery",
    "sphinx_design",
    "sphinx_copybutton",
    "sphinx_issues",
    "sphinxext.opengraph",
    "scieasy_directives",
    "llms_txt_builder",
]
```

Keep link checking as a command:

```bash
sphinx-build -b linkcheck docs/sphinx _build/linkcheck
```

### P1.2 Docs-Build Snippets Are Not Copy-Paste Runnable

ADR claims:

- ADR-043 and ADR-044 provide GitHub workflow sketches that run
  `python -m scieasy...` and `sphinx-build`.

Tool reality:

- The snippets omit Python setup, dependency installation, and editable
  installation of the project.
- This is acceptable if the snippets are illustrative, but not if ADR-044
  presents them as the workflow body to implement.

Required fix:

- Label these as pseudocode, or include complete setup:
  `actions/setup-python`, `uv`/pip install, docs/QA extras, and package install.
- Add a dedicated dependency group, for example `.[docs,qa]`, before the
  workflow is made normative.

### P1.3 `llms.txt` Generation Order Is Contradictory

ADR claim:

- ADR-044 says `llms_txt.generate` walks the rendered Sphinx ToC.
- The same ADR runs `llms_txt.generate` before `sphinx-build`.

Tool reality:

- A rendered Sphinx ToC does not exist until after Sphinx builds, unless the
  generator reads source toctrees rather than rendered output.

Required fix:

- Either run `llms_txt.generate` after the HTML build, or change the ADR to say
  it walks source toctrees before build.

### P1.4 Test-Quality Gates Are Too Absolute

ADR claims:

- Every new public function must have at least one Hypothesis `@given`
  property test.
- `test_first_check.py` should verify that tests were committed before the
  implementation and failed at the parent commit.
- Mutation score gates should apply by package and for new code.

Tool reality:

- Hypothesis documentation frames property-based testing as a powerful addition
  to unit testing, not always a replacement. It recommends looking for
  properties such as round trips, equivalence, invariants, and crash freedom.
- Some public functions are side-effectful wrappers, CLI entry points,
  subprocess launchers, external-app integration, GUI bridges, or orchestration
  glue. A meaningful property test may not exist for each one.
- Commit-order verification is heuristic: behavior tests often cover multiple
  functions, and a test name does not reliably map to one production symbol.
- Running tests at historical parent commits is slow and must happen in an
  isolated checkout.
- mutmut is useful, but its docs note operational constraints, including a
  fork-support requirement and WSL for Windows use.

Required fix:

- Require property tests for pure transforms, schemas, parsers, serializers,
  and deterministic invariants.
- Require issue-linked justification when a public function has no property
  test target.
- Make test-first verification report-only at first, then enforce only for PRs
  explicitly marked TDD-required.
- Scope mutation testing to CI/Linux initially; document Windows/WSL limits.

### P1.5 "Every Public Function Must Have User-Facing Docs" Is Too Broad

ADR claim:

- ADR-044 extends class-d drift to every public class/function/CLI command/HTTP
  endpoint/entry point missing from some user-doc reference page.

Tool reality:

- Sphinx AutoAPI can generate API references, but generated API reference is
  not the same thing as user-facing conceptual documentation.
- Enforcing every public function as user-facing documentation encourages
  symbol dumping and noisy docs.

Required fix:

- Split coverage into two categories:
  `api_reference_coverage` for generated API pages and
  `user_workflow_coverage` for curated user docs.
- Hard-require user-facing docs for stable public contracts: block classes,
  CLI commands, HTTP endpoints, plugin contracts, data object contracts, and
  externally documented workflows.
- Let helper functions appear only in generated API reference unless exported
  as a supported public API.

### P2.1 Two-Page "Rendered Line" Enforcement Is Not Deterministic

ADR claim:

- ADR-044 caps docs at two letter pages, described as roughly 120 rendered
  lines, and says the linter counts after Markdown rendering.

Tool reality:

- Rendered line count depends on theme, viewport width, font metrics, tables,
  admonitions, code wrapping, and output format.

Required fix:

- Enforce source-based measures: non-empty source lines, word count, or Sphinx
  doctree node count.
- Keep "two letter pages" as editorial guidance, not a blocking machine rule.

### P2.2 Non-ASCII Rejection Is Too Broad for Scientific Docs

ADR claim:

- ADR-042 says CI rejects non-ASCII outside fenced code under `docs/`, except
  `docs/zh-CN/**`.

Tool reality:

- Scientific documentation often legitimately needs Unicode units, symbols,
  Greek letters, names, arrows in formulas, and international references.
- The repository already contains non-ASCII prose and generated artifacts.

Required fix:

- Enforce "source prose is English" rather than raw ASCII.
- If a machine rule is needed, use an allowlist for scientific symbols and
  typographic characters, or make the check report-only during cleanup.

### P2.3 Codex Skill Paths Need One Canonical Table

ADR claims:

- ADR-042 lists Codex skill install location as `~/.codex/skills/<name>/`.
- ADR-044 Appendix A describes project-scoped embedded-agent skills under
  `<project>/.agents/skills/<name>/SKILL.md` and a project
  `<project>/.codex/config.toml`.

Reality:

- This may be a difference between user-global and project-local installs, but
  the ADRs do not say that clearly.
- Without one canonical table, future provisioning agents will implement
  different layouts.

Required fix:

Add a single runtime-path table with these columns:

- Runtime
- Source tree in SciEasy repo
- Project-local install path
- User-global install path, if any
- Discovery limitation, if any
- Governing ADR/issue

## Non-Findings

The following are not defects in this audit:

- `src/scieasy/qa/**` does not exist yet.
- `scripts/audit/**` does not exist yet.
- `tests/qa/**` does not exist yet.
- `docs/contributing/**`, `docs/user/**`, `docs/prod-agent/**`, and
  `docs/doc-guide/**` do not exist yet.
- ADR-042/043/044 frontmatter lists planned governed files and tests.

Those are implementation-scope questions for later phase audits, not
tool-reality findings against new Draft ADRs.

## Required Changes Before Acceptance

1. Rewrite hook parity language so only CI/GitHub/gate/runtime validation are
   hard guarantees; runtime-specific hooks are advisory.
2. Replace direct-push docs/translation workflows with PR-producing workflows.
3. Move PR approval verification out of local pre-commit and into CI/GitHub
   App checks.
4. Correct Sphinx extension names and linkcheck usage.
5. Mark pseudocode as non-executable or explicitly skipped for
   `pytest-examples`.
6. Clarify `llms.txt` generation source: rendered ToC after build or source
   toctree before build.
7. Re-scope test-quality gates to enforce objective checks and report
   heuristic checks until the false-positive rate is known.
8. Replace rendered-line doc length enforcement with deterministic source
   metrics.
9. Replace raw non-ASCII rejection with an English-source policy plus a
   scientific Unicode allowlist if needed.

## Acceptance Recommendation

Do not accept ADR-042 to ADR-044 unchanged. The ADRs are acceptable as Draft
design direction, but the P0/P1 items above must be corrected before they
become binding governance. The implementation absence of new QA files should
not block these ADRs; the blocking issue is tool-contract accuracy and
enforceability of the proposed rules.
