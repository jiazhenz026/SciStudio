"""Load and validate a plot's manifest and render script.

Pure helpers (no tool wiring) that the tool layer and the runtime both reuse.
Validation covers the manifest schema, path confinement, the script language and
entrypoint shape, that the bound target still exists, the declared output
formats, and runner availability. A missing R runner is reported as a warning,
never an error, so a manifest validates the same everywhere.
"""

from __future__ import annotations

import ast
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from pydantic import ValidationError

from scistudio.plot._context import PlotRuntimeContext, resolve_project_path, resolve_project_root
from scistudio.plot.models import PlotManifest
from scistudio.plot.scaffold import _SCRIPT_FILENAME, validate_plot_id
from scistudio.plot.targets import discover_targets


@dataclass
class LoadedPlot:
    """A plot resolved on disk: its id, directory, manifest, and script path.

    The result of :func:`load_plot`. It bundles everything downstream steps need to run
    or inspect a plot, with every path already resolved and confined under the
    project root.
    """

    plot_id: str
    """Id of the loaded plot (the manifest's ``id``)."""
    plot_dir: Path
    """Absolute path of the plot's ``plots/<id>/`` directory."""
    manifest_path: Path
    """Absolute path of the plot's ``plot.yaml``."""
    manifest: PlotManifest
    """The parsed, validated manifest."""
    script_path: Path
    """Absolute, confined path of the render script."""


@dataclass
class ValidationOutcome:
    """The result of validating a plot's manifest and render script.

    ``valid`` is ``True`` only when ``errors`` is empty. Errors block a run;
    warnings are advisory. ``manifest`` is populated whenever the manifest parsed,
    and ``loaded`` is set only when the plot is fully valid and ready to run.
    """

    valid: bool
    """``True`` only when there are no blocking errors."""
    errors: list[str] = field(default_factory=list)
    """Problems that must be fixed before the plot can run."""
    warnings: list[str] = field(default_factory=list)
    """Advisory notes that do not block a run (e.g. R is not installed)."""
    manifest: PlotManifest | None = None
    """The parsed manifest when it parsed, else ``None``."""
    loaded: LoadedPlot | None = None
    """The fully resolved plot when valid, else ``None``."""


class PlotNotFoundError(FileNotFoundError):
    """Raised when a plot id or path does not resolve to a manifest.

    Signals that no ``plot.yaml`` was found for the requested plot. A subclass of
    :class:`FileNotFoundError`.
    """


def resolve_manifest_path(ctx: PlotRuntimeContext, plot_id: str | None, path: str | None) -> Path:
    """Resolve the path of a plot's ``plot.yaml`` from an id or an explicit path.

    Supply exactly one of ``plot_id`` or ``path``. A ``plot_id`` resolves to
    ``plots/<plot_id>/plot.yaml``; an explicit ``path`` is taken as given. Either
    way the result is confined under the project root.

    Args:
        ctx: The injected runtime context.
        plot_id: Id of the plot, or ``None`` when passing ``path`` instead.
        path: Project-relative path to a ``plot.yaml``, or ``None`` when passing
            ``plot_id`` instead.

    Returns:
        The resolved manifest path.

    Raises:
        ValueError: When not exactly one of ``plot_id`` / ``path`` is given.
        PlotNotFoundError: When ``plot_id`` escapes the ``plots/`` directory.
        RuntimeError: When no project is currently open.
        PermissionError: When ``path`` resolves outside the project root.
    """
    if (plot_id is None) == (path is None):
        raise ValueError("provide exactly one of plot_id or path.")
    if plot_id is not None:
        validate_plot_id(plot_id)
        root = resolve_project_root(ctx)
        manifest_path = (root / "plots" / plot_id / "plot.yaml").resolve()
        # Confinement: must live under <root>/plots.
        try:
            manifest_path.relative_to((root / "plots").resolve())
        except ValueError as exc:  # pragma: no cover - validate_plot_id blocks this
            raise PlotNotFoundError(f"plot_id {plot_id!r} escapes the plots/ directory.") from exc
        return manifest_path
    return resolve_project_path(ctx, path)  # type: ignore[arg-type]


