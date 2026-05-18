"""Property-based tests for test_quality public surface (TC-1F.4, ADR-043 §4.1).

This file establishes the `hypothesis` integration for the cascade. The
properties exercised here are deliberately scoped to the **public, pure
helpers** of :mod:`scieasy.qa.test_quality.mutation_runner` — the
threshold lookup, score arithmetic, and results-parsing primitives.

Per ADR-043 §4.1 property-tests are required for "pure transforms,
schemas, parsers, serializers, deterministic invariants" — every
function tested here meets that bar. The subprocess-bound orchestration
of ``run_targeted`` is NOT property-tested (it's side-effectful glue;
unit tests in ``test_mutation_runner.py`` cover its branches).

This file is the seed: future Phase 3 cleanup-track work will retrofit
property tests onto 1F.1 / 1F.2 surface. That work is out of scope for
this sub-PR per the cascade dispatch prompt.
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from scieasy.qa.test_quality import mutation_runner as mr

# --------------------------------------------------------------------------- #
# Strategies                                                                  #
# --------------------------------------------------------------------------- #

# Non-negative counts bounded so total computation stays well inside
# float-precision territory.
_counts = st.integers(min_value=0, max_value=10_000)

# Threshold table prefixes, used by `_resolve_threshold` property below.
_threshold_prefixes = st.sampled_from([prefix for prefix, _ in mr._THRESHOLDS])

# Suffix path appended to a prefix to verify nested-path inheritance.
_path_suffix = st.text(
    alphabet=st.characters(
        whitelist_categories=("Ll", "Lu", "Nd"),
        whitelist_characters="_/.",
    ),
    min_size=1,
    max_size=20,
).filter(lambda s: "//" not in s and not s.startswith("/"))


# --------------------------------------------------------------------------- #
# _compute_score invariants                                                    #
# --------------------------------------------------------------------------- #


@given(killed=_counts, survived=_counts, timeout=_counts)
@settings(max_examples=200)
def test_compute_score_returns_value_in_unit_interval(killed: int, survived: int, timeout: int) -> None:
    """`_compute_score` always returns a score in [0, 1].

    Mutation-score is a probability ratio by construction; any
    overflow / negative path is a bug. Property-tested rather than
    case-tested because the function is a pure 3-arg arithmetic
    primitive — the search space is well-suited to hypothesis.
    """
    _total, score = mr._compute_score(killed, survived, timeout)
    assert 0.0 <= score <= 1.0


@given(killed=_counts, survived=_counts, timeout=_counts)
@settings(max_examples=200)
def test_compute_score_total_equals_sum(killed: int, survived: int, timeout: int) -> None:
    """Returned ``total`` equals ``killed + survived + timeout``.

    The §4.5 baseline JSON shape relies on this denormalisation
    being consistent — the schema's structural-only validator
    (TC-1A.8 manager default) trusts the caller, so the caller
    must be right.
    """
    total, _score = mr._compute_score(killed, survived, timeout)
    assert total == killed + survived + timeout


@given(killed=st.integers(min_value=1, max_value=10_000))
@settings(max_examples=100)
def test_compute_score_pure_killed_is_one(killed: int) -> None:
    """All-killed mutation runs always score 1.0.

    Pinning this invariant catches off-by-one errors in the divisor
    (e.g. dividing by ``killed + survived`` only, dropping timeouts
    — a real-world drift mode in mutmut wrappers).
    """
    _total, score = mr._compute_score(killed, 0, 0)
    assert score == 1.0


# --------------------------------------------------------------------------- #
# _resolve_threshold invariants                                                #
# --------------------------------------------------------------------------- #


@given(prefix=_threshold_prefixes)
@settings(max_examples=50)
def test_resolve_threshold_exact_prefix_returns_table_value(prefix: str) -> None:
    """Every prefix in the §4.5 table resolves to its tabled value.

    Property invariant: the table is its own ground truth. If the
    helper drops or rewrites an entry the property fails immediately.
    """
    expected = dict(mr._THRESHOLDS)[prefix]
    assert mr._resolve_threshold(prefix) == expected


@given(prefix=_threshold_prefixes, suffix=_path_suffix)
@settings(max_examples=200)
def test_resolve_threshold_nested_paths_inherit_prefix(prefix: str, suffix: str) -> None:
    """A nested module under any §4.5 prefix inherits that prefix's target.

    Property invariant: directory-boundary matching MUST extend the
    threshold to every descendant — otherwise the per-PR diff (which
    typically names files, not packages) would silently fall through
    to "no target" and skip mutation testing on the very code that
    changed.
    """
    expected = dict(mr._THRESHOLDS)[prefix]
    nested = f"{prefix}/{suffix}"
    # Direct nested form, plus normalised variants the runner accepts.
    assert mr._resolve_threshold(nested) == expected
    assert mr._resolve_threshold(f"./{nested}") == expected
    # Backslash variant — Windows callers in CI sometimes pass these.
    assert mr._resolve_threshold(nested.replace("/", "\\")) == expected


@given(suffix=_path_suffix)
@settings(max_examples=100)
def test_resolve_threshold_unrelated_paths_return_none(suffix: str) -> None:
    """Paths outside the four §4.5 families resolve to None.

    Property invariant: the "Other — no target" row in §4.5 must not
    be silently overridden by a prefix-collision (e.g. a hypothetical
    ``scripts/scieasy/qa`` substring inside ``scripts/``).
    """
    # `scripts/` is explicitly cited in §4.5 as a no-target zone.
    candidate = f"scripts/{suffix}"
    assert mr._resolve_threshold(candidate) is None


# --------------------------------------------------------------------------- #
# Parser round-trip invariants                                                 #
# --------------------------------------------------------------------------- #


@given(killed=_counts, survived=_counts, timeout=_counts)
@settings(max_examples=100)
def test_parse_results_payload_json_roundtrip(killed: int, survived: int, timeout: int) -> None:
    """Any valid mutmut JSON payload round-trips through the parser exactly.

    Property invariant: the parser must accept its own canonical form
    losslessly — otherwise the runner's score computation would drift
    against the mutmut tool over time.
    """
    import json as _json

    payload = _json.dumps({"killed": killed, "survived": survived, "timeout": timeout})
    parsed = mr._parse_results_payload(payload)
    assert parsed == (killed, survived, timeout)


@given(killed=_counts, survived=_counts, timeout=_counts)
@settings(max_examples=100)
def test_parse_results_payload_plaintext_roundtrip(killed: int, survived: int, timeout: int) -> None:
    """The plaintext form ``Killed: N / Survived: M / Timeout: K`` round-trips.

    Property invariant: older mutmut versions emit plaintext; this
    fallback must be exact-round-trip with the modern JSON form so
    the score is independent of which mutmut version is installed.
    """
    payload = f"Killed: {killed}\nSurvived: {survived}\nTimeout: {timeout}\n"
    parsed = mr._parse_results_payload(payload)
    assert parsed == (killed, survived, timeout)
