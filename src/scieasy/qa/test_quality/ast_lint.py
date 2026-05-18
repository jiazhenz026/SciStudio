"""AST-level anti-pattern detector for test files (TC-1F.1, ADR-043 §4.2).

The public entry point :func:`check_test_file` parses one Python test
file and emits a :class:`scieasy.qa.schemas.report.Finding` per detected
anti-pattern. The ten anti-patterns are defined in
:class:`scieasy.qa.schemas.test_quality.AntiPattern` and the §4.2.1 table;
each pattern is implemented by a dedicated ``_detect_<slug>`` helper
walking the AST of one ``def test_*`` function.

Severity mapping
----------------

Per ADR-043 §4.2 the AST checks are "flagged as errors". The reviewer
intent in §4.3 distinguishes structural blockers (no assertion at all,
mocking the subject, name-claim mismatch, self-confirming fixtures) from
soft signals (magic numbers, snapshot reasoning). This module maps:

* ``error`` — :data:`_HARD_ERRORS` (semantic blockers).
* ``warning`` — everything else (style/heuristic; reviewer judgement).

Rule IDs use the ``TQAST-<slug>`` namespace so downstream tooling
(CI annotations, baseline files) can filter unambiguously.

Limitations
-----------

* The walker only inspects functions whose name starts with ``test_`` at
  module top-level or inside a ``class Test*`` container — pytest's
  collection conventions.
* ``hardcoded-magic-without-comment`` recognises numeric / string literals
  appearing inside a comparison and looks for an attached comment on the
  same source line. The heuristic is intentionally lenient (warning
  severity) to avoid false-positives on common idioms like ``assert
  len(x) == 0``.
* ``snapshot-without-reasoning`` matches calls whose attribute is
  ``snapshot`` or whose target name contains ``snapshot``; a single-line
  ``# reason: …`` comment satisfies the rule.
* ``test-also-provides-ground-truth`` is detected when a fixture / local
  assignment derives the expected value by calling the symbol under
  test — see :func:`_detect_test_also_provides_ground_truth` for the
  precise condition (callee name overlaps with an asserted comparison
  operand).

Out-of-scope (Phase 3)
----------------------

* ``# noqa: TQAST-<rule>`` per-line suppression. TODO(#1144) for follow-up.
* Custom severity overrides via ``pyproject.toml [tool.scieasy.qa.test_quality]``.
* Whole-repo walker with parallel processing — the :func:`check_test_file`
  entry point intentionally takes a single path; orchestration belongs
  in the CLI shim (``scripts/audit/test_quality.py``).
"""

from __future__ import annotations

import ast
import re
import tokenize
from io import BytesIO
from pathlib import Path

from scieasy.qa.schemas.report import Finding, Severity
from scieasy.qa.schemas.test_quality import AntiPattern

#: Anti-patterns that are structural correctness blockers (severity=error).
_HARD_ERRORS: frozenset[AntiPattern] = frozenset(
    {
        AntiPattern.NO_ASSERT,
        AntiPattern.MOCKS_THE_SUBJECT,
        AntiPattern.TEST_NAME_CLAIM_MISMATCH,
        AntiPattern.TEST_ALSO_PROVIDES_GROUND_TRUTH,
        AntiPattern.ASSERTS_ON_MOCK_CALL_ONLY,
    }
)

#: Threshold for the ``excessive-mocks`` heuristic (§4.2.1: ">6 mocks").
_EXCESSIVE_MOCKS_THRESHOLD = 6

#: Names of helpers that, when ``pytest.raises``/``pytest.warns`` calls
#: lack a ``match=`` keyword, trigger ``raises-without-match``.
_RAISES_HELPERS: frozenset[str] = frozenset({"raises", "warns"})

#: ``unittest.mock``-style call-count assertions. These are the variants the
#: ``asserts-on-mock-call-count-only`` detector collects AND the ones it
#: excludes from the "other meaningful assertions" check — the sets must
#: match (Codex review #1148 P1 fix).
_MOCK_CALL_ASSERT_NAMES: frozenset[str] = frozenset(
    {
        "assert_called",
        "assert_called_once",
        "assert_called_with",
        "assert_called_once_with",
        "assert_any_call",
        "assert_has_calls",
        "assert_not_called",
    }
)

