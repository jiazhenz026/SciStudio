"""Candidate package inventory for the ADR-049 validator."""

from __future__ import annotations

import configparser
import contextlib
import email.parser
import importlib
import importlib.metadata
import shutil
import sys
import tarfile
import tempfile
import tomllib
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from packaging.requirements import InvalidRequirement, Requirement
from packaging.utils import canonicalize_name

from scistudio.packages.validation.models import CandidatePackage, PackageIdentity, PackageInventory

KNOWN_ENTRY_POINT_GROUPS = {
    "scistudio.blocks": "blocks",
    "scistudio.types": "types",
    "scistudio.previewers": "previewers",
    "scistudio.runners": "runners",
}


@dataclass(frozen=True)
class CandidateEntryPoint:
    """Entry point resolved from source-tree pyproject or installed metadata."""

    group: str
    name: str
    value: str

    @property
    def surface(self) -> str:
        return KNOWN_ENTRY_POINT_GROUPS.get(self.group, "entry_points")

    def to_dict(self) -> dict[str, str]:
        return {"group": self.group, "name": self.name, "value": self.value}

    def load(self) -> Any:
        module_name, sep, attr = self.value.partition(":")
        module = importlib.import_module(module_name)
        if not sep:
            return module
        loaded: Any = module
        for part in attr.split("."):
            loaded = getattr(loaded, part)
        return loaded


@dataclass(frozen=True)
class CandidateInventory:
    """Inventory plus loadable entry point helpers."""

    candidate: CandidatePackage
    inventory: PackageInventory
    entry_points: tuple[CandidateEntryPoint, ...]
    import_paths: tuple[Path, ...] = ()
    cleanup_paths: tuple[Path, ...] = ()


def build_inventory(candidate_input: str | Path) -> CandidateInventory:
    """Build package identity, entry-point, and surface inventory."""

    if isinstance(candidate_input, Path) or Path(str(candidate_input)).exists():
        path = Path(candidate_input)
        if path.is_dir():
            return _source_tree_inventory(path)
        return _archive_inventory(path)
    return _installed_distribution_inventory(str(candidate_input))


@contextlib.contextmanager
def candidate_import_context(candidate: CandidateInventory) -> Iterator[None]:
    """Expose a source-tree candidate on ``sys.path`` for one validation block."""

    inserted: list[str] = []
    before_modules = dict(sys.modules)
    for path in reversed(candidate.import_paths):
        value = str(path)
        if value not in sys.path:
            sys.path.insert(0, value)
            inserted.append(value)
    try:
        yield
    finally:
        for value in inserted:
            with contextlib.suppress(ValueError):
                sys.path.remove(value)
        _remove_candidate_modules(before_modules, _candidate_owned_import_paths(candidate))
        for path in candidate.cleanup_paths:
            with contextlib.suppress(OSError):
                shutil.rmtree(path)


def _source_tree_inventory(root: Path) -> CandidateInventory:
    pyproject = root / "pyproject.toml"
    if not pyproject.is_file():
        identity = PackageIdentity(name=root.name, version="unknown", source=str(root))
        candidate = CandidatePackage(
            "source-tree", str(root), root_path=root, name=identity.name, version=identity.version
        )
        inventory = PackageInventory(package=identity, root_path=root, surfaces={"distribution_metadata"})
        return CandidateInventory(candidate=candidate, inventory=inventory, entry_points=(), import_paths=(root,))

    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    project = data.get("project", {})
    name = str(project.get("name") or root.name)
    version = str(project.get("version") or "unknown")
    identity = PackageIdentity(name=name, version=version, source=str(root))
    entry_points = _entry_points_from_pyproject(project)
    import_paths = _source_import_paths(root, data)
    surfaces = _surfaces_for_entry_points(entry_points)
    surfaces.add("distribution_metadata")
    candidate = CandidatePackage("source-tree", str(root), root_path=root, name=name, version=version)
    inventory = PackageInventory(
        package=identity,
        root_path=root,
        entry_points=[entry_point.to_dict() for entry_point in entry_points],
        surfaces=surfaces,
    )
    return CandidateInventory(
        candidate=candidate,
        inventory=inventory,
        entry_points=tuple(entry_points),
        import_paths=tuple(import_paths),
    )