def load_plot(ctx: PlotRuntimeContext, plot_id: str | None = None, path: str | None = None) -> LoadedPlot:
    """Load and parse a plot, resolving its manifest and script paths.

    Reads ``plot.yaml`` (by id or path), validates it against the manifest schema,
    and resolves the render-script path. Use it when you need the plot ready to
    run or inspect; for a pass/fail report with messages, use
    :func:`validate_plot`.

    Args:
        ctx: The injected runtime context.
        plot_id: Id of the plot to load, or ``None`` when passing ``path``.
        path: Project-relative path to a ``plot.yaml``, or ``None`` when passing
            ``plot_id``.

    Returns:
        The resolved :class:`LoadedPlot`.

    Raises:
        ValueError: When not exactly one of ``plot_id`` / ``path`` is given, or
            the manifest is not a mapping.
        PlotNotFoundError: When the manifest file does not exist.
        pydantic.ValidationError: When the manifest fails the schema.
    """
    manifest_path = resolve_manifest_path(ctx, plot_id, path)
    if not manifest_path.exists():
        raise PlotNotFoundError(f"plot manifest not found: {manifest_path}")
    raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"plot manifest is not a mapping: {manifest_path}")
    manifest = PlotManifest.model_validate(raw)
    plot_dir = manifest_path.parent
    script_path = resolve_script_path(plot_dir, manifest.script.path, root=resolve_project_root(ctx))
    return LoadedPlot(
        plot_id=manifest.id,
        plot_dir=plot_dir,
        manifest_path=manifest_path,
        manifest=manifest,
        script_path=script_path,
    )


def resolve_script_path(plot_dir: Path, script_path: str, *, root: Path) -> Path:
    """Resolve a manifest's ``script.path`` and reject paths that escape.

    Joins the manifest's script path onto the plot directory and confirms it stays
    both inside the plot directory and inside the project root, so a render script
    can never point outside ``plots/<id>/``. Call this before reading or running
    the script.

    Args:
        plot_dir: The plot's ``plots/<id>/`` directory.
        script_path: The manifest's ``script.path`` value.
        root: The project root (the caller resolves it from the context).

    Returns:
        The resolved, confined script path.

    Raises:
        PermissionError: When the script path escapes the plot directory or the
            project root.
    """
    raw_path = Path(script_path)
    resolved = raw_path.resolve() if raw_path.is_absolute() else (plot_dir / raw_path).resolve()
    try:
        resolved.relative_to(plot_dir.resolve())
    except ValueError as exc:
        raise PermissionError(
            f"script.path {script_path!r} resolves outside the plot directory; "
            "render scripts must live inside plots/<id>/."
        ) from exc
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise PermissionError(f"script.path {script_path!r} resolves outside the project root.") from exc
    return resolved


def _rscript_available() -> bool:
    return shutil.which("Rscript") is not None


def validate_plot(ctx: PlotRuntimeContext, plot_id: str | None = None, path: str | None = None) -> ValidationOutcome:
    """Validate a plot's manifest and render script end to end.

    Checks the manifest schema, the script language and ``render(collection)``
    entrypoint, path confinement, the declared output formats, and that the bound
    target still exists. A missing R runner is reported as a warning, never an
    error, so the same manifest validates everywhere. Returns a structured report
    rather than raising, so a caller can surface the messages to the user.

    Args:
        ctx: The injected runtime context.
        plot_id: Id of the plot to validate, or ``None`` when passing ``path``.
        path: Project-relative path to a ``plot.yaml``, or ``None`` when passing
            ``plot_id``.

    Returns:
        A :class:`ValidationOutcome` whose ``valid`` flag is ``True`` only when
        there are no errors.
    """
    errors: list[str] = []
    warnings: list[str] = []

    manifest_path = resolve_manifest_path(ctx, plot_id, path)
    if not manifest_path.exists():
        return ValidationOutcome(valid=False, errors=[f"plot manifest not found: {manifest_path}"])

    try:
        raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        return ValidationOutcome(valid=False, errors=[f"plot.yaml is not valid YAML: {exc}"])
    if not isinstance(raw, dict):
        return ValidationOutcome(valid=False, errors=["plot.yaml top-level must be a mapping."])

    try:
        manifest = PlotManifest.model_validate(raw)
    except ValidationError as exc:
        return ValidationOutcome(valid=False, errors=[f"plot.yaml schema error: {_short_pydantic(exc)}"])

    # Schema version.
    if manifest.schema_version != 1:
        errors.append(f"unsupported schema_version {manifest.schema_version}; only 1 is supported.")

    # Entrypoint shape (FR-012/FR-013).
    if manifest.script.entrypoint != "render":
        errors.append(f"script.entrypoint must be 'render', got {manifest.script.entrypoint!r}.")

    # Script filename must match language convention.
    expected_script = _SCRIPT_FILENAME[manifest.script.language]
    if Path(manifest.script.path).name != expected_script:
        warnings.append(
            f"script.path {manifest.script.path!r} is unconventional for "
            f"language={manifest.script.language!r}; expected {expected_script!r}."
        )

    # Output formats (FR-018).
    if manifest.outputs.preferred_format not in manifest.outputs.allowed_formats:
        errors.append(
            f"outputs.preferred_format {manifest.outputs.preferred_format!r} "
            f"is not in allowed_formats {manifest.outputs.allowed_formats}."
        )

    plot_dir = manifest_path.parent
    root = resolve_project_root(ctx)

    # Path confinement of the script (FR-004): the script must live inside the
    # plot directory and not escape the project root.
    try:
        script_path = resolve_script_path(plot_dir, manifest.script.path, root=root)
    except PermissionError as exc:
        errors.append(str(exc))
        script_path = plot_dir.resolve()
    try:
        script_path.relative_to(plot_dir.resolve())
    except ValueError:
        errors.append(
            f"script.path {manifest.script.path!r} escapes the plot directory — "
            "the render script must live inside plots/<id>/."
        )
    else:
        try:
            script_path.relative_to(root.resolve())
        except ValueError:
            errors.append("script.path escapes the project root.")
        if not script_path.exists():
            errors.append(f"render script not found: {manifest.script.path}")
        else:
            errors.extend(_validate_render_signature(script_path, manifest))

    # Target existence (FR-021): the bound workflow path + node + output port
    # must still resolve to a discoverable target.
    target_diags = _validate_target(ctx, manifest)
    if target_diags.broken:
        errors.extend(target_diags.errors)
    warnings.extend(target_diags.warnings)

    # Runner availability diagnostics (FR-021) — never fatal.
    if manifest.script.language == "r" and not _rscript_available():
        warnings.append(
            "R runner unavailable: 'Rscript' is not on PATH. The manifest is valid; "
            "run_plot_job will report a runner-unavailable status until R is installed."
        )

    valid = not errors
    return ValidationOutcome(
        valid=valid,
        errors=errors,
        warnings=warnings,
        manifest=manifest,
        loaded=LoadedPlot(
            plot_id=manifest.id,
            plot_dir=plot_dir,
            manifest_path=manifest_path,
            manifest=manifest,
            script_path=script_path,
        )
        if valid
        else None,
    )


