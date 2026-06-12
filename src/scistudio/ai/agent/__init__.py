"""AI agent runtime package (terminal session, system prompt, MCP wiring).

This subpackage hosts the agent-side runtime that the AI block (``scistudio.
blocks.ai.ai_block``) drives: ``terminal`` (PTY/agent session helpers),
``system_prompt`` (prompt assembly), and ``mcp`` (MCP server/tool wiring).

Issue #1591: this package was previously missing its ``__init__.py``, so
``[tool.setuptools.packages.find]`` (regular, non-namespace discovery) silently
dropped it from the built wheel, and import-linter / grimp could not see
``scistudio.ai.agent.*`` modules in the import graph (so the
``blocks.ai.ai_block -> ai.agent.terminal`` boundary crossing went unchecked).
Making it a regular package fixes both: the wheel ships the agent runtime and
the architecture contracts observe the real edge (carved out explicitly in
``pyproject.toml``).
"""