#: Substrings that mark a call/identifier as a mock object.
_MOCK_NAME_TOKENS: tuple[str, ...] = ("mock", "Mock", "MagicMock", "AsyncMock")

#: Identifier substrings that mark a call/attribute as a snapshot operation.
_SNAPSHOT_NAME_TOKENS: tuple[str, ...] = ("snapshot", "Snapshot")

#: Pytest fixture-mark and the dataclass-style assert-style class-name patterns
#: are *not* part of the heuristic set; reviewer-judgement only.

#: Regex matching an inline comment that explicitly notes a magic-number /
#: snapshot rationale.  The keyword list is intentionally loose to keep the
#: rule a warning rather than a brittle error.
_RATIONALE_COMMENT_RE = re.compile(
    r"#\s*(reason|because|why|rationale|note|expect|locks?|snapshot|known)",
    re.IGNORECASE,
)


def _severity_for(pattern: AntiPattern) -> Severity:
    """Return the canonical severity for one anti-pattern."""
    return Severity.ERROR if pattern in _HARD_ERRORS else Severity.WARNING


def _make_finding(
    *,
    pattern: AntiPattern,
    file: str,
    line: int,
    symbol: str,
    message: str,
    suggested_fix: str | None = None,
) -> Finding:
    """Construct a :class:`Finding` for an anti-pattern occurrence."""
    return Finding(
        rule_id=f"TQAST-{pattern.value}",
        severity=_severity_for(pattern),
        drift_class=None,
        file=file,
        line=line,
        symbol=symbol,
        message=message,
        suggested_fix=suggested_fix,
    )


# --------------------------------------------------------------------------- #
# Helpers — AST node introspection                                            #
# --------------------------------------------------------------------------- #


def _is_test_function(node: ast.AST) -> bool:
    """Return True iff ``node`` is a ``def test_*`` / ``async def test_*``."""
    return isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name.startswith("test_")


def _iter_pytest_collectable_tests(
    tree: ast.Module,
) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    """Yield only test functions pytest would actually collect.

    Pytest's default collection rules:

    * Module-level ``def test_*`` / ``async def test_*``.
    * Methods on a ``class Test*`` (no ``__init__``).

    Nested helpers (``def test_helper`` inside a non-test function) and
    methods on non-``Test*`` classes are intentionally skipped — they
    are not collected as tests so the AST detectors must not flag them.
    Codex review #1148 P2 fix.
    """
    out: list[ast.FunctionDef | ast.AsyncFunctionDef] = []
    for node in tree.body:
        if _is_test_function(node):
            assert isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
            out.append(node)
        elif isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
            for inner in node.body:
                if _is_test_function(inner):
                    assert isinstance(inner, ast.FunctionDef | ast.AsyncFunctionDef)
                    out.append(inner)
    return out


def _qualified_name(expr: ast.AST) -> str:
    """Render a dotted attribute chain to a string (best-effort)."""
    if isinstance(expr, ast.Attribute):
        return f"{_qualified_name(expr.value)}.{expr.attr}"
    if isinstance(expr, ast.Name):
        return expr.id
    if isinstance(expr, ast.Call):
        return _qualified_name(expr.func)
    return ""


def _is_assertion_node(node: ast.AST) -> bool:
    """Return True iff ``node`` is a meaningful assertion expression.

    Recognises plain ``assert`` statements, ``pytest.raises``/``pytest.warns``
    context managers, and ``unittest`` assert methods.
    """
    if isinstance(node, ast.Assert):
        return True
    if isinstance(node, ast.With | ast.AsyncWith):
        for item in node.items:
            qn = _qualified_name(item.context_expr)
            if qn.endswith("pytest.raises") or qn.endswith("pytest.warns"):
                return True
            short = qn.rsplit(".", 1)[-1]
            if short in _RAISES_HELPERS:
                return True
        return False
    if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
        callee = _qualified_name(node.value.func)
        short = callee.rsplit(".", 1)[-1]
        # unittest-style asserts (self.assertEqual, self.assertTrue, …) count
        # as meaningful; the mock-call-count variants do NOT — they are the
        # ones the dedicated detector targets.
        if short.startswith("assert") and short not in _MOCK_CALL_ASSERT_NAMES:
            return True
    return False


