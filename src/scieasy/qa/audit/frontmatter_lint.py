"""Per-file YAML frontmatter validation (ADR-042 §5, ADR-044 §5.6).

:func:`lint_file` parses a markdown file's YAML frontmatter and validates
it against the schema appropriate for the file's location/kind:

* ``docs/adr/ADR-*.md`` → :class:`ADRFrontmatter`
* ``docs/spec/SPEC-*.md`` → :class:`SpecFrontmatter`
* ``docs/contributing/workflows/*.md`` → :class:`WorkflowDocFrontmatter`
* ``docs/user/**/*.md`` → :class:`UserDocFrontmatter`
* ``docs/prod/agent/**/*.md`` → :class:`ProdAgentDocFrontmatter`
* ``docs/guides/**/*.md`` → :class:`DocGuideFrontmatter`
* any other ``docs/contributing/**/*.md`` → permissive fall-through
  (per Phase 1 investigation default Q1B.2.2).

Returns a list of :class:`~scieasy.qa.schemas.report.Finding`
objects. Each Pydantic ValidationError becomes one Finding. The empty
return value means "no validation errors".

References
----------
ADR-042 §5 — ADR frontmatter schema.
ADR-042 §5.6 — supersession automation (the lint surface).
ADR-042 §9.6 — entry-point signature (return type :py:class:`list[Finding]`).
ADR-044 §5.6 — multi-schema dispatch for docs/.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ValidationError

from scieasy.qa.docs.schemas import (
    DocGuideFrontmatter,
    ProdAgentDocFrontmatter,
    UserDocFrontmatter,
    WorkflowDocFrontmatter,
)
from scieasy.qa.schemas.frontmatter import ADRFrontmatter, SpecFrontmatter
from scieasy.qa.schemas.report import Finding, Severity

__all__ = ["lint_file", "select_schema"]


def lint_file(path: Path, repo_root: Path | None = None) -> list[Finding]:
    """Validate a single doc's YAML frontmatter against its schema.

    Args:
        path: Repo-relative or absolute path to a Markdown file.
        repo_root: Optional repo root for computing the path category.
            When ``None``, the parent of ``path`` is used (which works
            fine for the ADR / spec cases, where the path category
            comes from the filename itself).

    Returns:
        List of findings. Empty when the frontmatter is valid (or when
        the file legitimately has no frontmatter, e.g. a stray README).
    """
    findings: list[Finding] = []
    if not path.is_file():
        return [
            Finding(
                rule_id="frontmatter-lint.missing-file",
                severity=Severity.ERROR,
                file=str(path),
                message=f"file does not exist: {path}",
            )
        ]

    text = path.read_text(encoding="utf-8")
    block, frontmatter_line = _extract_frontmatter_block(text)
    if block is None:
        # Files in docs/ that legitimately carry no frontmatter (e.g.
        # the consolidated cascade dump, archive snapshots) are out of
        # scope for this lint. We surface an info-level finding only
        # when the file's location DOES require frontmatter.
        if _requires_frontmatter(path, repo_root):
            findings.append(
                Finding(
                    rule_id="frontmatter-lint.missing-frontmatter",
                    severity=Severity.ERROR,
                    file=str(path),
                    message=(
                        "file is in a frontmatter-required location but has "
                        "no YAML frontmatter block (expected '---' delimiters "
                        "at the top of the file)"
                    ),
                )
            )
        return findings

    try:
        data = yaml.safe_load(block)
    except yaml.YAMLError as exc:
        findings.append(
            Finding(
                rule_id="frontmatter-lint.yaml-parse",
                severity=Severity.ERROR,
                file=str(path),
                line=frontmatter_line,
                message=f"YAML parse error in frontmatter: {exc}",
            )
        )
        return findings

    if not isinstance(data, dict):
        findings.append(
            Finding(
                rule_id="frontmatter-lint.non-mapping",
                severity=Severity.ERROR,
                file=str(path),
                line=frontmatter_line,
                message=(f"frontmatter must be a YAML mapping (got {type(data).__name__})"),
            )
        )
        return findings

    schema_cls = select_schema(path, repo_root)
    if schema_cls is None:
        # Permissive fall-through (Q1B.2.2): emit no error.
        return findings

    try:
        schema_cls.model_validate(data)
    except ValidationError as exc:
        for err in exc.errors():
            findings.append(
                Finding(
                    rule_id=f"frontmatter-lint.{schema_cls.__name__}.{err['type']}",
                    severity=Severity.ERROR,
                    file=str(path),
                    line=None,  # line numbers require ruamel.yaml SourceMap; deferred per Q1B.2.2 note
                    message=_format_validation_error(err),
                )
            )
    return findings


# ---------------------------------------------------------------------------
# Schema selection
# ---------------------------------------------------------------------------


def select_schema(path: Path, repo_root: Path | None = None) -> type[BaseModel] | None:
    """Pick the pydantic schema appropriate for ``path``.

    Returns ``None`` for files in the permissive fall-through bucket
    (e.g. ``docs/contributing/onboarding.md``) — those validate any
    frontmatter shape.
    """
    rel = _rel_path(path, repo_root)
    parts = rel.replace("\\", "/").split("/")

    name = parts[-1] if parts else ""

    # ADRs and specs are identified by filename prefix anywhere under docs/.
    if name.startswith("ADR-") and name.endswith(".md") and "_template" not in parts:
        # The template files contain pseudo-frontmatter that intentionally
        # does not validate — exempt them.
        return ADRFrontmatter
    if name.startswith("SPEC-") and name.endswith(".md") and "_template" not in parts:
        return SpecFrontmatter

    # Directory-based dispatch for non-ADR/spec docs.
    if "docs" in parts:
        idx = parts.index("docs")
        sub = parts[idx + 1 :]
        if not sub:
            return None
        if sub[0] == "contributing" and len(sub) > 1 and sub[1] == "workflows":
            return WorkflowDocFrontmatter
        if sub[0] == "user":
            return UserDocFrontmatter
        if sub[0] == "prod" and len(sub) > 1 and sub[1] == "agent":
            return ProdAgentDocFrontmatter
        if sub[0] == "guides":
            return DocGuideFrontmatter

    return None  # permissive fall-through (Q1B.2.2)


def _requires_frontmatter(path: Path, repo_root: Path | None) -> bool:
    """Whether ``path``'s location MUST carry a frontmatter block."""
    return select_schema(path, repo_root) is not None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _rel_path(path: Path, repo_root: Path | None) -> str:
    if repo_root is not None:
        try:
            return str(path.relative_to(repo_root))
        except ValueError:
            pass
    return str(path)


def _extract_frontmatter_block(text: str) -> tuple[str | None, int]:
    """Return the YAML block between ``---`` fences plus its first line."""
    if not text.startswith("---"):
        return None, 0
    end = text.find("\n---", 3)
    if end == -1:
        return None, 0
    block = text[3:end].strip("\n")
    return block, 2  # frontmatter content starts at line 2 (line 1 is "---")


def _format_validation_error(err: Any) -> str:
    """Render a pydantic ValidationError entry into a one-line message."""
    raw_loc = err.get("loc", ()) or ()
    if not isinstance(raw_loc, tuple | list):
        raw_loc = ()
    loc = ".".join(str(p) for p in raw_loc if p is not None)
    msg = err.get("msg", "")
    if loc:
        return f"{loc}: {msg}"
    return str(msg)