def _archive_inventory(path: Path) -> CandidateInventory:
    if path.suffix == ".whl":
        return _wheel_inventory(path)
    if path.suffixes[-2:] in ([".tar", ".gz"], [".tar", ".bz2"], [".tar", ".xz"]) or path.suffix in {
        ".tgz",
        ".zip",
    }:
        return _sdist_inventory(path)
    name = path.name
    identity = PackageIdentity(name=name, version="unknown", source=str(path))
    candidate = CandidatePackage("unsupported-archive", str(path), root_path=path.parent, name=name, version="unknown")
    inventory = PackageInventory(package=identity, root_path=path.parent, surfaces={"distribution_metadata", "archive"})
    return CandidateInventory(candidate=candidate, inventory=inventory, entry_points=())


def _installed_distribution_inventory(distribution_name: str) -> CandidateInventory:
    distribution = importlib.metadata.distribution(distribution_name)
    metadata = distribution.metadata
    name = _metadata_name(metadata, distribution_name)
    version = distribution.version or "unknown"
    identity = PackageIdentity(name=name, version=version, source=distribution_name)
    entry_points = [
        CandidateEntryPoint(group=ep.group, name=ep.name, value=ep.value)
        for ep in distribution.entry_points
        if _is_scistudio_entry_point_group(ep.group)
    ]
    surfaces = _surfaces_for_entry_points(entry_points)
    surfaces.add("distribution_metadata")
    candidate = CandidatePackage("installed-distribution", distribution_name, name=name, version=version)
    inventory = PackageInventory(
        package=identity,
        entry_points=[entry_point.to_dict() for entry_point in entry_points],
        surfaces=surfaces,
    )
    return CandidateInventory(candidate=candidate, inventory=inventory, entry_points=tuple(entry_points))


def _entry_points_from_pyproject(project: dict[str, Any]) -> list[CandidateEntryPoint]:
    groups = project.get("entry-points", {})
    if not isinstance(groups, dict):
        return []
    entry_points: list[CandidateEntryPoint] = []
    for group, entries in sorted(groups.items()):
        if not _is_scistudio_entry_point_group(str(group)):
            continue
        if not isinstance(entries, dict):
            continue
        for name, value in sorted(entries.items()):
            entry_points.append(CandidateEntryPoint(group=str(group), name=str(name), value=str(value)))
    return entry_points


def _metadata_name(metadata: importlib.metadata.PackageMetadata, fallback: str) -> str:
    try:
        return metadata["Name"]
    except KeyError:
        return fallback


def _source_import_paths(root: Path, pyproject: dict[str, Any]) -> list[Path]:
    paths = _local_source_paths(root, pyproject)
    for dependency_path in _declared_monorepo_dependency_import_paths(root, pyproject):
        if dependency_path not in paths:
            paths.append(dependency_path)
    return paths


