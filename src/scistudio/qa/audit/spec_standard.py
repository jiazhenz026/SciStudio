"""Structural validation for specs written to the revision-2 standard."""
# Development references: ADR-042 document standards 3.7.

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from scistudio.qa.audit._util import normalise_path
from scistudio.qa.schemas.frontmatter import SpecFrontmatter
from scistudio.qa.schemas.report import Finding, Severity

# ADR-042 3.7.2. The ten headings, in this order, and no other H2.
SECTIONS: tuple[str, ...] = (
    "1. Change Summary",
    "2. User Stories",
    "3. Functional Requirements",
    "4. New Modules",
    "5. Changed Modules",
    "6. Removed Modules",
    "7. Migration",
    "8. Public API Changes",
    "9. Documentation Changes",
    "10. Impact Surface",
)

# ADR-042 3.7.3 to 3.7.8. Header row per tabled section, in order.
COLUMNS: dict[str, tuple[str, ...]] = {
    "3. Functional Requirements": ("FR", "Name", "Behavior", "ADR decision"),
    "4. New Modules": ("ID", "FR", "Module"),
    "5. Changed Modules": ("ID", "FR", "Action", "Module"),
    "6. Removed Modules": ("ID", "FR", "Replaced by", "Module"),
    "7. Migration": ("ID", "FR", "From", "To", "Carrier"),
    "8. Public API Changes": ("ID", "FR", "Surface", "Change", "Compatibility"),
    "9. Documentation Changes": ("ID", "FR", "Document", "Change"),
    "10. Impact Surface": ("Path", "IDs", "Action"),
}

PREFIXES: dict[str, str] = {
    "3. Functional Requirements": "FR",
    "4. New Modules": "NEW",
    "5. Changed Modules": "CHANGE",
    "6. Removed Modules": "DEL",
    "7. Migration": "MIG",
    "8. Public API Changes": "API",
    "9. Documentation Changes": "DOC",
}

MODULE_SECTIONS: tuple[str, ...] = ("4. New Modules", "5. Changed Modules", "6. Removed Modules")

CHANGE_ACTIONS = frozenset({"modify", "verify"})
IMPACT_ACTIONS = frozenset({"create", "modify", "delete", "verify"})

_H2_RE = re.compile(r"^##\s+(.+?)\s*$")
_H3_RE = re.compile(r"^###\s+(.+?)\s*$")
_ID_RE = re.compile(r"^(FR|NEW|CHANGE|DEL|MIG|API|DOC)-(\d{3})$")
_SECTION_REF_RE = re.compile(r"\bSections?\s+(\d+(?:\.\d+)*)", re.IGNORECASE)


@dataclass(frozen=True)
class _Row:
    cells: tuple[str, ...]
    line: int


@dataclass(frozen=True)
class _Section:
    title: str
    line: int
    header: tuple[str, ...]
    rows: tuple[_Row, ...]
    subsections: tuple[tuple[str, int], ...]


def _finding(path: Path, rule: str, message: str, *, line: int | None = None) -> Finding:
    return Finding(
        rule_id=f"spec-standard.{rule}",
        severity=Severity.ERROR,
        file=normalise_path(path),
        line=line,
        message=message,
    )


def _split_row(raw: str) -> tuple[str, ...]:
    return tuple(cell.strip() for cell in raw.strip().strip("|").split("|"))


def _is_divider(raw: str) -> bool:
    return bool(re.fullmatch(r"\|(?:\s*:?-{3,}:?\s*\|)+", raw.strip()))


@dataclass
class _Builder:
    title: str
    line: int
    header: tuple[str, ...] = ()
    rows: list[_Row] = field(default_factory=list)
    subsections: list[tuple[str, int]] = field(default_factory=list)
    seen_h3: bool = False

    def freeze(self) -> _Section:
        return _Section(
            title=self.title,
            line=self.line,
            header=self.header,
            rows=tuple(self.rows),
            subsections=tuple(self.subsections),
        )


def _parse(body: str) -> list[_Section]:
    """Split the body into H2 sections, each with its opening table and its H3s."""

    sections: list[_Section] = []
    current: _Builder | None = None

    for number, raw in enumerate(body.split("\n"), start=1):
        h2 = _H2_RE.match(raw)
        if h2:
            if current is not None:
                sections.append(current.freeze())
            current = _Builder(title=h2.group(1), line=number)
            continue
        if current is None:
            continue
        h3 = _H3_RE.match(raw)
        if h3:
            current.seen_h3 = True
            current.subsections.append((h3.group(1), number))
            continue
        if current.seen_h3 or not raw.startswith("|") or _is_divider(raw):
            continue
        cells = _split_row(raw)
        if not current.header:
            current.header = cells
        else:
            current.rows.append(_Row(cells=cells, line=number))

    if current is not None:
        sections.append(current.freeze())
    return sections


