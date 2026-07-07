# Contributing to SciStudio

Thanks for your interest in SciStudio! Contributions of all kinds are welcome
while the project is in alpha — bug reports, feature ideas, documentation, and
code.

## Ways to contribute

- **Report a bug or request a feature** — open a [GitHub issue](https://github.com/jiazhenz026/SciStudio/issues).
  Include what you expected, what happened, and how to reproduce it.
- **Improve the docs** — the user-facing docs live in `src/scistudio/_user_guide/`
  and the developer docs in `docs/`.
- **Contribute code** — pick up an open issue and follow the workflow below.
- **Build blocks or packages** — to extend SciStudio without changing the core,
  follow the [Package Development guide](https://jiazhenz026.github.io/SciStudio/package-development/index.html).
  Packages live in their own repositories and are not part of this repo's gate
  workflow.

## Development setup

```bash
git clone https://github.com/jiazhenz026/SciStudio.git
cd SciStudio

# Python backend (use a conda env or a virtualenv)
python -m pip install ".[dev]"

# Frontend dependencies
npm --prefix frontend install

# Run the desktop app against your source (Vite HMR + backend + Electron)
npm --prefix desktop run dev
```

Install the commit hooks once:

```bash
pip install pre-commit
pre-commit install --hook-type pre-commit --hook-type commit-msg
```

## Opening a pull request

1. **Start from an open issue.** Every PR must close one; don't open a new issue
   when an existing one already tracks the work.
2. **Branch from `main`** with a descriptive name. Never push directly to `main`.
3. **Use [Conventional Commits](https://www.conventionalcommits.org/)** —
   `feat(core): ...`, `fix(storage): ...`, `docs: ...`. Types: `feat`, `fix`,
   `docs`, `refactor`, `test`, `ci`, `chore`.
4. **Tests and docs are part of the change.** Add or update tests when behavior
   changes; update the docs (or note why none are needed).
5. **Open the PR against `main`**, fill in the template, and link the issue.
   CI must pass and a review is required before merge.

The full development workflow and branch/traceability rules are documented in
[`AGENTS.md`](AGENTS.md).

## AI-assisted development

SciStudio is built to be friendly to AI-assisted development — much of it is
written with coding agents, and the repo ships the rules, personas, and a gated
workflow they follow. If you use an AI agent (Claude Code, Codex, and the like)
to work on SciStudio, point it at:

- [`AGENTS.md`](AGENTS.md) — the root behavior guide and required rules.
- [`docs/ai-developer/rules.md`](docs/ai-developer/rules.md) — the rules every AI
  persona must follow, including the gated workflow and the gate CLI.

Agents read and follow these automatically (including the local gate checks), so
as a human contributor you don't need to run the gate yourself.

## Community

- [Discord](https://discord.gg/5b7kTRU2k)
