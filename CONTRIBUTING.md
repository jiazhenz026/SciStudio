# Contributing

## Setup

```bash
pip install pre-commit
pre-commit install --hook-type pre-commit --hook-type commit-msg
pip install ruff mypy pytest import-linter
```

## Workflow

1. Open or find an issue before starting work.
2. Branch from `main` using a descriptive name.
3. Use [Conventional Commits](https://www.conventionalcommits.org/) — e.g., `feat(core): ...`, `fix(storage): ...`.
4. Run checks before pushing:
   ```bash
   ruff check . && ruff format --check .
   mypy src/scistudio/ --ignore-missing-imports
   pytest
   ```
5. Open a PR against `main`, fill in the template, and link the issue.

## Commit Message Format

```
type(scope): short description

Optional body explaining why.
```

Types: `feat`, `fix`, `docs`, `refactor`, `test`, `ci`, `chore`.

## Code Review

All changes require PR review before merging. See `CLAUDE.md` for full project standards.
