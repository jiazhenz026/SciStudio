<div align="center">

<img src="desktop/assets/icon.png" alt="SciStudio" width="120" />

# SciStudio

**Scientific data workbench with your AI partner.**

[![Status: alpha](https://img.shields.io/badge/status-alpha-orange.svg)]()
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-green.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![CI](https://github.com/jiazhenz026/SciStudio/actions/workflows/ci.yml/badge.svg)](https://github.com/jiazhenz026/SciStudio/actions/workflows/ci.yml)
[![Docs](https://img.shields.io/badge/docs-online-blue.svg)](https://jiazhenz026.github.io/SciStudio/)
[![Discord](https://img.shields.io/badge/Discord-join-5865F2.svg?logo=discord&logoColor=white)](https://discord.gg/KGJfkM6EQN)

**English** | [简体中文](README.zh-CN.md)

</div>

---

<div align="center">

<!-- Drop the home-page workflow canvas screenshot at docs/assets/scistudio-canvas.png -->
<img src="docs/assets/scistudio-canvas.png" alt="SciStudio workflow canvas" width="820" />

</div>

## What is SciStudio?

SciStudio is an interactive workbench for multimodal scientific data analysis.
It is a shared space where you and your AI partner work on your data together:
explore it interactively, turn what works into reproducible workflows, and keep
using the tools you already trust.

- **Explore with MiniApps** — ask your AI partner for an interactive app on your
  data, and try analyses while the next step is still open.
- **Reproduce with workflows** — settled steps become a typed workflow you can
  rerun, reuse, and trace back.
- **Bring your tools** — R and Python scripts and desktop apps like Fiji run as
  blocks in the flow.
- **Your AI, your way** — work with an AI coding agent inside SciStudio, or from
  your AI app through WebMCP.
- **Grows with you** — add blocks, data types, panels, MiniApps, and plots, and
  share them as packages.

## Install and use

### For users

Download and install the SciStudio desktop app from the
[**Releases page**](https://github.com/jiazhenz026/SciStudio/releases).
Python and the required runtime dependencies are bundled.

When you launch SciStudio, choose how you want to use it:

- **Desktop**: Work in the SciStudio desktop window.
- **External AI**: Choose this mode to use SciStudio inside an AI desktop app
  with WebMCP support, such as ChatGPT or Kimi **(Claude is not currently
  supported)**. Once the service is ready, click **Copy** in the connection
  window and open the copied address in the AI app's built-in browser to work
  with your AI partner. Keep SciStudio running in the background while you work.

See the [**User Guide**](https://jiazhenz026.github.io/SciStudio/user-guide/)
for detailed instructions.

### For servers

```bash
pip install scistudio
```

The wheel bundles the web frontend. Every desktop update is also a PyPI release
of the same build: `0.3.4-alpha-build0029` is `scistudio==0.3.4a29`. Once a
stable release exists, add `--pre` to get the newest alpha.

### For developers (run from source)

```bash
git clone https://github.com/jiazhenz026/SciStudio.git
cd SciStudio

# Python backend (use a conda env or a virtualenv)
python -m pip install ".[dev]"

# Frontend dependencies
npm --prefix frontend install

# Run the desktop app against your source:
# Vite HMR for the frontend + the SciStudio backend + Electron.
npm --prefix desktop run dev
```

Frontend edits hot-reload; restart the command to pick up backend changes. See
[`desktop/README.md`](desktop/README.md) for packaging the app (`.dmg` /
Windows installer).

## Documentation

Full documentation lives at **[jiazhenz026.github.io/SciStudio](https://jiazhenz026.github.io/SciStudio/)**:

- [**User Guide**](https://jiazhenz026.github.io/SciStudio/user-guide/)
  — building and running workflows, previewing data, history and branches, the
  AI assistant, and writing your own blocks, types, and plots.
- [**Quickstart**](https://jiazhenz026.github.io/SciStudio/user-guide/getting-started.html)
  — from a fresh install to your first running workflow.
- [**API Reference**](https://jiazhenz026.github.io/SciStudio/user-guide/api-reference/index.html)
  — the public API you can rely on, with signatures and stability tiers.
- [**Package Development**](https://jiazhenz026.github.io/SciStudio/package-development/index.html)
  — building a distributable SciStudio package (blocks, types, previewers).
- [**Architecture**](docs/architecture/ARCHITECTURE.md) — how SciStudio is built
  and why.

The User Guide and API Reference are the same docs SciStudio provisions into each
project, so what you read online matches what ships with the app.

## Contributing

Contributions are welcome — bug reports, feature ideas, docs, and code. Start by
reading [**CONTRIBUTING.md**](CONTRIBUTING.md), and see [`AGENTS.md`](AGENTS.md)
for the full development workflow (branch, issue, gate, tests, docs, review).

To build and ship your own blocks (rather than change the core), follow the
[Package Development guide](https://jiazhenz026.github.io/SciStudio/package-development/index.html).

## Community

Questions, feedback, and bug reports are very welcome while SciStudio is in alpha:

- [Discord](https://discord.gg/KGJfkM6EQN)
- [GitHub Issues](https://github.com/jiazhenz026/SciStudio/issues)

## Status

SciStudio is in **alpha** and under active development. Interfaces and APIs may
change between releases; the [API Reference](https://jiazhenz026.github.io/SciStudio/user-guide/api-reference/index.html)
marks the stability tier of each public symbol.

## License

SciStudio is released under the Apache License 2.0. See [LICENSE](LICENSE) for
the full text.