def _check_sections(path: Path, sections: list[_Section]) -> list[Finding]:
    titles = [section.title for section in sections]
    if titles == list(SECTIONS):
        return []
    findings: list[Finding] = []
    for expected, actual in zip(SECTIONS, titles, strict=False):
        if expected != actual:
            line = next((s.line for s in sections if s.title == actual), None)
            findings.append(_finding(path, "sections", f"expected H2 '## {expected}', found '## {actual}'", line=line))
            break
    extra = [title for title in titles if title not in SECTIONS]
    findings.extend(
        _finding(
            path, "sections", f"unexpected H2 '## {title}'", line=next(s.line for s in sections if s.title == title)
        )
        for title in extra
    )
    missing = [title for title in SECTIONS if title not in titles]
    findings.extend(_finding(path, "sections", f"missing H2 '## {title}'", line=1) for title in missing)
    return findings


def _check_tables(path: Path, by_title: dict[str, _Section]) -> list[Finding]:
    findings: list[Finding] = []
    for title, expected in COLUMNS.items():
        section = by_title.get(title)
        if section is None:
            continue
        if not section.header:
            findings.append(_finding(path, "tables", f"'## {title}' must open with a table", line=section.line))
        elif section.header != expected:
            findings.append(
                _finding(
                    path,
                    "tables",
                    f"'## {title}' table header must be {list(expected)}, found {list(section.header)}",
                    line=section.line + 2,
                )
            )
    return findings


def _ids(section: _Section | None) -> list[tuple[str, _Row]]:
    if section is None:
        return []
    return [(row.cells[0], row) for row in section.rows if row.cells and _ID_RE.match(row.cells[0])]


def _check_numbering(path: Path, by_title: dict[str, _Section]) -> list[Finding]:
    findings: list[Finding] = []
    for title, prefix in PREFIXES.items():
        section = by_title.get(title)
        if section is None:
            continue
        found = _ids(section)
        # 3.7.6 allows the single row API-000 when no public surface changes.
        if prefix == "API" and len(found) == 1 and found[0][0] == "API-000":
            continue
        seen: set[str] = set()
        for position, (identifier, row) in enumerate(found, start=1):
            match = _ID_RE.match(identifier)
            assert match is not None
            if match.group(1) != prefix:
                findings.append(
                    _finding(
                        path,
                        "numbering",
                        f"'## {title}' row must use the {prefix}- prefix, found {identifier}",
                        line=row.line,
                    )
                )
                continue
            if identifier in seen:
                findings.append(_finding(path, "numbering", f"duplicate id {identifier}", line=row.line))
                continue
            seen.add(identifier)
            if int(match.group(2)) != position:
                findings.append(
                    _finding(
                        path,
                        "numbering",
                        f"ids must run contiguously from {prefix}-001; expected {prefix}-{position:03d}, found {identifier}",
                        line=row.line,
                    )
                )
        if len(section.rows) != len(found):
            findings.append(
                _finding(path, "numbering", f"'## {title}' has a row whose first cell is not an id", line=section.line)
            )
    return findings


def _referenced_ids(cell: str) -> list[str]:
    return [token for token in re.split(r"[,\s]+", cell) if _ID_RE.match(token)]


def _check_requirement_links(path: Path, by_title: dict[str, _Section]) -> list[Finding]:
    known = {identifier for identifier, _ in _ids(by_title.get("3. Functional Requirements"))}
    findings: list[Finding] = []
    for title in (
        "4. New Modules",
        "5. Changed Modules",
        "6. Removed Modules",
        "7. Migration",
        "8. Public API Changes",
        "9. Documentation Changes",
    ):
        section = by_title.get(title)
        if section is None or not section.header:
            continue
        try:
            column = section.header.index("FR")
        except ValueError:
            continue
        for row in section.rows:
            if column >= len(row.cells):
                continue
            cell = row.cells[column]
            if cell in {"", "—", "-", "None"}:
                continue
            referenced = _referenced_ids(cell)
            if not referenced:
                findings.append(_finding(path, "requirement-links", f"'{cell}' names no requirement", line=row.line))
            findings.extend(
                _finding(path, "requirement-links", f"{identifier} is not defined in Section 3", line=row.line)
                for identifier in referenced
                if identifier not in known
            )
    return findings


