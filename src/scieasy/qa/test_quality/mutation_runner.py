"""Mutation-testing runner shim (TC-1F.3, ADR-043 §4.5).

The public entry point :func:`run_targeted` invokes ``mutmut`` scoped to a
caller-supplied list of changed modules, parses the per-module mutation
score from ``mutmut results``, compares each score to the ADR-043 §4.5
path-target table, and emits one :class:`scieasy.qa.schemas.report.Finding`
per below-target module.

The implementation is intentionally a thin shim around the ``mutmut``
CLI:

1. For every entry in ``changed_modules`` resolve a §4.5 path-prefix
   target (``_resolve_threshold``) — modules outside the four named
   prefixes are skipped with an INFO-level finding (no target to apply).
2. Spawn ``mutmut run --paths-to-mutate <module>``; on success spawn
   ``mutmut results --json`` and parse the kill/survive/timeout counts
   per :class:`scieasy.qa.schemas.test_quality.MutationScoreResult`.
3. Compute ``score = killed / total`` (a total of zero yields
   ``score = 1.0`` — no mutations to kill is trivially "passing"; the
   pattern is documented in the ADR-043 §4.5 baseline JSON conventions).
4. If the score falls below the path-target threshold the function emits
   a finding with rule-ID ``TQMUT-below-threshold`` and severity
   :class:`Severity.WARNING` (Phase 1 is report-only per §4.5 table
   "Phase 1: report; Phase 3: hard gate").

Baseline JSON (``baseline_path``)
---------------------------------

The optional ``baseline_path`` argument points to a JSON file in the
shape::

    {
      "src/scieasy/qa": {"score": 0.92, "captured_at": "..."},
      "src/scieasy/core": {"score": 0.87, "captured_at": "..."},
      ...
    }

When provided, a per-module score that REGRESSES below the baseline
(even if still above the §4.5 target) emits an INFO-level finding under
rule-ID ``TQMUT-baseline-regression`` so trend dashboards can pick it
up. Phase 1 keeps these findings non-blocking; Phase 3 cleanup-track
work will promote them. See ADR-043 §4.5 "ratchet on this single axis
only".

Platform constraint (ADR-043 §4.5)
----------------------------------

``mutmut`` requires ``os.fork()`` and therefore runs cleanly only on
Linux / macOS. The runner detects ``sys.platform == "win32"`` early and
returns one finding under rule-ID ``TQMUT-unavailable-platform`` at
severity :class:`Severity.INFO`; the CI workflow gates the mutation job
to ``runs-on: ubuntu-latest`` per §4.5 "CI mutation runs on Linux
runners only".

Subprocess boundary
-------------------

All ``mutmut`` invocations go through :func:`_run_capture` — the same
seam used by ``test_first_check.py`` — so unit tests under
``tests/qa/test_mutation_runner.py`` can patch one symbol to feed
synthetic JSON into the parser. The shim never imports ``mutmut`` at
module load time; the dependency is dev-only per ``pyproject.toml``
and the runtime tree must function without it installed.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

from scieasy.qa.schemas.report import Finding, Severity

#: ADR-043 §4.5 path-prefix → mutation-score target. Ordered most-specific
#: first so :func:`_resolve_threshold` returns the right entry for
#: paths under ``src/scieasy/qa/audit/`` (matches ``src/scieasy/qa``).
_THRESHOLDS: tuple[tuple[str, float], ...] = (
    ("src/scieasy/qa", 0.90),
    ("src/scieasy/core", 0.85),
    ("src/scieasy/blocks", 0.75),
    ("src/scieasy/engine", 0.75),
    ("src/scieasy/api", 0.75),
    ("src/scieasy/workflow", 0.75),
    ("src/scieasy/ai", 0.70),
)

#: Rule-IDs emitted by this module — kept module-level so callers can
#: filter SARIF / annotations without re-importing the source strings.
_RULE_BELOW_THRESHOLD = "TQMUT-below-threshold"
_RULE_BASELINE_REGRESSION = "TQMUT-baseline-regression"
_RULE_UNAVAILABLE_PLATFORM = "TQMUT-unavailable-platform"
_RULE_TOOL_MISSING = "TQMUT-tool-missing"
_RULE_RUN_FAILED = "TQMUT-run-failed"
_RULE_PARSE_FAILED = "TQMUT-parse-failed"
_RULE_NO_TARGET = "TQMUT-no-target"

#: Set of all rule-IDs this module can emit. Exposed for downstream
#: filtering / docs; tests assert membership when checking finding
#: classification.
RULE_IDS: frozenset[str] = frozenset(
    {
        _RULE_BELOW_THRESHOLD,
        _RULE_BASELINE_REGRESSION,
        _RULE_UNAVAILABLE_PLATFORM,
        _RULE_TOOL_MISSING,
        _RULE_RUN_FAILED,
        _RULE_PARSE_FAILED,
        _RULE_NO_TARGET,
    }
)


def _run_capture(args: Sequence[str]) -> tuple[int, str, str]:
    """Run ``args`` capturing stdout/stderr; returns ``(rc, stdout, stderr)``.

    Single subprocess seam — unit tests monkeypatch this name. Matches
    the pattern used by ``test_first_check._run_capture`` so the two
    shims share auditable surface area.
    """
    if not args:
        return 2, "", "no command"
    if shutil.which(args[0]) is None:
        return 2, "", f"{args[0]} not on PATH"
    proc = subprocess.run(
        list(args),
        capture_output=True,
        text=True,
        check=False,
        encoding="utf-8",
        errors="replace",
    )
    return proc.returncode, proc.stdout or "", proc.stderr or ""


def _is_windows() -> bool:
    """Return True iff running on Windows.

    Wrapped so tests can monkeypatch the platform check without poking
    at :mod:`sys` directly.
    """
    return sys.platform == "win32"


def _normalise_module(module: str) -> str:
    """Normalise a module path to forward-slash form.

    Windows callers may pass ``src\\scieasy\\qa\\audit`` — the threshold
    table uses forward slashes (the form `git diff --name-only` emits
    in CI). Trailing slashes and ``./`` prefixes are also stripped.
    """
    cleaned = module.replace("\\", "/").strip()
    while cleaned.startswith("./"):
        cleaned = cleaned[2:]
    return cleaned.rstrip("/")


def _resolve_threshold(module: str) -> float | None:
    """Return the §4.5 mutation-score target for ``module``, or None.

    A return of ``None`` means the module is outside the four named
    path families (``scripts/``, ``tools/``, ``tests/`` itself per the
    §4.5 table "Other — no target"); callers emit a non-actionable INFO
    finding rather than a threshold comparison.
    """
    norm = _normalise_module(module)
    for prefix, target in _THRESHOLDS:
        if norm == prefix or norm.startswith(prefix + "/"):
            return target
    return None


def _compute_score(killed: int, survived: int, timeout: int) -> tuple[int, float]:
    """Return ``(total, score)`` where ``score = killed / total``.

    A zero-mutation total returns ``score = 1.0`` (nothing to kill is
    trivially passing — see module docstring "Baseline JSON" section).
    """
    total = killed + survived + timeout
    if total == 0:
        return 0, 1.0
    return total, killed / total


def _invoke_mutmut(module: str) -> tuple[int, str, str]:
    """Spawn ``mutmut run --paths-to-mutate <module>``.

    Returns the captured ``(rc, stdout, stderr)`` triple. Exit code 2
    from ``mutmut run`` historically means "some mutants survived";
    the runner treats both 0 and 2 as "produced results" and lets the
    parser decide. Any other return code becomes a ``TQMUT-run-failed``
    finding.
    """
    return _run_capture(["mutmut", "run", "--paths-to-mutate", module])


def _fetch_results_json() -> tuple[int, str, str]:
    """Spawn ``mutmut results --json``.

    Newer mutmut versions support ``--json``; the parser tolerates the
    fallback ``mutmut results`` plaintext too (split across whitespace
    for ``Killed: N Survived: M Timeout: K`` headers — see
    :func:`_parse_results_payload`).
    """
    return _run_capture(["mutmut", "results", "--json"])


def _parse_results_payload(payload: str) -> tuple[int, int, int] | None:
    """Parse ``mutmut results`` output → ``(killed, survived, timeout)``.

    Supports both the modern JSON form (``{"killed": …, "survived": …,
    "timeout": …}``) and the historical plaintext form that prints
    ``Killed: N`` / ``Survived: M`` / ``Timeout: K`` on separate lines.
    Returns ``None`` on unparseable input so callers emit a
    ``TQMUT-parse-failed`` finding.
    """
    payload = payload.strip()
    if not payload:
        return None

    # Modern JSON form.
    try:
        data = json.loads(payload)
        if isinstance(data, dict):
            killed = int(data.get("killed", 0))
            survived = int(data.get("survived", 0))
            # Accept either "timeout" (modern) or "timed_out" (older mutmut).
            timeout_raw = data.get("timeout")
            if timeout_raw is None:
                timeout_raw = data.get("timed_out", 0)
            timeout = int(timeout_raw)
            return killed, survived, timeout
    except (json.JSONDecodeError, TypeError, ValueError):
        pass

    # Plaintext fallback: scan for "Killed: N" / "Survived: M" / "Timeout: K".
    killed = survived = timeout = 0
    found_any = False
    for line in payload.splitlines():
        cleaned = line.strip().lower()
        if cleaned.startswith("killed:"):
            try:
                killed = int(cleaned.split(":", 1)[1].strip())
                found_any = True
            except ValueError:
                continue
        elif cleaned.startswith("survived:"):
            try:
                survived = int(cleaned.split(":", 1)[1].strip())
                found_any = True
            except ValueError:
                continue
        elif cleaned.startswith("timeout:") or cleaned.startswith("timed out:"):
            try:
                timeout = int(cleaned.split(":", 1)[1].strip())
                found_any = True
            except ValueError:
                continue
    if found_any:
        return killed, survived, timeout
    return None


def _load_baseline(baseline_path: Path) -> dict[str, float]:
    """Load ``baseline_path`` JSON → ``{module_prefix: score}`` map.

    A missing file is not an error — returns an empty dict (the §4.5
    ratchet rule is a soft signal; absent baseline means no regression
    can be detected and that is fine). Malformed JSON is logged via a
    raised exception which the caller turns into a ``TQMUT-parse-failed``
    finding under the ``baseline`` pseudo-module.
    """
    if not baseline_path.is_file():
        return {}
    raw = baseline_path.read_text(encoding="utf-8")
    data = json.loads(raw)
    out: dict[str, float] = {}
    if not isinstance(data, dict):
        return out
    for key, value in data.items():
        if isinstance(value, (int, float)):
            out[str(key)] = float(value)
            continue
        if isinstance(value, dict) and "score" in value:
            inner = value["score"]
            if isinstance(inner, (int, float)):
                out[str(key)] = float(inner)
    return out


def _baseline_score_for(module: str, baseline: dict[str, float]) -> float | None:
    """Look up ``module``'s baseline score by exact key or longest matching prefix.

    Mirrors :func:`_resolve_threshold` semantics so callers don't have
    to maintain two prefix tables. Returns ``None`` if no key matches.
    """
    norm = _normalise_module(module)
    if norm in baseline:
        return baseline[norm]
    best_prefix = ""
    best_score: float | None = None
    for key, score in baseline.items():
        norm_key = _normalise_module(key)
        matches = norm == norm_key or norm.startswith(norm_key + "/")
        if matches and len(norm_key) > len(best_prefix):
            best_prefix = norm_key
            best_score = score
    return best_score


def _windows_unavailable_finding() -> Finding:
    """Emit the singleton finding for the Windows-platform path."""
    return Finding(
        rule_id=_RULE_UNAVAILABLE_PLATFORM,
        severity=Severity.INFO,
        drift_class=None,
        file=".",
        line=None,
        symbol=None,
        message=(
            "mutmut requires os.fork() and is not available on Windows; "
            "ADR-043 §4.5 confines CI mutation runs to Linux runners. "
            "Windows contributors should use WSL or skip local mutation "
            "runs (the CI gate is authoritative)."
        ),
        suggested_fix=(
            "Run the mutation suite from a Linux/macOS shell, or use WSL "
            "on Windows. See docs/contributing/reference/mutation-testing.md."
        ),
    )


def _tool_missing_finding() -> Finding:
    """Emit the singleton finding for missing ``mutmut`` binary."""
    return Finding(
        rule_id=_RULE_TOOL_MISSING,
        severity=Severity.INFO,
        drift_class=None,
        file=".",
        line=None,
        symbol=None,
        message=("mutmut not on PATH. Install via the dev extras: `pip install -e .[dev]`."),
        suggested_fix="`pip install mutmut>=2.4` or `pip install -e .[dev]`.",
    )


def _below_threshold_finding(
    module: str,
    score: float,
    threshold: float,
    *,
    total: int,
    killed: int,
    survived: int,
    timeout: int,
) -> Finding:
    """Build a ``TQMUT-below-threshold`` finding for ``module``."""
    return Finding(
        rule_id=_RULE_BELOW_THRESHOLD,
        severity=Severity.WARNING,
        drift_class=None,
        file=module,
        line=None,
        symbol=None,
        message=(
            f"mutation score {score:.3f} below ADR-043 §4.5 target "
            f"{threshold:.2f} for path '{module}' "
            f"(killed={killed}, survived={survived}, timeout={timeout}, "
            f"total={total})."
        ),
        suggested_fix=(
            "Inspect surviving mutants via `mutmut show` and add tests "
            "that fail when the production code is mutated. Phase 1 is "
            "report-only; Phase 3 promotes this finding to a hard gate."
        ),
        git_evidence=f"score={score:.3f},target={threshold:.2f}",
    )


def _regression_finding(module: str, score: float, baseline: float) -> Finding:
    """Build a ``TQMUT-baseline-regression`` finding for ``module``."""
    return Finding(
        rule_id=_RULE_BASELINE_REGRESSION,
        severity=Severity.INFO,
        drift_class=None,
        file=module,
        line=None,
        symbol=None,
        message=(
            f"mutation score {score:.3f} regressed below baseline "
            f"{baseline:.3f} for path '{module}'. Above-target overall "
            f"but trend is negative."
        ),
        suggested_fix=(
            "Identify the test(s) that previously killed the now-surviving mutants. See ADR-043 §4.5 ratchet rule."
        ),
        git_evidence=f"score={score:.3f},baseline={baseline:.3f}",
    )


def _no_target_finding(module: str) -> Finding:
    """Build a ``TQMUT-no-target`` finding (module outside §4.5 table)."""
    return Finding(
        rule_id=_RULE_NO_TARGET,
        severity=Severity.INFO,
        drift_class=None,
        file=module,
        line=None,
        symbol=None,
        message=(
            f"module '{module}' is not covered by an ADR-043 §4.5 "
            "mutation-score target (rows: src/scieasy/{qa,core,blocks,"
            "engine,api,workflow,ai}). Mutation testing skipped."
        ),
    )


def _run_failed_finding(module: str, rc: int, stderr: str) -> Finding:
    """Build a ``TQMUT-run-failed`` finding when ``mutmut run`` errored."""
    snippet = stderr.strip().splitlines()[-1] if stderr.strip() else "(no stderr)"
    return Finding(
        rule_id=_RULE_RUN_FAILED,
        severity=Severity.WARNING,
        drift_class=None,
        file=module,
        line=None,
        symbol=None,
        message=(f"`mutmut run --paths-to-mutate {module}` exited with rc={rc}. Last stderr line: {snippet}"),
        suggested_fix="Re-run mutmut locally to inspect the failure.",
    )


def _parse_failed_finding(module: str) -> Finding:
    """Build a ``TQMUT-parse-failed`` finding for unreadable results."""
    return Finding(
        rule_id=_RULE_PARSE_FAILED,
        severity=Severity.WARNING,
        drift_class=None,
        file=module,
        line=None,
        symbol=None,
        message=(
            "could not parse `mutmut results --json` output for "
            f"'{module}'. Neither JSON nor the plaintext "
            "'Killed: N / Survived: M / Timeout: K' form recognised."
        ),
        suggested_fix=("Capture `mutmut results --json` manually and open an issue with the payload."),
    )


def _baseline_load_finding(baseline_path: Path, message: str) -> Finding:
    """Build a ``TQMUT-parse-failed`` finding for a malformed baseline JSON."""
    return Finding(
        rule_id=_RULE_PARSE_FAILED,
        severity=Severity.WARNING,
        drift_class=None,
        file=str(baseline_path),
        line=None,
        symbol="baseline",
        message=f"failed to load mutation baseline: {message}",
        suggested_fix=(
            'Verify baseline_path is a JSON file shaped {"<module>": {"score": float}} or {"<module>": float}.'
        ),
    )


def run_targeted(
    changed_modules: list[str],
    baseline_path: Path,
) -> list[Finding]:
    """Run mutmut scoped to PR-changed modules; compare to baseline.

    Implements the ADR-043 §4.7 stub signature exactly.

    Parameters
    ----------
    changed_modules:
        Project-relative paths of modules touched in the PR diff, e.g.
        ``["src/scieasy/qa/test_quality/ast_lint.py",
        "src/scieasy/core/storage/zarr_backend.py"]``. The runner does
        not deduplicate or group by package — callers (CI) are
        expected to feed the right granularity (one entry per package
        is conventional; finer is allowed).
    baseline_path:
        Path to an optional baseline JSON (see module docstring
        "Baseline JSON"). A missing file is OK and disables the
        ratchet check; a malformed file emits a single warning finding
        and otherwise proceeds with an empty baseline.

    Returns
    -------
    list[Finding]
        Empty list = all modules met their §4.5 target. Non-empty list
        carries one finding per below-target module, one per
        regression, one per platform / tool / parse failure. All
        findings are WARNING or INFO severity (Phase 1 is report-only
        per §4.5 table; Phase 3 cleanup-track work promotes
        ``TQMUT-below-threshold`` to ERROR).
    """
    # Platform guard — ADR-043 §4.5 last paragraph.
    if _is_windows():
        return [_windows_unavailable_finding()]

    # Tool guard — surface "mutmut not installed" as INFO so the CI
    # job that calls this with an empty venv produces an actionable
    # signal rather than a Python traceback.
    if shutil.which("mutmut") is None:
        return [_tool_missing_finding()]

    findings: list[Finding] = []

    # Baseline JSON parsing — malformed baseline is non-fatal.
    try:
        baseline = _load_baseline(baseline_path)
    except (json.JSONDecodeError, OSError, UnicodeDecodeError) as exc:
        findings.append(_baseline_load_finding(baseline_path, str(exc)))
        baseline = {}

    for module in changed_modules:
        threshold = _resolve_threshold(module)
        if threshold is None:
            findings.append(_no_target_finding(module))
            continue

        rc, _stdout, stderr = _invoke_mutmut(module)
        # ``mutmut run`` returns 0 when all mutants killed and 2 when
        # some survived — both are "results produced". Other codes
        # indicate a tooling failure (config error, syntax error in
        # subject code, …).
        if rc not in (0, 2):
            findings.append(_run_failed_finding(module, rc, stderr))
            continue

        rc_results, results_stdout, _results_stderr = _fetch_results_json()
        if rc_results not in (0, 2):
            findings.append(_run_failed_finding(module, rc_results, _results_stderr))
            continue

        parsed = _parse_results_payload(results_stdout)
        if parsed is None:
            findings.append(_parse_failed_finding(module))
            continue

        killed, survived, timeout = parsed
        total, score = _compute_score(killed, survived, timeout)

        if score < threshold:
            findings.append(
                _below_threshold_finding(
                    module,
                    score,
                    threshold,
                    total=total,
                    killed=killed,
                    survived=survived,
                    timeout=timeout,
                )
            )
            # Even when below-target we still record a regression if
            # the baseline existed and was lower — useful for telling
            # "regressing further" vs "stable below target" apart.

        baseline_score = _baseline_score_for(module, baseline)
        # Use a small tolerance (1e-6) so float round-trip through
        # JSON doesn't create spurious regressions when the score is
        # numerically identical.
        if baseline_score is not None and score < baseline_score - 1e-6:
            findings.append(_regression_finding(module, score, baseline_score))

    return findings


# TODO(#1144): Per-PR baseline-update flag. Currently each PR consumes
#   ``baseline_path`` read-only; a future flag should let the
#   release-train ratchet job WRITE the new high-water mark back to
#   the file.
#   Out of scope per ADR-043 §4.5 "Phase 1 introduced; Phase 3
#   enforced" — baseline-management UX is a Phase 3 cleanup-track
#   responsibility.
#   Followup: open a fresh issue at Phase 3 kickoff.

# TODO(#1145): Cross-runtime install of the test-author skill body
#   (Codex / Cursor / Aider / Gemini trees) belongs in 1H sub-PR 3
#   (``agent_provisioning.qa_skills``). The current sub-PR mirrors
#   the source body to ``.claude/skills/test-author/SKILL.md`` for
#   immediate Claude Code use only.
#   Followup: 1H sub-PR 3 dispatch.
