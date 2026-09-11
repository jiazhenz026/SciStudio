"""Check Python documentation strings for internal development references.

The source is parsed without importing application modules. This includes
module, class, function, and attribute documentation, so future exports receive
the same protection as today's generated reference and OpenAPI descriptions.
"""

from __future__ import annotations

import ast
import re
import tokenize
from collections.abc import Iterator
from pathlib import Path

from scistudio.qa.schemas.report import AuditReport, AuditStatus, Finding, Severity

# The identifier families are defined in docs/contributing/docstring-style.md.
# Match internal records explicitly: external standards (UTF-8, RFC 3339,
# ISO-8601, SHA-256) and tooling identifiers (RUF001) remain valid content.
INTERNAL_MARKERS = re.compile(
    r"\b(?:ADR|FR|NFR|DSN|SC|OQ|ECA|OBS|BCP|AC|TRK|BUG|REQ|SPEC|PR)"
    r"(?:[-_\u2010-\u2014]|\s)+\d+[a-z0-9_-]*"
    r"|\bAddendum\s+\d+"
    r"|(?<![\w/])#\d+\b"
    r"|\b(?:TODO|FIXME|XXX)\b"
    r"|\b(?:dispatch\s+prompt|skeleton\s+agent|implementation\s+plan|test\s+plan)\b"
    r"|\b(?:ADR|spec|checklist)\s+§\s*\d+(?:\.\d+)*"
    r"|\b(?:[IS]\d{2}[a-z]|D\d{2}-\d+(?:\.\d+)*[a-z]?|T-\d{3})\b"
    r"|\b(?:Phase|Task)\s+\d+[a-z]?(?:\.\d+)*\b"
    r"|\bdocs/(?:adr|specs|planning|ai-developer)/[^\s`<>]+",
    re.IGNORECASE,
)


def iter_docstrings(tree: ast.AST) -> Iterator[tuple[str, ast.Constant]]:
    """Yield documentation literals with their qualified owner names.

    Assignment-following literals include class attributes and instance
    attributes documented in constructors. Additional consecutive docstrings
    are included too. Ordinary strings used by executable code are ignored.
    """

    def visit(node: ast.AST, owner: str) -> Iterator[tuple[str, ast.Constant]]:
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            owner = f"{owner}.{node.name}" if owner else node.name
        documentable = isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
        for _, body in ast.iter_fields(node):
            if not isinstance(body, list) or not body or not all(isinstance(item, ast.stmt) for item in body):
                continue
            previous_is_doc = False
            attribute = ""
            for index, statement in enumerate(body):
                if isinstance(statement, (ast.Assign, ast.AnnAssign)):
                    target = statement.targets[0] if isinstance(statement, ast.Assign) else statement.target
                    attribute = ast.unparse(target)
                elif isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Constant):
                    if isinstance(statement.value.value, str) and (
                        (documentable and index == 0) or attribute or previous_is_doc
                    ):
                        name = f"{owner}.{attribute}" if attribute and owner else attribute or owner or "<module>"
                        yield name, statement.value
                        previous_is_doc = True
                        continue
                    attribute = ""
                else:
                    attribute = ""
                previous_is_doc = False
        for child in ast.iter_child_nodes(node):
            yield from visit(child, owner)

    yield from visit(tree, "")


def check(repo_root: Path) -> AuditReport:
    """Report internal development language in package docstrings as errors.

    Scan every Python file under ``src/scistudio`` without depending on export
    lists or installed optional dependencies. A file that cannot be parsed or
    read is an error, since its documentation cannot be verified.
    """
    root = repo_root.resolve()
    findings: list[Finding] = []
    files = sorted((root / "src" / "scistudio").rglob("*.py"))
    count = 0
    for path in files:
        relative = path.relative_to(root).as_posix()
        try:
            with tokenize.open(path) as stream:
                source = stream.read()
            tree = ast.parse(source, filename=relative)
        except (OSError, UnicodeError, SyntaxError) as exc:
            findings.append(
                Finding(
                    rule_id="docstrings.unreadable-source",
                    severity=Severity.ERROR,
                    file=relative,
                    line=getattr(exc, "lineno", None) or 1,
                    message=f"Cannot check docstrings: {exc}",
                )
            )
            continue
        for owner, literal in iter_docstrings(tree):
            count += 1
            # Scan source spelling for physical lines, including escaped
            # newlines, then decoded text to catch escapes/concatenated literals.
            value = str(literal.value)
            markers = sorted({match.group() for match in INTERNAL_MARKERS.finditer(value)})
            if not markers:
                continue
            segment = ast.get_source_segment(source, literal) or value
            match = INTERNAL_MARKERS.search(segment)
            line = literal.lineno + (segment[: match.start()].count("\n") if match else 0)
            findings.append(
                Finding(
                    rule_id="docstrings.internal-language",
                    severity=Severity.ERROR,
                    file=relative,
                    line=line,
                    message=f"{owner}: internal development text {markers!r}; describe the behavior "
                    "and move maintainer references to ordinary # comments.",
                )
            )
    return AuditReport(
        tool="docstrings",
        status=AuditStatus.FAIL if findings else AuditStatus.PASS,
        source_sha="",
        findings=findings,
        summary={"files_checked": len(files), "docstrings_checked": count},
    )