def _declared_monorepo_dependency_import_paths(root: Path, pyproject: dict[str, Any]) -> list[Path]:
    project = pyproject.get("project", {})
    dependency_names = _declared_dependency_names(project)
    if not dependency_names:
        return []

    packages_root = root.parent
    if packages_root.name != "packages" or not packages_root.is_dir():
        return []

    paths: list[Path] = []
    for sibling in sorted(packages_root.iterdir()):
        if sibling == root or not sibling.is_dir():
            continue
        sibling_pyproject = sibling / "pyproject.toml"
        if not sibling_pyproject.is_file():
            continue
        try:
            sibling_data = tomllib.loads(sibling_pyproject.read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError:
            continue
        sibling_project = sibling_data.get("project", {})
        sibling_name = sibling_project.get("name")
        if not isinstance(sibling_name, str) or canonicalize_name(sibling_name) not in dependency_names:
            continue
        for path in _local_source_paths(sibling, sibling_data):
            if path not in paths:
                paths.append(path)
    return paths


def _declared_dependency_names(project: dict[str, Any]) -> set[str]:
    dependencies = project.get("dependencies", [])
    if not isinstance(dependencies, list):
        return set()

    names: set[str] = set()
    for dependency in dependencies:
        if not isinstance(dependency, str):
            continue
        try:
            names.add(canonicalize_name(Requirement(dependency).name))
        except InvalidRequirement:
            continue
    return names


def _local_source_paths(root: Path, pyproject: dict[str, Any]) -> list[Path]:
    paths: list[Path] = []
    setuptools_find = (
        pyproject.get("tool", {}).get("setuptools", {}).get("packages", {}).get("find", {}).get("where", [])
    )
    if isinstance(setuptools_find, list):
        for item in setuptools_find:
            candidate = root / str(item)
            if candidate.is_dir():
                paths.append(candidate)
    if (root / "src").is_dir() and root / "src" not in paths:
        paths.append(root / "src")
    if root not in paths:
        paths.append(root)
    return paths


def _surfaces_for_entry_points(entry_points: list[CandidateEntryPoint]) -> set[str]:
    surfaces = {"entry_points"} if entry_points else set()
    for entry_point in entry_points:
        surfaces.add(entry_point.surface)
    return surfaces


def _is_scistudio_entry_point_group(group: str) -> bool:
    return group in KNOWN_ENTRY_POINT_GROUPS or group.startswith("scistudio.")


def _wheel_inventory(path: Path) -> CandidateInventory:
    extract_root = Path(tempfile.mkdtemp(prefix="scistudio-pv-wheel-"))
    with zipfile.ZipFile(path) as wheel:
        wheel.extractall(extract_root)
    metadata = _wheel_metadata(extract_root)
    name = metadata.get("Name") or path.stem
    version = metadata.get("Version") or "unknown"
    entry_points = _entry_points_from_ini(_first_existing(extract_root.glob("*.dist-info/entry_points.txt")))
    surfaces = _surfaces_for_entry_points(entry_points)
    surfaces.update({"distribution_metadata", "archive"})
    identity = PackageIdentity(name=name, version=version, source=str(path))
    candidate = CandidatePackage("wheel", str(path), root_path=extract_root, name=name, version=version)
    inventory = PackageInventory(
        package=identity,
        root_path=extract_root,
        entry_points=[entry_point.to_dict() for entry_point in entry_points],
        surfaces=surfaces,
    )
    return CandidateInventory(
        candidate=candidate,
        inventory=inventory,
        entry_points=tuple(entry_points),
        import_paths=(extract_root,),
        cleanup_paths=(extract_root,),
    )


def _sdist_inventory(path: Path) -> CandidateInventory:
    extract_root = Path(tempfile.mkdtemp(prefix="scistudio-pv-sdist-"))
    if path.suffix == ".zip":
        with zipfile.ZipFile(path) as archive:
            archive.extractall(extract_root)
    else:
        with tarfile.open(path) as archive:
            archive.extractall(extract_root, filter="data")
    roots = [candidate for candidate in extract_root.iterdir() if candidate.is_dir()]
    source_root = roots[0] if len(roots) == 1 else extract_root
    inventory = _source_tree_inventory(source_root)
    return CandidateInventory(
        candidate=CandidatePackage(
            "sdist",
            str(path),
            root_path=inventory.candidate.root_path,
            name=inventory.candidate.name,
            version=inventory.candidate.version,
        ),
        inventory=inventory.inventory,
        entry_points=inventory.entry_points,
        import_paths=inventory.import_paths,
        cleanup_paths=(extract_root,),
    )


def _wheel_metadata(extract_root: Path) -> dict[str, str]:
    metadata_path = _first_existing(extract_root.glob("*.dist-info/METADATA"))
    if metadata_path is None:
        return {}
    message = email.parser.Parser().parsestr(metadata_path.read_text(encoding="utf-8"))
    return {key: value for key, value in message.items()}


def _entry_points_from_ini(path: Path | None) -> list[CandidateEntryPoint]:
    if path is None:
        return []
    parser = configparser.ConfigParser()
    parser.read(path, encoding="utf-8")
    entry_points: list[CandidateEntryPoint] = []
    for group in sorted(parser.sections()):
        if not _is_scistudio_entry_point_group(group):
            continue
        for name, value in sorted(parser.items(group)):
            entry_points.append(CandidateEntryPoint(group=group, name=name, value=value))
    return entry_points


def _first_existing(paths: Iterator[Path]) -> Path | None:
    return next(paths, None)


def _remove_candidate_modules(before_modules: dict[str, Any], import_paths: tuple[Path, ...]) -> None:
    roots = tuple(path.resolve() for path in import_paths if path.exists())
    if not roots:
        return
    for name, module in list(sys.modules.items()):
        if name in before_modules and before_modules[name] is module:
            continue
        module_file = getattr(module, "__file__", None)
        if not module_file:
            continue
        with contextlib.suppress(OSError, RuntimeError):
            resolved = Path(module_file).resolve()
            if any(resolved.is_relative_to(root) for root in roots):
                sys.modules.pop(name, None)


def _candidate_owned_import_paths(candidate: CandidateInventory) -> tuple[Path, ...]:
    root = candidate.inventory.root_path
    if root is None:
        return candidate.import_paths
    resolved_root = root.resolve()
    return tuple(path for path in candidate.import_paths if path.resolve().is_relative_to(resolved_root))
