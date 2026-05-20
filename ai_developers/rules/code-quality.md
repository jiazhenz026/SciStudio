# Code Quality

## 1. Decision Summary

Use the repository's existing quality checks for the files touched by a task.

Python checks:

- `ruff check .`
- `ruff format --check .`
- Targeted `pytest` for changed behavior.
- `mypy src/scieasy/ --ignore-missing-imports` or the configured type command
  when the touched area requires it.

Documentation checks:

- Run available frontmatter or documentation lint tools when editing governed
  docs.
- Run Sphinx or focused docs checks when changing generated docs, user docs, or
  architecture docs.

Frontend checks:

- Use `eslint`, `prettier`, `tsc --noEmit`, `vitest`, and `vite build` when
  editing frontend code.

Security and workflow checks:

- Use dependency, workflow, and security checks when changing dependencies,
  GitHub Actions, pre-commit config, packaging, or release automation.

Test quality:

- Prefer behavior tests over implementation-shape tests.
- Do not skip tests without a tracked reason.
- Do not mock away the behavior under test unless that is the contract being
  verified.
