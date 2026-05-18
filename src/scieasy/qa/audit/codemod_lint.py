"""libCST codemod metadata lint (ADR-042 §20.3).

Every codemod under ``tools/codemods/adr-NNN-<slug>.py`` is required to
begin with a structured metadata docstring describing the contract change
(ADR ref + description + affected symbols + co-located tests). This
module parses that metadata and emits :class:`Finding` objects on
malformed / missing fields.

Two parsing entry points are exposed per the Phase 1 investigation
SUMMARY Q1B.9.1 manager default:

* :func:`parse` returns a plain ``dict[str, Any]`` (the §20.3 stub
  literal form) — useful for ad-hoc CLI inspection / JSON dumping.
* :func:`parse_model` returns a :class:`CodemodMeta` — the pydantic
  validated typed view used by audit-time consumers.

:func:`check` walks ``tools/codemods/`` and emits one finding per
malformed file plus structural findings (missing ADR ref, missing
``Tests:`` block when the codemod tests directory contains a matching
file, etc.).

References
----------
ADR-042 §20.1 — discipline statement.
ADR-042 §20.3 — metadata format (authoritative source).
ADR-042 §20.4 — CI verification pattern.
ADR-042 §9.6 — entry-point signature contract.

Deferred work
-------------
* The ``Affects:`` block's free-form "renamed to X" tail is parsed only
  structurally in v1; semantic verification that the renamed-target
  symbol exists in code is owned by :mod:`scieasy.qa.audit.doc_drift`
  (d-class).
* Adding ``scieasy.qa.codemods`` to ADR-042 ``governs.modules`` per
  Q1B.9.2 is deferred — closure currently exempts the codemods
  subpackage.

# TODO(#1154-ext): wire scieasy.qa.codemods governs.modules entry
#   Out of scope per Phase 1 investigation SUMMARY Q1B.9.2.
#   Followup: open as ADR-042 §27.4 errata after sub-PR 3 ships.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from scieasy.qa.schemas.codemod import CodemodMeta
from scieasy.qa.schemas.report import Finding, Severity

__all__ = ["check", "parse", "parse_model"]


# --------------------------------------------------------------------------- #
# Public entry points                                                         #
# --------------------------------------------------------------------------- #


def parse(codemod_path: Path) -> dict[str, Any]:
    """Parse a codemod file's metadata docstring header.

    Returns the parsed-but-not-validated dict view (per the §20.3 stub
    literal). Callers wanting a validated typed view should call
    :func:`parse_model` instead.

    Raises:
        ValueError: When the file has no module-level docstring, or the
            docstring is missing the ``ADR:`` / ``Description:`` keys.
    """
    return _parse_raw(codemod_path)


def parse_model(codemod_path: Path) -> CodemodMeta:
    """Parse + pydantic-validate a codemod file's metadata.

    Returns:
        :class:`CodemodMeta` — typed metadata.

    Raises:
        ValueError: On missing / malformed docstring (see :func:`parse`).
        pydantic.ValidationError: When the parsed dict violates the
            schema (e.g. ADR out of range, empty description).
    """
    raw = _parse_raw(codemod_path)
    return CodemodMeta.model_validate(raw)


def check(repo_root: Path | None = None) -> list[Finding]:
    """Walk ``tools/codemods/`` and emit lint findings.

    For every file matching ``tools/codemods/adr-*.py``:

    * Empty / missing metadata docstring → ``codemod-lint.missing-metadata``
      (ERROR).
    * Malformed ``ADR:`` / ``Description:`` field → ``codemod-lint.malformed-field``
      (ERROR).
    * pydantic ``ValidationError`` → ``codemod-lint.schema-violation`` (ERROR).
    * Empty ``Tests:`` block → ``codemod-lint.missing-tests`` (WARNING).
    * ``Tests:`` entry pointing at a non-existent path → ``codemod-lint.broken-test-ref``
      (WARNING).
    * Filename ADR slug disagrees with metadata ``ADR:`` field →
      ``codemod-lint.adr-ref-mismatch`` (WARNING).

    When ``tools/codemods/`` does not exist or contains no matching files,
    no findings are emitted (the directory is optional pre-Phase 2).
    """
    repo_root = repo_root or Path.cwd()
    codemods_dir = repo_root / "tools" / "codemods"
    findings: list[Finding] = []
    if not codemods_dir.is_dir():
        return findings

    for path in sorted(codemods_dir.glob("adr-*.py")):
        rel_path = path.relative_to(repo_root).as_posix()
        findings.extend(_lint_one(path, rel_path))
        # Cross-reference: declared tests must exist.
        try:
            meta = parse_model(path)
        except (ValueError, ValidationError):
            continue
        findings.extend(_check_filename_consistency(path, rel_path, meta))
        findings.extend(_check_test_refs(meta, rel_path, repo_root))
        if not meta.tests:
            findings.append(
                Finding(
                    rule_id="codemod-lint.missing-tests",
                    severity=Severity.WARNING,
                    file=rel_path,
                    message=(
                        "codemod declares no `Tests:` entries — every "
                        "codemod ships with an idempotency test per "
                        "ADR-042 §20.5."
                    ),
                )
            )
    return findings


# --------------------------------------------------------------------------- #
# Internal: docstring parser                                                  #
# --------------------------------------------------------------------------- #


# ``ADR: 42`` — int after colon (also tolerates ``ADR-042`` numeric tail).
_ADR_KEY_RE = re.compile(r"^ADR:\s*(?P<adr>\d+)\s*$", re.MULTILINE)
_DESCRIPTION_KEY_RE = re.compile(
    r"^Description:\s*(?P<description>.+?)\s*$",
    re.MULTILINE,
)
# Block headers introduce indented list items: ``Affects:\n  - foo``.
_AFFECTS_BLOCK_RE = re.compile(
    r"^Affects:\s*\n(?P<body>(?:\s+-\s+.+\n?)*)",
    re.MULTILINE,
)
_TESTS_BLOCK_RE = re.compile(
    r"^Tests:\s*\n(?P<body>(?:\s+-\s+.+\n?)*)",
    re.MULTILINE,
)
_LIST_ITEM_RE = re.compile(r"^\s+-\s+(?P<value>.+?)\s*$", re.MULTILINE)


def _parse_raw(codemod_path: Path) -> dict[str, Any]:
    """Extract the metadata docstring fields. Raises ``ValueError`` on errors."""
    if not codemod_path.is_file():
        raise ValueError(f"codemod file does not exist: {codemod_path}")

    text = codemod_path.read_text(encoding="utf-8")
    try:
        module = ast.parse(text)
    except SyntaxError as exc:
        raise ValueError(f"failed to parse {codemod_path}: {exc}") from exc

    docstring = ast.get_docstring(module, clean=False)
    if not docstring or not docstring.strip():
        raise ValueError(f"codemod {codemod_path} has no module-level docstring (ADR-042 §20.3 requires one)")

    adr_match = _ADR_KEY_RE.search(docstring)
    if adr_match is None:
        raise ValueError(f"codemod {codemod_path} docstring missing `ADR:` numeric field")

    description_match = _DESCRIPTION_KEY_RE.search(docstring)
    if description_match is None:
        raise ValueError(f"codemod {codemod_path} docstring missing `Description:` field")

    affects = _extract_list(_AFFECTS_BLOCK_RE, docstring)
    tests = _extract_list(_TESTS_BLOCK_RE, docstring)

    return {
        "adr": int(adr_match.group("adr")),
        "description": description_match.group("description"),
        "affects": affects,
        "tests": tests,
    }


def _extract_list(block_re: re.Pattern[str], docstring: str) -> list[str]:
    """Pull list items out of ``Header:\\n  - item\\n  - item`` blocks."""
    match = block_re.search(docstring)
    if match is None:
        return []
    body = match.group("body")
    return [m.group("value") for m in _LIST_ITEM_RE.finditer(body)]


# --------------------------------------------------------------------------- #
# Internal: per-file lint                                                     #
# --------------------------------------------------------------------------- #


def _lint_one(path: Path, rel_path: str) -> list[Finding]:
    """Run parse + schema validation; emit one finding per failure."""
    findings: list[Finding] = []
    try:
        raw = _parse_raw(path)
    except ValueError as exc:
        rule_id = (
            "codemod-lint.missing-metadata"
            if "no module-level docstring" in str(exc)
            else "codemod-lint.malformed-field"
        )
        findings.append(
            Finding(
                rule_id=rule_id,
                severity=Severity.ERROR,
                file=rel_path,
                message=str(exc),
            )
        )
        return findings

    try:
        CodemodMeta.model_validate(raw)
    except ValidationError as exc:
        for err in exc.errors():
            loc = ".".join(str(part) for part in err.get("loc", ()))
            findings.append(
                Finding(
                    rule_id="codemod-lint.schema-violation",
                    severity=Severity.ERROR,
                    file=rel_path,
                    message=f"{loc}: {err.get('msg', 'invalid value')}",
                )
            )
    return findings


# Filename pattern: ``adr-042-rename-foo-to-bar.py`` -> 42.
_FILENAME_ADR_RE = re.compile(r"^adr-(?P<adr>\d+)-")


def _check_filename_consistency(path: Path, rel_path: str, meta: CodemodMeta) -> list[Finding]:
    """Verify the filename's ``adr-NNN-`` prefix matches the metadata ``adr``."""
    match = _FILENAME_ADR_RE.match(path.name)
    if match is None:
        return [
            Finding(
                rule_id="codemod-lint.filename-format",
                severity=Severity.WARNING,
                file=rel_path,
                message=(
                    f"codemod filename {path.name!r} does not match `adr-NNN-<slug>.py` per ADR-042 §20.3 / §20.5."
                ),
            )
        ]
    filename_adr = int(match.group("adr"))
    if filename_adr != meta.adr:
        return [
            Finding(
                rule_id="codemod-lint.adr-ref-mismatch",
                severity=Severity.WARNING,
                file=rel_path,
                message=(f"filename declares ADR-{filename_adr:03d} but metadata says ADR: {meta.adr}"),
            )
        ]
    return []


def _check_test_refs(meta: CodemodMeta, rel_path: str, repo_root: Path) -> list[Finding]:
    """Verify every ``Tests:`` entry resolves to an existing file."""
    findings: list[Finding] = []
    for test_ref in meta.tests:
        if not (repo_root / test_ref).is_file():
            findings.append(
                Finding(
                    rule_id="codemod-lint.broken-test-ref",
                    severity=Severity.WARNING,
                    file=rel_path,
                    message=(f"declared test {test_ref!r} does not exist on disk"),
                )
            )
    return findings