def _walk_calls(node: ast.AST) -> list[ast.Call]:
    """Return every :class:`ast.Call` reachable from ``node``."""
    return [n for n in ast.walk(node) if isinstance(n, ast.Call)]


def _count_mocks(func: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    """Count distinct mock objects referenced in the function body."""
    seen: set[str] = set()
    for call in _walk_calls(func):
        qn = _qualified_name(call.func)
        for tok in _MOCK_NAME_TOKENS:
            if tok in qn:
                seen.add(qn)
                break
    for name in (n.id for n in ast.walk(func) if isinstance(n, ast.Name)):
        for tok in _MOCK_NAME_TOKENS:
            if tok in name:
                seen.add(name)
                break
    return len(seen)


def _line_comment_map(source: str) -> dict[int, str]:
    """Map each source line containing a comment → the comment text."""
    out: dict[int, str] = {}
    try:
        for tok in tokenize.tokenize(BytesIO(source.encode("utf-8")).readline):
            if tok.type == tokenize.COMMENT:
                out[tok.start[0]] = tok.string
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return out
    return out


def _function_under_test_candidates(func: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    """Best-effort derive the name(s) of the symbol(s) under test.

    Strategy: take the test-function name ``test_<stem>``; ``<stem>`` is
    the candidate. Splits on underscore to also match ``test_normalize_x``
    against ``normalize``.
    """
    name = func.name
    if not name.startswith("test_"):
        return set()
    stem = name[len("test_") :]
    parts = stem.split("_")
    candidates: set[str] = set()
    if stem:
        candidates.add(stem)
    if parts:
        candidates.add(parts[0])
        # Camel-case sibling for snake_case test names.
        if len(parts) > 1:
            candidates.add("".join(p.capitalize() for p in parts))
    return {c for c in candidates if c}


# --------------------------------------------------------------------------- #
# Detectors — one per anti-pattern                                            #
# --------------------------------------------------------------------------- #


def _detect_no_assert(func: ast.FunctionDef | ast.AsyncFunctionDef, file: str) -> list[Finding]:
    """``no-assert``: test function lacks any assertion form."""
    has_assert = any(_is_assertion_node(n) for n in ast.walk(func))
    if has_assert:
        return []
    return [
        _make_finding(
            pattern=AntiPattern.NO_ASSERT,
            file=file,
            line=func.lineno,
            symbol=func.name,
            message=f"test function '{func.name}' contains no assert / pytest.raises / pytest.warns",
            suggested_fix="Add an explicit assertion stating what observable behavior is verified.",
        )
    ]


def _detect_assert_not_none_only(func: ast.FunctionDef | ast.AsyncFunctionDef, file: str) -> list[Finding]:
    """``assert-not-none-only``: only assertion is ``assert X is not None``."""
    asserts = [n for n in ast.walk(func) if isinstance(n, ast.Assert)]
    if not asserts:
        return []
    not_none = [
        a
        for a in asserts
        if isinstance(a.test, ast.Compare)
        and len(a.test.ops) == 1
        and isinstance(a.test.ops[0], ast.IsNot)
        and len(a.test.comparators) == 1
        and isinstance(a.test.comparators[0], ast.Constant)
        and a.test.comparators[0].value is None
    ]
    if not_none and len(not_none) == len(asserts):
        return [
            _make_finding(
                pattern=AntiPattern.ASSERT_NOT_NONE_ONLY,
                file=file,
                line=asserts[0].lineno,
                symbol=func.name,
                message=(
                    f"test '{func.name}' only asserts non-None; specify what the value should equal / contain / match."
                ),
                suggested_fix="Replace 'assert x is not None' with a positive assertion about x's expected value.",
            )
        ]
    return []


def _detect_mocks_the_subject(func: ast.FunctionDef | ast.AsyncFunctionDef, file: str) -> list[Finding]:
    """``mocks-the-subject``: the symbol under test is itself patched."""
    candidates = _function_under_test_candidates(func)
    if not candidates:
        return []
    findings: list[Finding] = []
    for call in _walk_calls(func):
        qn = _qualified_name(call.func)
        short = qn.rsplit(".", 1)[-1]
        if short not in {"patch", "patch_object", "patch.object"} and not qn.endswith(".patch"):
            continue
        if not call.args:
            continue
        arg = call.args[0]
        if not isinstance(arg, ast.Constant) or not isinstance(arg.value, str):
            continue
        target = arg.value
        tail = target.rsplit(".", 1)[-1]
        if tail in candidates or any(c in target for c in candidates):
            findings.append(
                _make_finding(
                    pattern=AntiPattern.MOCKS_THE_SUBJECT,
                    file=file,
                    line=call.lineno,
                    symbol=func.name,
                    message=(
                        f"test '{func.name}' mocks '{target}', which appears to be "
                        "the function/class under test — tautological."
                    ),
                    suggested_fix="Remove the patch; exercise the real subject and stub only its collaborators.",
                )
            )
    return findings


def _detect_asserts_on_mock_call_only(func: ast.FunctionDef | ast.AsyncFunctionDef, file: str) -> list[Finding]:
    """``asserts-on-mock-call-count-only``: only assertion is ``mock.assert_called*``."""
    bare_asserts = [n for n in ast.walk(func) if isinstance(n, ast.Assert)]
    mock_call_asserts: list[ast.Call] = []
    for call in _walk_calls(func):
        qn = _qualified_name(call.func)
        short = qn.rsplit(".", 1)[-1]
        if short in _MOCK_CALL_ASSERT_NAMES:
            mock_call_asserts.append(call)
    if mock_call_asserts and not bare_asserts:
        # Ensure no other meaningful assertions (raises/warns ctx) either —
        # i.e. an assertion that is NOT one of the mock-call asserts the
        # detector is already counting.
        other = any(
            _is_assertion_node(n)
            and not (
                isinstance(n, ast.Expr)
                and isinstance(n.value, ast.Call)
                and _qualified_name(n.value.func).rsplit(".", 1)[-1] in _MOCK_CALL_ASSERT_NAMES
            )
            for n in ast.walk(func)
        )
        if not other:
            return [
                _make_finding(
                    pattern=AntiPattern.ASSERTS_ON_MOCK_CALL_ONLY,
                    file=file,
                    line=mock_call_asserts[0].lineno,
                    symbol=func.name,
                    message=(
                        f"test '{func.name}' only verifies a mock was invoked; "
                        "no assertion on the resulting behavior or return value."
                    ),
                    suggested_fix="Add an assertion on the function-under-test's observable output, not just the mock call count.",
                )
            ]
    return []


def _detect_hardcoded_magic_without_comment(
    func: ast.FunctionDef | ast.AsyncFunctionDef,
    file: str,
    comments: dict[int, str],
) -> list[Finding]:
    """``hardcoded-magic-without-comment``: comparison vs literal w/o comment."""
    findings: list[Finding] = []
    seen_lines: set[int] = set()
    for cmp in (n for n in ast.walk(func) if isinstance(n, ast.Compare)):
        operands = [cmp.left, *cmp.comparators]
        magic: list[ast.Constant] = []
        for op in operands:
            if not isinstance(op, ast.Constant):
                continue
            if isinstance(op.value, bool):
                continue  # True/False is rarely "magic"
            if op.value is None:
                continue
            if isinstance(op.value, int | float) and op.value in {0, 1, -1}:
                continue
            if isinstance(op.value, str) and len(op.value) <= 2:
                continue
            magic.append(op)
        if not magic:
            continue
        line = cmp.lineno
        if line in seen_lines:
            continue
        # Accept an inline comment on the same line OR the preceding line.
        rationale = comments.get(line, "") or comments.get(line - 1, "")
        if rationale and not _RATIONALE_COMMENT_RE.search(rationale):
            # A comment exists but contains no rationale keyword. Still
            # accept it — author has at least annotated the line.
            continue
        if rationale:
            continue
        seen_lines.add(line)
        findings.append(
            _make_finding(
                pattern=AntiPattern.HARDCODED_MAGIC_WITHOUT_COMMENT,
                file=file,
                line=line,
                symbol=func.name,
                message=(
                    f"test '{func.name}' compares against literal {magic[0].value!r} "
                    "without an inline comment explaining its significance."
                ),
                suggested_fix="Add ``  # because <rationale>`` to the line, or extract the literal to a named constant.",
            )
        )
    return findings


def _detect_test_name_claim_mismatch(func: ast.FunctionDef | ast.AsyncFunctionDef, file: str) -> list[Finding]:
    """``test-name-claim-mismatch``: name says X, body does not assert X."""
    name = func.name
    # Look for the verb after 'test_'. Pattern: test_validates_X, test_returns_X.
    m = re.match(r"test_(validates|returns|raises|rejects|accepts|computes|parses|saves|loads|normalizes)_(.+)$", name)
    if not m:
        return []
    claim = m.group(2)
    asserts = [n for n in ast.walk(func) if isinstance(n, ast.Assert)]
    if not asserts:
        return []  # caught by no-assert
    # Render each assert and check whether the claim token appears.
    body = "\n".join(ast.unparse(a) for a in asserts)
    if claim.replace("_", "") in body.replace("_", "").lower() or claim.lower() in body.lower():
        return []
    return [
        _make_finding(
            pattern=AntiPattern.TEST_NAME_CLAIM_MISMATCH,
            file=file,
            line=func.lineno,
            symbol=func.name,
            message=(f"test '{name}' claims to verify '{claim}' but no assertion references that concept."),
            suggested_fix=f"Either rename the test to reflect what it actually checks, or add an assertion touching '{claim}'.",
        )
    ]


def _detect_raises_without_match(func: ast.FunctionDef | ast.AsyncFunctionDef, file: str) -> list[Finding]:
    """``raises-without-match``: ``pytest.raises(E)`` with no ``match=``."""
    findings: list[Finding] = []
    for ctx in (n for n in ast.walk(func) if isinstance(n, ast.With | ast.AsyncWith)):
        for item in ctx.items:
            if not isinstance(item.context_expr, ast.Call):
                continue
            qn = _qualified_name(item.context_expr.func)
            short = qn.rsplit(".", 1)[-1]
            if short not in _RAISES_HELPERS:
                continue
            kwargs = {kw.arg for kw in item.context_expr.keywords if kw.arg}
            if "match" in kwargs:
                continue
            findings.append(
                _make_finding(
                    pattern=AntiPattern.RAISES_WITHOUT_MATCH,
                    file=file,
                    line=item.context_expr.lineno,
                    symbol=func.name,
                    message=(
                        f"test '{func.name}' uses pytest.{short}(...) without a "
                        "``match=`` regex; the wrong exception/message would pass."
                    ),
                    suggested_fix='Add ``match="..."`` so the test pins the specific error condition.',
                )
            )
    return findings


def _detect_snapshot_without_reasoning(
    func: ast.FunctionDef | ast.AsyncFunctionDef,
    file: str,
    comments: dict[int, str],
) -> list[Finding]:
    """``snapshot-without-reasoning``: snapshot call lacks inline rationale."""
    findings: list[Finding] = []
    for call in _walk_calls(func):
        qn = _qualified_name(call.func)
        if not any(tok in qn for tok in _SNAPSHOT_NAME_TOKENS):
            continue
        line = call.lineno
        rationale = comments.get(line, "") or comments.get(line - 1, "")
        if rationale and _RATIONALE_COMMENT_RE.search(rationale):
            continue
        findings.append(
            _make_finding(
                pattern=AntiPattern.SNAPSHOT_WITHOUT_REASONING,
                file=file,
                line=line,
                symbol=func.name,
                message=(
                    f"test '{func.name}' calls snapshot '{qn}' without a one-line comment explaining what is locked."
                ),
                suggested_fix="Prepend ``# locks: <reason>`` so reviewers know why the snapshot is inviolable.",
            )
        )
    return findings


def _detect_excessive_mocks(func: ast.FunctionDef | ast.AsyncFunctionDef, file: str) -> list[Finding]:
    """``excessive-mocks``: >6 mocks in one test function."""
    count = _count_mocks(func)
    if count <= _EXCESSIVE_MOCKS_THRESHOLD:
        return []
    return [
        _make_finding(
            pattern=AntiPattern.EXCESSIVE_MOCKS,
            file=file,
            line=func.lineno,
            symbol=func.name,
            message=(
                f"test '{func.name}' references {count} mocks (threshold "
                f"{_EXCESSIVE_MOCKS_THRESHOLD}); the test likely binds to "
                "implementation detail rather than observable behavior."
            ),
            suggested_fix="Split the test, or replace mock-heavy paths with real collaborators / in-memory fakes.",
        )
    ]


def _detect_test_also_provides_ground_truth(func: ast.FunctionDef | ast.AsyncFunctionDef, file: str) -> list[Finding]:
    """``test-also-provides-ground-truth``: expected value derived from SUT."""
    candidates = _function_under_test_candidates(func)
    if not candidates:
        return []
    findings: list[Finding] = []
    expected_names: dict[str, int] = {}
    expected_sut_calls: dict[str, set[str]] = {}
    for stmt in ast.walk(func):
        if not isinstance(stmt, ast.Assign):
            continue
        targets = [t for t in stmt.targets if isinstance(t, ast.Name)]
        if not targets:
            continue
        for call in _walk_calls(stmt.value):
            callee = _qualified_name(call.func)
            short = callee.rsplit(".", 1)[-1]
            if short in candidates or short in {c for c in candidates}:
                for tgt in targets:
                    if "expected" in tgt.id.lower() or "want" in tgt.id.lower() or "should" in tgt.id.lower():
                        expected_names[tgt.id] = stmt.lineno
                        expected_sut_calls.setdefault(tgt.id, set()).add(short)
    # Verify the suspicious name is then used inside an assert / compared.
    used_in_assert: set[str] = set()
    for cmp in (n for n in ast.walk(func) if isinstance(n, ast.Compare)):
        for operand in (cmp.left, *cmp.comparators):
            if isinstance(operand, ast.Name) and operand.id in expected_names:
                used_in_assert.add(operand.id)
    for name in used_in_assert:
        findings.append(
            _make_finding(
                pattern=AntiPattern.TEST_ALSO_PROVIDES_GROUND_TRUTH,
                file=file,
                line=expected_names[name],
                symbol=func.name,
                message=(
                    f"test '{func.name}' derives '{name}' by calling "
                    f"{sorted(expected_sut_calls[name])[0]} (a candidate symbol-"
                    "under-test); the assertion is self-confirming."
                ),
                suggested_fix="Compute the expected value independently (hard-code, fixture, or a different implementation).",
            )
        )
    return findings


# --------------------------------------------------------------------------- #
# Public entry point                                                          #
# --------------------------------------------------------------------------- #


def check_test_file(path: Path) -> list[Finding]:
    """AST-walk a test file; emit anti-pattern findings per ADR-043 §4.2.

    Parameters
    ----------
    path:
        Filesystem path to a Python test file. Non-existent paths return
        an empty list (the caller's responsibility is to enumerate files
        from ``tests/**/*.py``). Syntax errors emit a single
        ``error``-severity finding tagged ``TQAST-no-assert`` so the
        offending file shows up in CI annotations without crashing the
        run.

    Returns
    -------
    list[Finding]
        One :class:`Finding` per anti-pattern occurrence. The list is in
        AST-walk order; callers must sort if a deterministic display
        order is required.
    """
    if not path.exists() or not path.is_file():
        return []
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        return [
            _make_finding(
                pattern=AntiPattern.NO_ASSERT,
                file=str(path).replace("\\", "/"),
                line=exc.lineno or 1,
                symbol="<module>",
                message=f"syntax error parsing test file: {exc.msg}",
            )
        ]
    file = str(path).replace("\\", "/")
    comments = _line_comment_map(source)
    findings: list[Finding] = []
    for node in _iter_pytest_collectable_tests(tree):
        findings.extend(_detect_no_assert(node, file))
        findings.extend(_detect_assert_not_none_only(node, file))
        findings.extend(_detect_mocks_the_subject(node, file))
        findings.extend(_detect_asserts_on_mock_call_only(node, file))
        findings.extend(_detect_hardcoded_magic_without_comment(node, file, comments))
        findings.extend(_detect_test_name_claim_mismatch(node, file))
        findings.extend(_detect_raises_without_match(node, file))
        findings.extend(_detect_snapshot_without_reasoning(node, file, comments))
        findings.extend(_detect_excessive_mocks(node, file))
        findings.extend(_detect_test_also_provides_ground_truth(node, file))
    return findings


# TODO(#1144): per-line suppression directive (``# tq-skip: TQAST-<rule>``) —
#   Phase 3 refinement. Out of scope per ADR-043 §4.2 (Phase 1 ships the
#   detector; reviewer-tuning knobs land in Phase 3 alongside the hard-gate
#   flip).
#   Followup: open a fresh issue when Phase 3 cleanup-track work begins.