def _check_carrier_links(path: Path, by_title: dict[str, _Section]) -> list[Finding]:
    known = {identifier for section in by_title.values() for identifier, _ in _ids(section)}
    findings: list[Finding] = []
    for title, column_name in (("6. Removed Modules", "Replaced by"), ("7. Migration", "Carrier")):
        section = by_title.get(title)
        if section is None or not section.header or column_name not in section.header:
            continue
        column = section.header.index(column_name)
        for row in section.rows:
            if column >= len(row.cells):
                continue
            cell = row.cells[column]
            if cell == "None":
                continue
            referenced = _referenced_ids(cell)
            if not referenced:
                findings.append(
                    _finding(
                        path,
                        "carrier-links",
                        f"'{column_name}' must name an id or 'None', found '{cell}'",
                        line=row.line,
                    )
                )
            findings.extend(
                _finding(path, "carrier-links", f"{identifier} is not defined in this spec", line=row.line)
                for identifier in referenced
                if identifier not in known
            )
    return findings


def _module_column(section: _Section) -> int | None:
    for name in ("Module", "Document", "Path"):
        if name in section.header:
            return section.header.index(name)
    return None


def _check_detail_subsections(path: Path, by_title: dict[str, _Section]) -> list[Finding]:
    findings: list[Finding] = []
    for title in MODULE_SECTIONS:
        section = by_title.get(title)
        if section is None or not section.header:
            continue
        column = _module_column(section)
        if column is None:
            continue
        expected = [f"{identifier} {row.cells[column]}" for identifier, row in _ids(section) if column < len(row.cells)]
        actual = [heading for heading, _ in section.subsections]
        if expected == actual:
            continue
        for index, want in enumerate(expected):
            have = actual[index] if index < len(actual) else None
            if have == want:
                continue
            line = section.subsections[index][1] if index < len(section.subsections) else section.line
            findings.append(
                _finding(
                    path,
                    "detail-subsections",
                    f"'## {title}' expects H3 '### {want}' in table order, found {'### ' + have if have else 'nothing'}",
                    line=line,
                )
            )
            break
        for extra in actual[len(expected) :]:
            line = next(number for heading, number in section.subsections if heading == extra)
            findings.append(_finding(path, "detail-subsections", f"H3 '### {extra}' has no table row", line=line))
    return findings


def _check_paths(path: Path, by_title: dict[str, _Section]) -> list[Finding]:
    findings: list[Finding] = []
    for title in (*MODULE_SECTIONS, "9. Documentation Changes", "10. Impact Surface"):
        section = by_title.get(title)
        if section is None or not section.header:
            continue
        column = _module_column(section)
        if column is None:
            continue
        for row in section.rows:
            if column >= len(row.cells):
                continue
            value = row.cells[column]
            if not value or value.startswith("/") or value.startswith("~") or ":" in value or value.startswith(".."):
                findings.append(_finding(path, "paths", f"'{value}' must be a repository-relative path", line=row.line))
    return findings


def _check_action_values(path: Path, by_title: dict[str, _Section]) -> list[Finding]:
    findings: list[Finding] = []
    for title, allowed in (("5. Changed Modules", CHANGE_ACTIONS), ("10. Impact Surface", IMPACT_ACTIONS)):
        section = by_title.get(title)
        if section is None or not section.header or "Action" not in section.header:
            continue
        column = section.header.index("Action")
        for row in section.rows:
            if column < len(row.cells) and row.cells[column] not in allowed:
                findings.append(
                    _finding(
                        path,
                        "action-values",
                        f"'{row.cells[column]}' is not one of {sorted(allowed)}",
                        line=row.line,
                    )
                )
    return findings


def _declared_surface(by_title: dict[str, _Section]) -> dict[str, str]:
    """Path to action, from Sections 4, 5, 6 and 9."""

    surface: dict[str, str] = {}
    for title, default in (
        ("4. New Modules", "create"),
        ("5. Changed Modules", None),
        ("6. Removed Modules", "delete"),
        ("9. Documentation Changes", "modify"),
    ):
        section = by_title.get(title)
        if section is None or not section.header:
            continue
        column = _module_column(section)
        if column is None:
            continue
        action_column = section.header.index("Action") if "Action" in section.header else None
        for row in section.rows:
            if column >= len(row.cells):
                continue
            action = default
            if action_column is not None and action_column < len(row.cells):
                action = row.cells[action_column]
            if action is not None:
                surface[row.cells[column]] = action
    return surface


