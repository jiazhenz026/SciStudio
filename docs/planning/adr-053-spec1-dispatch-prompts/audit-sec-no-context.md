[DISPATCH-TEMPLATE-V1: audit-no-context]

## Task Identity

- Repository: SciStudio
- Persona: audit_reviewer
- Audit mode: no-context
- Audit branch: audit/adr-053-spec1-write-path
- Audit worktree: C:/Users/jiazh/workspace/SciStudio-wt-audit-sec
- Allowed audit surfaces:
  - `src/scistudio/api/routes/` — every filesystem-write endpoint
  - `src/scistudio/core/dropins.py` and everything that computes drop-in directories or `sys.path` roots
  - `src/scistudio/blocks/registry/` — drop-in module loading
  - `src/scistudio/core/types/` — type registry and drop-in type loading
  - `src/scistudio/ai/agent/mcp/` — tools that write to disk
  - `docs/architecture/ARCHITECTURE.md`, `docs/architecture/sentrux-rules.md`
  - Tests covering the above
- Audit report path: docs/audit/2026-08-07-adr-053-spec1-write-path.md

## Context Limits

You must not read or use:

- Any current owner request.
- Any GitHub issue.
- Any manager checklist file (in particular anything under `docs/planning/`).
- Any dispatch prompt other than this one.
- PR descriptions, PR comments, or commit messages for the current work.
- Chat summaries or manager summaries of what changed.

You may read only:

- Repository docs.
- Repository code.
- Tests.
- Generated facts or audit outputs already committed in the repository.
- Tool output from commands you run yourself.

Do not try to infer "what the manager intended". Judge the tree as it stands.

## Required Reading

- AGENTS.md
- docs/ai-developer/rules.md
- docs/ai-developer/personas/audit-reviewer.md
- Governing ADRs, specs, and docs you discover from the allowed audit surfaces.

## Audit Goal

Independently determine whether the repository's **filesystem-write surfaces** and its
**`sys.path` manipulation** are safe and match what the governing documents claim.

This is an adversarial review, not a conformance checklist. Assume a user's project
directory and a user's home library directory can contain hostile or accidental content.

Concretely, answer these questions from the code:

1. **Every endpoint that writes a file to disk** — enumerate them. For each: what constrains
   the resolved target path, and can that constraint be defeated?
   - Path traversal (`..`, encoded variants, nested).
   - Symlink escape — is the path resolved to a real path *before* the containment check, or
     after? Is the check a string prefix comparison or a real path-relationship test?
   - Absolute paths, UNC paths, drive-relative paths, and differing drive letters. **This
     project runs on Windows**; a POSIX-only containment check is a real defect here.
   - Case sensitivity and trailing-separator edge cases.
   - File type — can a caller write something other than a `.py` file, or write into a
     nested subdirectory of the intended root?
   - Overwrite — can an existing file be destroyed without an explicit caller opt-in?
2. **Do any two write endpoints have inconsistent constraints?** If one endpoint confines
   writes to a project root and another confines them elsewhere, does adding the second
   weaken the first — for example by sharing a helper that now accepts a wider set of paths?
3. **`sys.path` manipulation during drop-in module execution** — which directories are
   prepended, for how long, and in which processes? Is the mutation restored on every exit
   path including exceptions? Is it safe under concurrency?
4. **Module shadowing** — a user-writable directory participating in module resolution can
   shadow an installed third-party or standard-library module for anything imported
   afterwards. Does the code detect that? Does it warn, block, or ignore it? Is the detection
   itself sound, or can a legitimate file be mistaken for a collision, or a real collision be
   missed?
5. **Failure handling** — can one hostile or broken drop-in file crash a scan, hang it, or
   prevent unrelated blocks and types from loading?
6. **Cross-process consistency** — do all processes that load drop-in code agree on which
   directories they trust? A directory trusted in one process and not another is a
   correctness and a security problem.
7. **Docs vs. code** — do `ARCHITECTURE.md`, the Sentrux rules, and any spec under
   `docs/specs/` describe these surfaces accurately? Flag docs that claim behaviour the code
   does not implement, and code behaviour no governing doc covers.
8. **Tests** — is each containment rule actually covered by a test that would fail if the
   rule were removed? A test that only exercises the happy path does not cover a containment
   rule.

Also look for the standard no-context findings: public signatures or schemas that drift from
docs, ADR/spec `governs` paths that do not exist, and generated docs edited by hand.

## Coordination

- MUST work only on your assigned audit branch, in your assigned audit worktree.
- MUST NOT use `pip install -e .`. Use `PYTHONPATH=./src`.
- MUST NOT merge any PR.
- MUST NOT edit implementation files.
- MUST NOT edit any file under `docs/planning/`.
- MUST write the audit report to the repository file named above.
- Windows note: a post-commit hook fails with `ExecutableNotFoundError: Executable /bin/sh not found`. The commit still lands; verify with `git log`.

## Checks

Run or verify:

- `PYTHONPATH=./src python -m pytest tests/api tests/blocks tests/core -q`
- Write your own probe scripts against the write endpoints and the drop-in loader. Actually
  attempt the escapes rather than reasoning about them — a traversal you executed is
  evidence; a traversal you reasoned about is a hypothesis. Do this in a scratch directory,
  never against real user data.
- The repository's import-linter command.
- Sentrux MCP if available; otherwise `sentrux scan .` and `sentrux check .`, or record the
  unavailability explicitly. Do not claim Pro-only diagnostics.
- `python -m scistudio.qa.governance.gate_record check --mode pre-pr` to confirm gate ledger
  reconciliation for your audit branch.

## Output Required

- Audit report path.
- Commit that contains the audit report file.
- The complete enumeration of filesystem-write endpoints and their containment rules.
- Findings ordered by severity (P1 blocks, P2 should fix, P3 follow-up), each with evidence:
  the probe you ran and its actual output, or the exact code path.
- For every escape you attempted: what you tried and whether it was rejected.
- No statement about anyone's intent unless it is visible in repository docs.
- Recommendation: pass, pass-with-fixes, or block.

## Stop Conditions

Stop and report back if:

- You are asked to read issue, checklist, or PR context.
- The audit requires hidden context to make sense.
- You need to edit implementation code.
- A probe you run would affect data outside a scratch directory.