@dataclass
class _TargetDiagnostics:
    broken: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _validate_target(ctx: PlotRuntimeContext, manifest: PlotManifest) -> _TargetDiagnostics:
    target = manifest.target
    diags = _TargetDiagnostics(broken=False)
    try:
        targets = discover_targets(ctx, workflow_path=target.workflow_path, include_unavailable=True)
    except Exception as exc:
        diags.warnings.append(f"could not discover targets for {target.workflow_path!r}: {exc}")
        return diags
    match = next(
        (t for t in targets if t.node_id == target.node_id and t.output_port == target.output_port),
        None,
    )
    if match is None:
        diags.broken = True
        diags.errors.append(
            f"broken target: node_id={target.node_id!r} output_port={target.output_port!r} "
            f"not found in {target.workflow_path!r}. The workflow/node/port may have been deleted."
        )
        return diags
    if not match.latest_output_available:
        diags.warnings.append(
            "target has no recorded output yet; run the workflow before run_plot_job, "
            "or run_plot_job will report no available collection."
        )
    return diags


def _short_pydantic(exc: ValidationError) -> str:
    parts = []
    for err in exc.errors()[:5]:
        loc = ".".join(str(p) for p in err.get("loc", ()))
        parts.append(f"{loc}: {err.get('msg', '')}")
    return "; ".join(parts)


def _validate_render_signature(script_path: Path, manifest: PlotManifest) -> list[str]:
    entrypoint = manifest.script.entrypoint
    if manifest.script.language == "python":
        try:
            tree = ast.parse(script_path.read_text(encoding="utf-8"), filename=str(script_path))
        except SyntaxError as exc:
            return [f"render script syntax error: {exc.msg} at line {exc.lineno}."]
        render_node = next(
            (node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == entrypoint),
            None,
        )
        if render_node is None:
            return [f"render script must define def {entrypoint}(collection)."]
        args = render_node.args
        positional = [*args.posonlyargs, *args.args]
        ok = (
            len(positional) == 1
            and positional[0].arg == "collection"
            and not args.defaults
            and not args.vararg
            and not args.kwonlyargs
            and not args.kw_defaults
            and not args.kwarg
        )
        if ok:
            return []
        return [
            "Python render entrypoint must be exactly def render(collection). "
            "render(collection, context) is not supported."
        ]
    if manifest.script.language == "r":
        source = script_path.read_text(encoding="utf-8")
        pattern = rf"(?s)\b{re.escape(entrypoint)}\s*(?:<-|=)\s*function\s*\((?P<formals>[^)]*)\)"
        match = re.search(pattern, source)
        if match is None:
            return [f"R render script must define {entrypoint} <- function(collection)."]
        formals = [part.strip() for part in match.group("formals").split(",") if part.strip()]
        if formals == ["collection"]:
            return []
        return [
            "R render entrypoint must be exactly render <- function(collection). "
            "render <- function(collection, context) is not supported."
        ]
    return []


__all__ = [
    "LoadedPlot",
    "PlotNotFoundError",
    "ValidationOutcome",
    "load_plot",
    "resolve_manifest_path",
    "resolve_script_path",
    "validate_plot",
]
