"""spec_audit — SciEasy interface SSOT auditor.

Four extractors + one diff produce a three-way report comparing:
  1. Code-side interface surface (Python ABCs, Pydantic, FastAPI, Typer, entry-points)
  2. SSOT-side spec entries (docs/specs/INTERFACE_SPEC.md, fixed grammar)
  3. Docs-side mentions (ARCHITECTURE.md, ADR/*.md, CLAUDE.md)

Output: build/spec-audit/diff-report.md plus build/spec-audit/{code,spec,docs}.json
Exit 0 if clean, 2 on drift. See scripts/hooks/check-spec-drift.sh for CI wiring.

Status: V1 MVP. Coverage caveats — see TODOs in extract_code.py for surfaces
NOT yet covered (MCP tools, WS message types). These require running-server
introspection (MCP) or richer AST inference (WS) than fits the V1 scope;
they will land as follow-up PRs once the SSOT freezes.

Plan: ~/.claude/plans/single-source-of-truth-issue-issue-acce-wiggly-truffle.md
Umbrella issue: #1090.
"""

__version__ = "0.1.0"