def _check_impact_surface(path: Path, by_title: dict[str, _Section]) -> list[Finding]:
    section = by_title.get("10. Impact Surface")
    if section is None or not section.header or "Path" not in section.header:
        return []
    declared = _declared_surface(by_title)
    listed = {
        row.cells[0]: (
            row.cells[section.header.index("Action")] if section.header.index("Action") < len(row.cells) else ""
        )
        for row in section.rows
        if row.cells
    }
    lines = {row.cells[0]: row.line for row in section.rows if row.cells}
    findings: list[Finding] = []
    findings.extend(
        _finding(
            path, "impact-surface", f"'{item}' is listed in Section 10 but in no earlier section", line=lines[item]
        )
        for item in sorted(set(listed) - set(declared))
    )
    findings.extend(
        _finding(
            path,
            "impact-surface",
            f"'{item}' is named in an earlier section but missing from Section 10",
            line=section.line,
        )
        for item in sorted(set(declared) - set(listed))
    )
    findings.extend(
        _finding(
            path,
            "impact-surface",
            f"'{item}' is '{listed[item]}' in Section 10 but '{declared[item]}' earlier",
            line=lines[item],
        )
        for item in sorted(set(declared) & set(listed))
        if listed[item] != declared[item] and not (declared[item] == "modify" and listed[item] == "create")
    )
    return findings


def _check_governed_scope(path: Path, frontmatter: SpecFrontmatter, by_title: dict[str, _Section]) -> list[Finding]:
    section = by_title.get("10. Impact Surface")
    if section is None or not section.header or "Path" not in section.header:
        return []
    governed = set(frontmatter.governs.files) | set(frontmatter.planned_governs.files)
    return [
        _finding(
            path,
            "governed-scope",
            f"'{row.cells[0]}' is in Section 10 but in neither governs.files nor planned_governs.files",
            line=row.line,
        )
        for row in section.rows
        if row.cells and row.cells[0] not in governed
    ]


def _check_adr_links(
    path: Path, frontmatter: SpecFrontmatter, by_title: dict[str, _Section], repo_root: Path
) -> list[Finding]:
    """Every 'ADR decision' value names a section that exists in a related ADR.

    Skipped when no related ADR file is present; this checks the spec against its
    own inputs, never against an implementation.
    """

    section = by_title.get("3. Functional Requirements")
    if section is None or not section.header or "ADR decision" not in section.header:
        return []
    available: set[str] = set()
    found_any = False
    for number in frontmatter.related_adrs:
        adr_path = repo_root / "docs" / "adr" / f"ADR-{number:03d}.md"
        if not adr_path.is_file():
            continue
        found_any = True
        for raw in adr_path.read_text(encoding="utf-8").split("\n"):
            heading = re.match(r"^#{2,6}\s+(\d+(?:\.\d+)*)\.?\s", raw)
            if heading:
                available.add(heading.group(1))
    if not found_any:
        return []
    column = section.header.index("ADR decision")
    findings: list[Finding] = []
    for row in section.rows:
        if column >= len(row.cells):
            continue
        referenced = _SECTION_REF_RE.findall(row.cells[column])
        if not referenced:
            findings.append(_finding(path, "adr-links", f"'{row.cells[column]}' names no ADR section", line=row.line))
        findings.extend(
            _finding(path, "adr-links", f"Section {number} does not exist in the related ADRs", line=row.line)
            for number in referenced
            if number not in available
        )
    return findings


def check_spec(path: Path, frontmatter: SpecFrontmatter, body: str, *, repo_root: Path | None = None) -> list[Finding]:
    """Validate the structure of a spec written to the revision-2 standard.

    Structure only: these checks never read the source tree and never judge
    whether an implementation followed the spec.
    """

    if frontmatter.spec_standard != 2:
        return []
    root = Path(repo_root or Path.cwd())
    sections = _parse(body)
    findings = _check_sections(path, sections)
    by_title = {section.title: section for section in sections}
    findings += _check_tables(path, by_title)
    findings += _check_numbering(path, by_title)
    findings += _check_requirement_links(path, by_title)
    findings += _check_carrier_links(path, by_title)
    findings += _check_detail_subsections(path, by_title)
    findings += _check_paths(path, by_title)
    findings += _check_action_values(path, by_title)
    findings += _check_impact_surface(path, by_title)
    findings += _check_governed_scope(path, frontmatter, by_title)
    findings += _check_adr_links(path, frontmatter, by_title, root)
    return findings
