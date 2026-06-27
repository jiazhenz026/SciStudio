"""Local package installer for desktop SciStudio runs."""

from __future__ import annotations

import contextlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import tomllib
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from email.parser import Parser
from pathlib import Path

from scistudio.desktop import paths

_MANIFEST_NAME = "scistudio-local-package.json"
_SUPPORTED_ARCHIVE_SUFFIXES = {".zip", ".tar", ".tgz", ".tar.gz", ".tar.bz2", ".tar.xz"}


class PackageInstallError(ValueError):
    """Raised when a local package cannot be installed."""


@dataclass(frozen=True)
class LocalPackageInstallResult:
    package_name: str
    version: str
    install_path: Path
    source_path: Path
    modules: tuple[str, ...]
    manifest_path: Path
    replaced: bool


@dataclass(frozen=True)
class LocalPackageDependencyRepairResult:
    package_name: str
    version: str
    install_path: Path
    repaired: bool
    reason: str
    error: str = ""


@dataclass(frozen=True)
class _PackageMetadata:
    name: str
    version: str


@dataclass(frozen=True)
class _PythonRuntimeInfo:
    executable: str
    version: str
    cache_tag: str


def install_local_package(
    source: str | Path,
    *,
    install_root: str | Path | None = None,
    install_dependencies: bool = False,
    python_executable: str | Path | None = None,
) -> LocalPackageInstallResult:
    """Install a local SciStudio block package into the user plugin area."""

    source_path = Path(source).expanduser()
    if not source_path.exists():
        raise PackageInstallError(f"Package path does not exist: {source_path}")

    resolved_source = source_path.resolve()
    root = Path(install_root).expanduser() if install_root is not None else paths.installed_packages_dir()
    root.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix=".scistudio-install-", dir=str(root)) as stage_name:
        stage_dir = Path(stage_name)
        prepared_dir = stage_dir / "prepared"
        install_source: Path
        dependencies: tuple[str, ...] = ()

        if resolved_source.is_dir():
            package_root = _find_source_root(resolved_source)
            if package_root is None:
                raise PackageInstallError(f"No SciStudio block package found in {resolved_source}")
            metadata = _source_metadata(package_root)
            dependencies = _source_dependencies(package_root)
            shutil.copytree(package_root, prepared_dir, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            install_source = prepared_dir
        elif _is_wheel(resolved_source):
            metadata = _wheel_metadata(resolved_source)
            dependencies = _wheel_dependencies(resolved_source)
            prepared_dir.mkdir()
            _extract_zip(resolved_source, prepared_dir)
            install_source = resolved_source
        elif _is_supported_archive(resolved_source):
            extract_dir = stage_dir / "archive"
            extract_dir.mkdir()
            if _suffix_key(resolved_source) == ".zip":
                _extract_zip(resolved_source, extract_dir)
            else:
                _extract_tar(resolved_source, extract_dir)
            package_root = _find_source_root(extract_dir)
            if package_root is None:
                raise PackageInstallError(f"No SciStudio block package found in {resolved_source}")
            metadata = _source_metadata(package_root)
            dependencies = _source_dependencies(package_root)
            shutil.copytree(package_root, prepared_dir, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            install_source = prepared_dir
        else:
            suffixes = "".join(resolved_source.suffixes) or resolved_source.suffix
            raise PackageInstallError(f"Unsupported package file type: {suffixes or resolved_source.name}")

        modules = tuple(_discover_block_modules(prepared_dir))
        if not modules:
            raise PackageInstallError("Package does not contain a scistudio_blocks_* module with an __init__.py file.")

        target_dir = root / _install_dir_name(metadata)
        runtime_dependencies = _runtime_dependencies(dependencies)
        dependency_runtime: dict[str, object] | None = None
        if install_dependencies:
            python = str(Path(python_executable)) if python_executable is not None else sys.executable
            _install_runtime_package(
                install_source,
                runtime_dependencies=runtime_dependencies,
                target_dir=prepared_dir / paths.PACKAGE_SITE_DIR_NAME,
                python_executable=python,
            )
            runtime_info = _python_runtime_info(python)
            dependency_runtime = {
                "python_executable": runtime_info.executable,
                "python_version": runtime_info.version,
                "cache_tag": runtime_info.cache_tag,
                "dependencies": list(runtime_dependencies),
                "installed_at": datetime.now(UTC).isoformat(),
            }

        manifest: dict[str, object] = {
            "package_name": metadata.name,
            "version": metadata.version,
            "modules": list(modules),
            "source_path": str(resolved_source),
            "installed_at": datetime.now(UTC).isoformat(),
            "format": _source_format(resolved_source),
        }
        if dependency_runtime is not None:
            manifest["dependency_runtime"] = dependency_runtime
        manifest_path = prepared_dir / _MANIFEST_NAME
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        replaced = target_dir.exists()
        if replaced:
            shutil.rmtree(target_dir)
        shutil.move(str(prepared_dir), str(target_dir))

    return LocalPackageInstallResult(
        package_name=metadata.name,
        version=metadata.version,
        install_path=target_dir,
        source_path=resolved_source,
        modules=modules,
        manifest_path=target_dir / _MANIFEST_NAME,
        replaced=replaced,
    )


def repair_installed_package_dependencies(
    *,
    install_root: str | Path | None = None,
    python_executable: str | Path | None = None,
) -> list[LocalPackageDependencyRepairResult]:
    """Repair user package dependency caches that target another Python ABI."""
    root = Path(install_root).expanduser() if install_root is not None else paths.installed_packages_dir()
    if not root.is_dir():
        return []

    python = str(Path(python_executable)) if python_executable is not None else sys.executable
    runtime_info = _python_runtime_info(python)
    results: list[LocalPackageDependencyRepairResult] = []
    for manifest_path in sorted(root.glob(f"*/{_MANIFEST_NAME}")):
        try:
            raw = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            results.append(
                LocalPackageDependencyRepairResult(
                    package_name=manifest_path.parent.name,
                    version="",
                    install_path=manifest_path.parent,
                    repaired=False,
                    reason="manifest unreadable",
                    error=str(exc),
                )
            )
            continue

        package_name = str(raw.get("package_name") or manifest_path.parent.name)
        version = str(raw.get("version") or "")
        install_path = manifest_path.parent
        source_raw = raw.get("source_path")
        source_path = Path(str(source_raw)).expanduser() if isinstance(source_raw, str) and source_raw else None
        if source_path is None or not source_path.exists():
            results.append(
                LocalPackageDependencyRepairResult(
                    package_name=package_name,
                    version=version,
                    install_path=install_path,
                    repaired=False,
                    reason="source path unavailable",
                    error=str(source_raw or ""),
                )
            )
            continue

        dependencies = _dependencies_for_source(source_path)
        runtime_dependencies = _runtime_dependencies(dependencies)
        reason = _dependency_cache_repair_reason(
            install_path=install_path,
            manifest=raw,
            runtime_info=runtime_info,
            runtime_dependencies=runtime_dependencies,
        )
        if reason is None:
            continue

        try:
            result = install_local_package(
                source_path,
                install_root=root,
                install_dependencies=True,
                python_executable=python,
            )
        except Exception as exc:
            results.append(
                LocalPackageDependencyRepairResult(
                    package_name=package_name,
                    version=version,
                    install_path=install_path,
                    repaired=False,
                    reason=reason,
                    error=str(exc),
                )
            )
            continue
        results.append(
            LocalPackageDependencyRepairResult(
                package_name=result.package_name,
                version=result.version,
                install_path=result.install_path,
                repaired=True,
                reason=reason,
            )
        )
    return results


def _source_format(source: Path) -> str:
    if source.is_dir():
        return "source-directory"
    if _is_wheel(source):
        return "wheel"
    return "source-archive"


def _install_dir_name(metadata: _PackageMetadata) -> str:
    name = _safe_path_component(metadata.name)
    version = _safe_path_component(metadata.version)
    return f"{name}-{version}"


def _safe_path_component(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip())
    cleaned = cleaned.strip("._-")
    return cleaned.lower() or "package"


def _is_wheel(path: Path) -> bool:
    return path.suffix.lower() == ".whl"


def _is_supported_archive(path: Path) -> bool:
    return _suffix_key(path) in _SUPPORTED_ARCHIVE_SUFFIXES


def _suffix_key(path: Path) -> str:
    suffixes = [suffix.lower() for suffix in path.suffixes]
    if len(suffixes) >= 2 and suffixes[-2:] in (
        [".tar", ".gz"],
        [".tar", ".bz2"],
        [".tar", ".xz"],
    ):
        return "".join(suffixes[-2:])
    return suffixes[-1] if suffixes else ""


def _source_metadata(package_root: Path) -> _PackageMetadata:
    pyproject = package_root / "pyproject.toml"
    if pyproject.is_file():
        try:
            parsed = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError as exc:
            raise PackageInstallError(f"Invalid pyproject.toml in {package_root}: {exc}") from exc
        project = parsed.get("project", {}) if isinstance(parsed, dict) else {}
        name = project.get("name") if isinstance(project, dict) else None
        version = project.get("version") if isinstance(project, dict) else None
        if isinstance(name, str) and name.strip():
            return _PackageMetadata(name=name.strip(), version=str(version or "0.1.0").strip() or "0.1.0")
    return _PackageMetadata(name=package_root.name, version="0.1.0")


def _wheel_metadata(wheel_path: Path) -> _PackageMetadata:
    with zipfile.ZipFile(wheel_path) as archive:
        metadata_names = [
            name for name in archive.namelist() if name.endswith(".dist-info/METADATA") and not name.startswith("/")
        ]
        if metadata_names:
            raw = archive.read(metadata_names[0]).decode("utf-8", errors="replace")
            message = Parser().parsestr(raw)
            name = message.get("Name")
            version = message.get("Version")
            if name:
                return _PackageMetadata(name=name.strip(), version=(version or "0.1.0").strip() or "0.1.0")

    parts = wheel_path.name[:-4].split("-")
    if len(parts) >= 2 and parts[0]:
        return _PackageMetadata(name=parts[0].replace("_", "-"), version=parts[1])
    raise PackageInstallError(f"Wheel metadata is missing a package name: {wheel_path}")


def _source_dependencies(package_root: Path) -> tuple[str, ...]:
    pyproject = package_root / "pyproject.toml"
    if not pyproject.is_file():
        return ()
    try:
        parsed = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise PackageInstallError(f"Invalid pyproject.toml in {package_root}: {exc}") from exc
    project = parsed.get("project", {}) if isinstance(parsed, dict) else {}
    dependencies = project.get("dependencies") if isinstance(project, dict) else None
    if not isinstance(dependencies, list):
        return ()
    return tuple(dep for dep in dependencies if isinstance(dep, str) and dep.strip())


def _wheel_dependencies(wheel_path: Path) -> tuple[str, ...]:
    with zipfile.ZipFile(wheel_path) as archive:
        metadata_names = [
            name for name in archive.namelist() if name.endswith(".dist-info/METADATA") and not name.startswith("/")
        ]
        if not metadata_names:
            return ()
        raw = archive.read(metadata_names[0]).decode("utf-8", errors="replace")
    message = Parser().parsestr(raw)
    return tuple(dep for dep in message.get_all("Requires-Dist", []) if isinstance(dep, str) and dep.strip())


def _dependencies_for_source(source_path: Path) -> tuple[str, ...]:
    resolved_source = source_path.expanduser().resolve()
    if resolved_source.is_dir():
        package_root = _find_source_root(resolved_source)
        return _source_dependencies(package_root) if package_root is not None else ()
    if _is_wheel(resolved_source):
        return _wheel_dependencies(resolved_source)
    return ()


def _find_source_root(root: Path) -> Path | None:
    if _looks_like_source_package(root):
        return root
    candidates = [child for child in sorted(root.iterdir()) if child.is_dir() and _looks_like_source_package(child)]
    if len(candidates) == 1:
        return candidates[0]
    if len(candidates) > 1:
        names = ", ".join(candidate.name for candidate in candidates[:5])
        raise PackageInstallError(f"Archive contains multiple SciStudio packages: {names}")
    return None


def _looks_like_source_package(root: Path) -> bool:
    return (root / "pyproject.toml").is_file() or bool(_discover_block_modules(root))


def _discover_block_modules(package_root: Path) -> list[str]:
    modules: set[str] = set()
    for import_root in _candidate_import_roots(package_root):
        if not import_root.is_dir():
            continue
        for package_init in sorted(import_root.glob("scistudio_blocks_*/__init__.py")):
            modules.add(package_init.parent.name)
    return sorted(modules)


def _candidate_import_roots(package_root: Path) -> tuple[Path, ...]:
    src_dir = package_root / "src"
    return (src_dir, package_root) if src_dir.is_dir() else (package_root,)


def _install_runtime_package(
    install_source: Path,
    *,
    runtime_dependencies: tuple[str, ...],
    target_dir: Path,
    python_executable: str,
) -> None:
    target_dir.mkdir(parents=True, exist_ok=True)
    _run_pip(
        [
            python_executable,
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "--no-input",
            "--no-warn-script-location",
            "--target",
            str(target_dir),
            "--no-deps",
            str(install_source),
        ]
    )
    if runtime_dependencies:
        _run_pip(
            [
                python_executable,
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
                "--no-input",
                "--no-warn-script-location",
                "--target",
                str(target_dir),
                *runtime_dependencies,
            ]
        )
    _remove_core_runtime_shadow(target_dir)


def _python_runtime_info(python_executable: str | Path) -> _PythonRuntimeInfo:
    python = str(Path(python_executable))
    current = Path(sys.executable).resolve()
    target = Path(python).expanduser()
    with contextlib.suppress(OSError):
        target = target.resolve()
    if target == current:
        import platform

        return _PythonRuntimeInfo(
            executable=str(current),
            version=platform.python_version(),
            cache_tag=str(sys.implementation.cache_tag),
        )

    script = (
        "import json, platform, sys; "
        "print(json.dumps({'executable': sys.executable, "
        "'version': platform.python_version(), "
        "'cache_tag': sys.implementation.cache_tag}))"
    )
    try:
        output = subprocess.check_output([python, "-c", script], text=True, stderr=subprocess.STDOUT)
        payload = json.loads(output)
        return _PythonRuntimeInfo(
            executable=str(payload["executable"]),
            version=str(payload["version"]),
            cache_tag=str(payload["cache_tag"]),
        )
    except (OSError, subprocess.CalledProcessError, KeyError, json.JSONDecodeError) as exc:
        raise PackageInstallError(f"Failed to inspect Python runtime {python!r}: {exc}") from exc


def _runtime_dependencies(dependencies: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dep for dep in dependencies if not _is_core_runtime_dependency(dep))


def _dependency_cache_repair_reason(
    *,
    install_path: Path,
    manifest: dict[str, object],
    runtime_info: _PythonRuntimeInfo,
    runtime_dependencies: tuple[str, ...],
) -> str | None:
    site_dir = install_path / paths.PACKAGE_SITE_DIR_NAME
    if runtime_dependencies and not site_dir.is_dir():
        return "missing dependency cache"

    mismatched_binary = _first_mismatched_binary_tag(site_dir, runtime_info.cache_tag)
    if mismatched_binary is not None:
        return f"compiled dependency targets {mismatched_binary}"

    dependency_runtime = manifest.get("dependency_runtime")
    if not isinstance(dependency_runtime, dict):
        if site_dir.is_dir() and runtime_dependencies:
            return "missing dependency runtime metadata"
        return None

    cache_tag = dependency_runtime.get("cache_tag")
    if isinstance(cache_tag, str) and cache_tag != runtime_info.cache_tag:
        return f"dependency cache tag {cache_tag} != {runtime_info.cache_tag}"
    return None


def _first_mismatched_binary_tag(site_dir: Path, expected_tag: str) -> str | None:
    if not site_dir.is_dir():
        return None
    pattern = re.compile(r"\.(cpython-\d+[^.]*)\.")
    for candidate in site_dir.rglob("*.so"):
        match = pattern.search(candidate.name)
        if match and not match.group(1).startswith(expected_tag):
            return match.group(1)
    for candidate in site_dir.rglob("*.pyd"):
        match = pattern.search(candidate.name)
        if match and not match.group(1).startswith(expected_tag):
            return match.group(1)
    return None


def _run_pip(command: list[str]) -> None:
    try:
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
    except OSError as exc:
        raise PackageInstallError(f"Failed to launch pip for package dependency installation: {exc}") from exc
    if completed.returncode != 0:
        output = "\n".join(part for part in (completed.stdout.strip(), completed.stderr.strip()) if part)
        tail = "\n".join(output.splitlines()[-20:]) if output else "pip produced no output"
        raise PackageInstallError(
            "Failed to install package dependencies into the bundled Python plugin environment. "
            f"pip exited with code {completed.returncode}:\n{tail}"
        )


def _is_core_runtime_dependency(requirement: str) -> bool:
    return _requirement_name(requirement) == "scistudio"


def _requirement_name(requirement: str) -> str:
    try:
        from packaging.requirements import Requirement
    except Exception:
        raw_name = re.split(r"[\s<>=!~;\[]", requirement.strip(), maxsplit=1)[0]
    else:
        try:
            raw_name = Requirement(requirement).name
        except Exception:
            raw_name = re.split(r"[\s<>=!~;\[]", requirement.strip(), maxsplit=1)[0]
    return re.sub(r"[-_.]+", "-", raw_name).lower()


def _remove_core_runtime_shadow(target_dir: Path) -> None:
    for candidate in (
        target_dir / "scistudio",
        *target_dir.glob("scistudio-*.dist-info"),
        *target_dir.glob("scistudio-*.egg-info"),
    ):
        if candidate.is_dir():
            shutil.rmtree(candidate)
        elif candidate.exists():
            candidate.unlink()


def _extract_zip(source: Path, destination: Path) -> None:
    with zipfile.ZipFile(source) as archive:
        for member in archive.infolist():
            _validate_archive_member(destination, member.filename)
        archive.extractall(destination)


def _extract_tar(source: Path, destination: Path) -> None:
    with tarfile.open(source) as archive:
        for member in archive.getmembers():
            if member.issym() or member.islnk():
                raise PackageInstallError(f"Archive member links are not supported: {member.name}")
            _validate_archive_member(destination, member.name)
        # ``filter="data"`` is the safe extraction policy (rejects absolute
        # paths, traversal, and special files) and silences the Python 3.14
        # unfiltered-tarfile DeprecationWarning that warnings-as-error CI turns
        # into a failure on 3.12+. The parameter only exists on 3.11.4+/3.12+,
        # so older interpreters (which do not emit the warning) fall through.
        if sys.version_info >= (3, 11, 4):
            archive.extractall(destination, filter="data")
        else:
            archive.extractall(destination)


def _validate_archive_member(destination: Path, member_name: str) -> None:
    if not member_name or Path(member_name).is_absolute():
        raise PackageInstallError(f"Archive contains an unsafe path: {member_name!r}")
    target = (destination / member_name).resolve()
    destination_real = destination.resolve()
    try:
        common = os.path.commonpath([str(destination_real), str(target)])
    except ValueError as exc:
        raise PackageInstallError(f"Archive contains an unsafe path: {member_name!r}") from exc
    if common != str(destination_real):
        raise PackageInstallError(f"Archive contains a path outside its install root: {member_name!r}")


__all__ = [
    "LocalPackageDependencyRepairResult",
    "LocalPackageInstallResult",
    "PackageInstallError",
    "install_local_package",
    "repair_installed_package_dependencies",
]
