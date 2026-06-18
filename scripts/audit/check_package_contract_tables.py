"""Check ADR-049 package-validator contract tables against code and ADRs.

The checker has two jobs:

1. Extract a mechanical inventory of package-extension interfaces from the
   repository code (`--dump-inventory`). Agents use this inventory as their
   starting point so contract tables are anchored in code instead of memory.
2. Validate each JSON contract row. Code evidence mismatches are errors because
   the table no longer matches implementation. ADR evidence mismatches are
   warnings because ADRs may lag the implementation.

The script intentionally uses only the Python standard library so agents can run
it in fresh worktrees without installing test dependencies.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import tomllib
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "adr049.package_contract_table.v1"
DEFAULT_CONTRACT_DIR = Path("docs/planning/adr-049-package-validator/contracts")

SECTION_ALIASES = {
    "01": "01_package_metadata_distribution",
    "02": "02_entry_points",
    "03": "03_type_contracts",
    "04": "04_block_contracts",
    "05": "05_config_dynamic_variadic",
    "06": "06_io_format_capability",
    "07": "07_data_transport_runtime_boundary",
    "08": "08_app_code_block_boundaries",
    "09": "09_previewer_contracts",
    "10": "10_preview_provider_behavior",
    "11": "11_plot_jobs",
    "12": "12_security_isolation",
    "13": "13_cross_surface_registry_consistency",
    "99": "99_omitted_or_discovered_contracts",
}
VALID_SECTIONS = set(SECTION_ALIASES.values())

BLOCK_BASE_NAMES = {
    "Block",
    "ProcessBlock",
    "IOBlock",
    "CodeBlock",
    "AppBlock",
    "AIBlock",
    "SubWorkflowBlock",
}
TYPE_BASE_NAMES = {
    "DataObject",
    "Array",
    "Series",
    "DataFrame",
    "Text",
    "Artifact",
    "CompositeData",
}
PUBLIC_CONTRACT_SYMBOLS = {
    "PackageInfo": "01_package_metadata_distribution",
    "BlockTestHarness": "04_block_contracts",
    "TypeRegistry": "03_type_contracts",
    "BlockRegistry": "13_cross_surface_registry_consistency",
    "BlockSpec": "13_cross_surface_registry_consistency",
    "FormatCapability": "06_io_format_capability",
    "MetadataFidelity": "06_io_format_capability",
    "PreviewerRegistry": "09_previewer_contracts",
    "PreviewRouter": "09_previewer_contracts",
    "PreviewerSpec": "09_previewer_contracts",
    "FrontendManifest": "09_previewer_contracts",
    "PreviewDataAccess": "10_preview_provider_behavior",
}
VALIDATOR_FUNCTIONS = {
    "_validate_meta_class": "03_type_contracts",
    "validate_entry_point_callable": "02_entry_points",
    "validate_block": "04_block_contracts",
    "validate_package_info": "01_package_metadata_distribution",
    "smoke_test": "07_data_transport_runtime_boundary",
    "_validate_dynamic_ports": "05_config_dynamic_variadic",
    "_validate_capability_registration": "06_io_format_capability",
    "_validate_class_capability": "06_io_format_capability",
    "_format_capabilities_from_class": "06_io_format_capability",
    "list_format_capabilities": "06_io_format_capability",
    "find_loader_capability": "06_io_format_capability",
    "find_saver_capability": "06_io_format_capability",
    "validate_codeblock_config": "08_app_code_block_boundaries",
    "validate_workflow": "08_app_code_block_boundaries",
    "validate_manifest": "09_previewer_contracts",
    "resolve_asset": "09_previewer_contracts",
    "is_remote_url": "12_security_isolation",
    "load_packages": "13_cross_surface_registry_consistency",
    "_scan_entry_points": "13_cross_surface_registry_consistency",
    "_scan_entrypoint_types": "13_cross_surface_registry_consistency",
    "_scan_tier2": "13_cross_surface_registry_consistency",
}


@dataclass(frozen=True)
class InventoryItem:
    section: str
    kind: str
    path: str
    line: int
    symbol: str
    required: bool
    reason: str


@dataclass
class Diagnostic:
    level: str
    table: str
    contract_id: str
    message: str


def relpath(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def ast_name(node: ast.AST | None) -> str:
    if node is None:
        return ""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = ast_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    if isinstance(node, ast.Subscript):
        return ast_name(node.value)
    if isinstance(node, ast.Call):
        return ast_name(node.func)
    if isinstance(node, ast.Constant):
        return str(node.value)
    return ""


def assigned_names(stmt: ast.stmt) -> set[str]:
    names: set[str] = set()
    if isinstance(stmt, ast.Assign):
        targets = stmt.targets
    elif isinstance(stmt, ast.AnnAssign):
        targets = [stmt.target]
    else:
        return names
    for target in targets:
        if isinstance(target, ast.Name):
            names.add(target.id)
        elif isinstance(target, ast.Attribute):
            names.add(target.attr)
    return names


def add_item(
    items: list[InventoryItem],
    *,
    section: str,
    kind: str,
    path: str,
    line: int,
    symbol: str,
    required: bool,
    reason: str,
) -> None:
    if section not in VALID_SECTIONS:
        raise ValueError(f"unknown inventory section: {section}")
    items.append(
        InventoryItem(
            section=section,
            kind=kind,
            path=path,
            line=line,
            symbol=symbol,
            required=required,
            reason=reason,
        )
    )


def parse_py_file(path: Path, root: Path, items: list[InventoryItem]) -> None:
    rel = relpath(path, root)
    try:
        text = path.read_text(encoding="utf-8")
        tree = ast.parse(text, filename=rel)
    except (OSError, SyntaxError, UnicodeDecodeError):
        return

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            base_names = {ast_name(base).split(".")[-1] for base in node.bases}
            if node.name in PUBLIC_CONTRACT_SYMBOLS:
                add_item(
                    items,
                    section=PUBLIC_CONTRACT_SYMBOLS[node.name],
                    kind="public_contract_class",
                    path=rel,
                    line=node.lineno,
                    symbol=node.name,
                    required=True,
                    reason="public class forms part of package validator contract surface",
                )
            if base_names & TYPE_BASE_NAMES and node.name not in TYPE_BASE_NAMES:
                add_item(
                    items,
                    section="03_type_contracts",
                    kind="type_class",
                    path=rel,
                    line=node.lineno,
                    symbol=node.name,
                    required=False,
                    reason="DataObject subtype candidate discovered from class bases",
                )
            if base_names & BLOCK_BASE_NAMES and node.name not in BLOCK_BASE_NAMES:
                block_section = "04_block_contracts"
                if "IOBlock" in base_names:
                    block_section = "06_io_format_capability"
                elif {"CodeBlock", "AppBlock"} & base_names:
                    block_section = "08_app_code_block_boundaries"
                add_item(
                    items,
                    section=block_section,
                    kind="block_class",
                    path=rel,
                    line=node.lineno,
                    symbol=node.name,
                    required=False,
                    reason="Block subtype candidate discovered from class bases",
                )
            for stmt in node.body:
                names = assigned_names(stmt)
                for name in sorted(names & {"config_schema", "dynamic_ports"}):
                    add_item(
                        items,
                        section="05_config_dynamic_variadic",
                        kind=f"classvar_{name}",
                        path=rel,
                        line=getattr(stmt, "lineno", node.lineno),
                        symbol=f"{node.name}.{name}",
                        required=False,
                        reason=f"{name} participates in package validator contract",
                    )
                if names & {
                    "variadic_inputs",
                    "variadic_outputs",
                    "min_input_ports",
                    "max_input_ports",
                    "min_output_ports",
                    "max_output_ports",
                }:
                    add_item(
                        items,
                        section="05_config_dynamic_variadic",
                        kind="classvar_variadic_port_contract",
                        path=rel,
                        line=getattr(stmt, "lineno", node.lineno),
                        symbol=node.name,
                        required=False,
                        reason="variadic port declarations participate in package validator contract",
                    )
                if "format_capabilities" in names or "supported_extensions" in names:
                    add_item(
                        items,
                        section="06_io_format_capability",
                        kind="classvar_io_capability_contract",
                        path=rel,
                        line=getattr(stmt, "lineno", node.lineno),
                        symbol=node.name,
                        required=False,
                        reason="IO capability declarations participate in package validator contract",
                    )
        elif isinstance(node, ast.FunctionDef):
            if node.name in VALIDATOR_FUNCTIONS:
                add_item(
                    items,
                    section=VALIDATOR_FUNCTIONS[node.name],
                    kind="validator_function",
                    path=rel,
                    line=node.lineno,
                    symbol=node.name,
                    required=True,
                    reason="validator or registry function that encodes package contract behavior",
                )
            if node.name in {"get_blocks", "get_block_package", "get_types", "get_previewers"}:
                section = "02_entry_points"
                if node.name == "get_types":
                    section = "03_type_contracts"
                elif node.name == "get_previewers":
                    section = "09_previewer_contracts"
                add_item(
                    items,
                    section=section,
                    kind="entry_point_factory",
                    path=rel,
                    line=node.lineno,
                    symbol=node.name,
                    required=True,
                    reason="package entry-point factory discovered in code",
                )
            if node.name in {"run", "load", "save", "setup", "teardown", "process_item", "get_format_capabilities"}:
                section = "04_block_contracts"
                if node.name in {"load", "save", "get_format_capabilities"}:
                    section = "06_io_format_capability"
                add_item(
                    items,
                    section=section,
                    kind="block_hook",
                    path=rel,
                    line=node.lineno,
                    symbol=node.name,
                    required=False,
                    reason="block hook signature candidate",
                )
        elif isinstance(node, ast.Call):
            call_name = ast_name(node.func).split(".")[-1]
            if call_name == "FormatCapability":
                add_item(
                    items,
                    section="06_io_format_capability",
                    kind="format_capability_call",
                    path=rel,
                    line=node.lineno,
                    symbol="FormatCapability",
                    required=False,
                    reason="concrete FormatCapability declaration",
                )
            elif call_name == "PreviewerSpec":
                add_item(
                    items,
                    section="09_previewer_contracts",
                    kind="previewer_spec_call",
                    path=rel,
                    line=node.lineno,
                    symbol="PreviewerSpec",
                    required=False,
                    reason="concrete PreviewerSpec declaration",
                )
            elif call_name == "FrontendManifest":
                add_item(
                    items,
                    section="09_previewer_contracts",
                    kind="frontend_manifest_call",
                    path=rel,
                    line=node.lineno,
                    symbol="FrontendManifest",
                    required=False,
                    reason="frontend preview manifest declaration",
                )


def parse_pyproject(path: Path, root: Path, items: list[InventoryItem]) -> None:
    rel = relpath(path, root)
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError, UnicodeDecodeError):
        return
    project = data.get("project", {})
    entry_points = project.get("entry-points", {})
    for group, value in sorted(entry_points.items()):
        if group.startswith("scistudio."):
            section = "02_entry_points"
            if group == "scistudio.types":
                section = "03_type_contracts"
            elif group == "scistudio.previewers":
                section = "09_previewer_contracts"
            elif group == "scistudio.adapters":
                section = "02_entry_points"
            add_item(
                items,
                section=section,
                kind="entry_point_group",
                path=rel,
                line=1,
                symbol=group,
                required=True,
                reason=f"pyproject declares {group} entry-point group",
            )
            if isinstance(value, dict):
                for name in sorted(value):
                    add_item(
                        items,
                        section=section,
                        kind="entry_point_name",
                        path=rel,
                        line=1,
                        symbol=f"{group}:{name}",
                        required=False,
                        reason="specific package entry-point declaration",
                    )
    tool = data.get("tool", {})
    if isinstance(tool, dict) and "scistudio" in tool:
        add_item(
            items,
            section="01_package_metadata_distribution",
            kind="tool_scistudio_manifest",
            path=rel,
            line=1,
            symbol="[tool.scistudio]",
            required=True,
            reason="ADR-037 package manifest declaration",
        )


def add_known_file_items(root: Path, items: list[InventoryItem]) -> None:
    known = {
        "src/scistudio/previewers/data_access.py": (
            "10_preview_provider_behavior",
            "preview_data_access_module",
            "PreviewDataAccess bounded data access surface",
        ),
        "src/scistudio/previewers/session.py": (
            "10_preview_provider_behavior",
            "preview_session_provider_invocation",
            "Preview provider invocation and exception handling",
        ),
        "src/scistudio/api/preview_plot_jobs.py": (
            "11_plot_jobs",
            "plot_job_api",
            "Plot job API contract",
        ),
        "src/scistudio/previewers/assets.py": (
            "12_security_isolation",
            "preview_asset_security",
            "Same-origin/path-confined preview asset serving",
        ),
        "src/scistudio/engine/worker.py": (
            "12_security_isolation",
            "worker_boundary",
            "Subprocess worker boundary",
        ),
        "src/scistudio/blocks/registry/_scan.py": (
            "13_cross_surface_registry_consistency",
            "block_registry_scan",
            "Block package registry scan and live mutation behavior",
        ),
        "src/scistudio/core/types/registry.py": (
            "13_cross_surface_registry_consistency",
            "type_registry_scan",
            "Type package registry scan behavior",
        ),
        "src/scistudio/previewers/registry.py": (
            "13_cross_surface_registry_consistency",
            "previewer_registry_scan",
            "Previewer package registry scan behavior",
        ),
    }
    for rel, (section, kind, reason) in known.items():
        path = root / rel
        if path.exists():
            add_item(
                items,
                section=section,
                kind=kind,
                path=rel,
                line=1,
                symbol=Path(rel).stem,
                required=True,
                reason=reason,
            )


def extract_inventory(root: Path) -> list[InventoryItem]:
    items: list[InventoryItem] = []
    for base in (root / "src", root / "packages"):
        if base.exists():
            for py_file in sorted(base.rglob("*.py")):
                parts = set(py_file.parts)
                if parts & {".venv", "node_modules", "__pycache__"}:
                    continue
                parse_py_file(py_file, root, items)
    for pyproject in sorted([root / "pyproject.toml", *(root / "packages").glob("*/pyproject.toml")]):
        if pyproject.exists():
            parse_pyproject(pyproject, root, items)
    add_known_file_items(root, items)

    dedup: dict[tuple[str, str, str, int, str], InventoryItem] = {}
    for item in items:
        key = (item.section, item.kind, item.path, item.line, item.symbol)
        dedup[key] = item
    return sorted(dedup.values(), key=lambda item: (item.section, item.path, item.line, item.kind, item.symbol))


def normalize_sections(raw: str | None) -> set[str] | None:
    if not raw:
        return None
    result: set[str] = set()
    for part in raw.split(","):
        key = part.strip()
        if not key:
            continue
        alias_key = key.zfill(2) if key.isdigit() else key
        result.add(SECTION_ALIASES.get(alias_key, key))
    unknown = result - VALID_SECTIONS
    if unknown:
        raise SystemExit(f"unknown section filter(s): {sorted(unknown)}")
    return result


def text_matches(text: str, kind: str, pattern: str) -> bool:
    if kind == "contains":
        return pattern in text
    if kind == "regex":
        return re.search(pattern, text, flags=re.MULTILINE | re.DOTALL) is not None
    raise ValueError(f"unknown evidence kind: {kind}")


def evidence_matches(root: Path, evidence: dict[str, Any]) -> tuple[bool, str]:
    evidence_path = evidence.get("path")
    if not isinstance(evidence_path, str) or not evidence_path:
        return False, "evidence path must be a non-empty string"
    path = root / evidence_path
    if not path.is_file():
        return False, f"path not found: {evidence_path}"
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return False, f"path is not UTF-8 text: {evidence_path}"
    kind = evidence.get("kind")
    pattern = evidence.get("pattern")
    if not isinstance(kind, str) or not isinstance(pattern, str):
        return False, f"evidence kind and pattern must be strings for {evidence_path}"
    try:
        matched = text_matches(text, kind, pattern)
    except re.error as exc:
        return False, f"invalid regex for {evidence_path}: {exc}"
    if not matched:
        return False, f"pattern not found in {evidence.get('path')}: {pattern!r}"
    return True, ""


def validate_contract_table_shape(table: dict[str, Any], table_path: Path) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    table_name = table_path.as_posix()
    required = {"schema_version", "agent_id", "generated_at", "source_priority", "agent_scope", "contracts"}
    missing = sorted(required - set(table))
    for key in missing:
        diagnostics.append(Diagnostic("error", table_name, "<table>", f"missing top-level field {key!r}"))
    if table.get("schema_version") != SCHEMA_VERSION:
        diagnostics.append(Diagnostic("error", table_name, "<table>", f"schema_version must be {SCHEMA_VERSION!r}"))
    if table.get("source_priority") != "code-primary-adr-secondary":
        diagnostics.append(
            Diagnostic("error", table_name, "<table>", "source_priority must be code-primary-adr-secondary")
        )
    contracts = table.get("contracts")
    if not isinstance(contracts, list) or not contracts:
        diagnostics.append(Diagnostic("error", table_name, "<table>", "contracts must be a non-empty list"))
        return diagnostics
    seen_ids: set[str] = set()
    for index, contract in enumerate(contracts):
        cid = contract.get("id", f"<contract[{index}]>") if isinstance(contract, dict) else f"<contract[{index}]>"
        if not isinstance(contract, dict):
            diagnostics.append(Diagnostic("error", table_name, cid, "contract row must be an object"))
            continue
        for key in {
            "id",
            "section",
            "title",
            "contract",
            "status",
            "severity",
            "environments",
            "validator_profile",
            "applicability",
            "code_evidence",
            "adr_evidence",
            "tests",
            "adr_alignment",
            "validator_implication",
        }:
            if key not in contract:
                diagnostics.append(Diagnostic("error", table_name, cid, f"missing contract field {key!r}"))
        if cid in seen_ids:
            diagnostics.append(Diagnostic("error", table_name, cid, "duplicate contract id"))
        seen_ids.add(cid)
        if contract.get("section") not in VALID_SECTIONS:
            diagnostics.append(Diagnostic("error", table_name, cid, f"unknown section {contract.get('section')!r}"))
        if not isinstance(contract.get("code_evidence"), list) or not contract.get("code_evidence"):
            diagnostics.append(Diagnostic("error", table_name, cid, "code_evidence must be a non-empty list"))
        applicability = contract.get("applicability")
        if not isinstance(applicability, dict):
            diagnostics.append(Diagnostic("error", table_name, cid, "applicability must be an object"))
        else:
            surfaces = applicability.get("candidate_surfaces")
            if not isinstance(surfaces, list) or not surfaces or not all(isinstance(s, str) and s for s in surfaces):
                diagnostics.append(
                    Diagnostic(
                        "error", table_name, cid, "applicability.candidate_surfaces must be a non-empty string list"
                    )
                )
            if not isinstance(applicability.get("trigger"), str) or not applicability.get("trigger"):
                diagnostics.append(
                    Diagnostic("error", table_name, cid, "applicability.trigger must be a non-empty string")
                )
            if applicability.get("not_applicable_result") != "not_applicable":
                diagnostics.append(
                    Diagnostic(
                        "error",
                        table_name,
                        cid,
                        "applicability.not_applicable_result must be 'not_applicable'",
                    )
                )
    return diagnostics


def load_tables(contract_dir: Path) -> tuple[list[tuple[Path, dict[str, Any]]], list[Diagnostic]]:
    diagnostics: list[Diagnostic] = []
    tables: list[tuple[Path, dict[str, Any]]] = []
    for path in sorted(contract_dir.glob("*.json")):
        if path.name == "contract-table.schema.json":
            continue
        try:
            table = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            diagnostics.append(Diagnostic("error", path.as_posix(), "<table>", f"cannot parse JSON: {exc}"))
            continue
        if not isinstance(table, dict):
            diagnostics.append(Diagnostic("error", path.as_posix(), "<table>", "table root must be an object"))
            continue
        diagnostics.extend(validate_contract_table_shape(table, path))
        tables.append((path, table))
    return tables, diagnostics


def check_tables(
    root: Path, contract_dir: Path, sections: set[str] | None
) -> tuple[list[Diagnostic], list[Diagnostic]]:
    errors: list[Diagnostic] = []
    warnings: list[Diagnostic] = []
    tables, shape_diags = load_tables(contract_dir)
    for diag in shape_diags:
        (errors if diag.level == "error" else warnings).append(diag)

    covered_symbols: set[tuple[str, str]] = set()
    global_ids: dict[str, str] = {}
    for table_path, table in tables:
        for contract in table.get("contracts", []):
            if not isinstance(contract, dict):
                continue
            section = contract.get("section")
            if sections is not None and section not in sections:
                continue
            cid = contract.get("id", "<unknown>")
            previous_table = global_ids.get(cid)
            if previous_table is not None:
                errors.append(
                    Diagnostic(
                        "error",
                        table_path.as_posix(),
                        cid,
                        f"duplicate contract id also appears in {previous_table}",
                    )
                )
            else:
                global_ids[cid] = table_path.as_posix()
            code_ok = True
            for evidence in contract.get("code_evidence", []):
                if not isinstance(evidence, dict):
                    errors.append(Diagnostic("error", table_path.as_posix(), cid, "code evidence must be object"))
                    code_ok = False
                    continue
                ok, message = evidence_matches(root, evidence)
                if not ok:
                    errors.append(Diagnostic("error", table_path.as_posix(), cid, f"code evidence mismatch: {message}"))
                    code_ok = False
                symbol = evidence.get("symbol")
                ev_path = evidence.get("path")
                if isinstance(symbol, str) and isinstance(ev_path, str):
                    covered_symbols.add((ev_path, symbol))

            if code_ok:
                alignment = contract.get("adr_alignment")
                if alignment in {"adr_drift", "adr_missing", "adr_planned"}:
                    warnings.append(
                        Diagnostic(
                            "warning",
                            table_path.as_posix(),
                            cid,
                            f"contract declares {alignment}; code evidence passed but ADR/spec text is not fully aligned",
                        )
                    )
                adr_evidence = contract.get("adr_evidence", [])
                if not adr_evidence and contract.get("adr_alignment") in {"aligned", "adr_drift"}:
                    warnings.append(
                        Diagnostic("warning", table_path.as_posix(), cid, "no ADR evidence for claimed ADR alignment")
                    )
                for evidence in adr_evidence:
                    if not isinstance(evidence, dict):
                        warnings.append(
                            Diagnostic("warning", table_path.as_posix(), cid, "ADR evidence must be object")
                        )
                        continue
                    ok, message = evidence_matches(root, evidence)
                    if not ok:
                        warnings.append(
                            Diagnostic("warning", table_path.as_posix(), cid, f"ADR evidence mismatch: {message}")
                        )

                for evidence in contract.get("tests", []):
                    if not isinstance(evidence, dict):
                        warnings.append(
                            Diagnostic("warning", table_path.as_posix(), cid, "test evidence must be object")
                        )
                        continue
                    ok, message = evidence_matches(root, evidence)
                    if not ok:
                        warnings.append(
                            Diagnostic("warning", table_path.as_posix(), cid, f"test evidence mismatch: {message}")
                        )

    inventory = extract_inventory(root)
    if sections is not None:
        inventory = [item for item in inventory if item.section in sections]
    for item in inventory:
        if not item.required:
            continue
        if (item.path, item.symbol) in covered_symbols:
            continue
        errors.append(
            Diagnostic(
                "error",
                "<inventory>",
                item.symbol,
                (
                    f"required inventory item not explicitly covered: section={item.section} "
                    f"kind={item.kind} path={item.path}:{item.line} reason={item.reason}"
                ),
            )
        )
    if sections is None:
        check_adr_coverage(root, tables, errors)
    return errors, warnings


def check_adr_coverage(
    root: Path,
    tables: list[tuple[Path, dict[str, Any]]],
    errors: list[Diagnostic],
) -> None:
    """Verify ADR-049 names the machine-verifiable contract artifacts."""

    adr_path = root / "docs/adr/ADR-049.md"
    if not adr_path.exists():
        return
    text = adr_path.read_text(encoding="utf-8")
    required_snippets = [
        "scripts/audit/check_package_contract_tables.py",
        "docs/planning/adr-049-package-validator/contracts/contract-table.schema.json",
    ]
    for table_path, table in tables:
        required_snippets.append(relpath(table_path, root))
        for contract in table.get("contracts", []):
            if isinstance(contract, dict) and isinstance(contract.get("id"), str):
                required_snippets.append(contract["id"])
    for snippet in sorted(set(required_snippets)):
        if snippet not in text:
            errors.append(
                Diagnostic(
                    "error",
                    relpath(adr_path, root),
                    "ADR-049",
                    f"ADR does not include required contract artifact or id: {snippet}",
                )
            )


def print_diagnostics(errors: list[Diagnostic], warnings: list[Diagnostic]) -> None:
    for diag in errors:
        print(f"ERROR {diag.table} {diag.contract_id}: {diag.message}")
    for diag in warnings:
        print(f"WARNING {diag.table} {diag.contract_id}: {diag.message}")
    print(f"summary: {len(errors)} error(s), {len(warnings)} warning(s)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".", help="Repository root. Defaults to cwd.")
    parser.add_argument("--contracts-dir", default=str(DEFAULT_CONTRACT_DIR), help="Contract table directory.")
    parser.add_argument("--sections", help="Comma-separated section numbers or names to filter.")
    parser.add_argument(
        "--dump-inventory", action="store_true", help="Print mechanical code interface inventory as JSON."
    )
    parser.add_argument("--output", help="Write --dump-inventory JSON to this path instead of stdout.")
    args = parser.parse_args(argv)

    root = Path(args.repo_root).resolve()
    sections = normalize_sections(args.sections)

    if args.dump_inventory:
        inventory = extract_inventory(root)
        if sections is not None:
            inventory = [item for item in inventory if item.section in sections]
        payload = {
            "schema_version": "adr049.package_interface_inventory.v1",
            "generated_by": "scripts/audit/check_package_contract_tables.py",
            "items": [asdict(item) for item in inventory],
        }
        text = json.dumps(payload, indent=2, sort_keys=True)
        if args.output:
            output = root / args.output
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(text + "\n", encoding="utf-8")
        else:
            print(text)
        return 0

    errors, warnings = check_tables(root, root / args.contracts_dir, sections)
    print_diagnostics(errors, warnings)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
