"""ADR-034 Success Criteria, made mechanically checkable (issue #1994).

Spec §5 states four outcomes that a human can only verify by grepping and that
therefore rot the moment someone stops grepping:

* "Per-provider knowledge exists in exactly one backend module; a repository
  search for a provider key outside the registry, tests, and documentation
  returns no spawn, status, or validation logic."
* "The frontend declares the provider type exactly once and contains no
  hand-maintained list of agent provider keys or labels."
* "No test asserts a hardcoded two-provider set."
* Spec §1: "The ``if provider == "claude-code" / elif provider == "codex"``
  chains must be removed rather than extended."

This module turns each into a test that scans the source tree, so a regression
fails CI instead of surviving until the next reviewer happens to look.

**Why allowlists rather than loose patterns.** Three literals legitimately
survive, each for a reason recorded in the spec or in an implementer's TODO. A
pattern broad enough to tolerate them by accident would also tolerate a real
regression, so every survivor is named individually, with its key and its
justification, and anything else fails. Widening an allowlist is a deliberate,
reviewable edit; that is the point.

**Scope of the backend guard.** Success Criterion wording is "no *spawn,
status, or validation* logic", so the guard covers exactly the modules that own
those three responsibilities (:data:`_SPAWN_STATUS_VALIDATION_MODULES`).
``src/scistudio/cli/install.py`` is deliberately outside it: it holds genuinely
per-provider *installation* facts (Codex's config is TOML while the others are
JSON; only Claude Code has a SciStudio-sanctioned user-scope config file), which
model which user-owned file SciStudio may write on the user's behalf rather than
what a CLI reads at spawn time. Spec §4.2 keeps that module's existing targets
working rather than folding it into the registry. ``src/scistudio/qa/**`` is
also outside it: its ``"codex"`` strings name the Codex *agent runtime* in the
governance ledger, an unrelated domain that merely shares a word.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from scistudio.ai.agent.providers_registry import agent_descriptors

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src" / "scistudio"
FRONTEND_SRC = REPO_ROOT / "frontend" / "src"
TESTS_ROOT = REPO_ROOT / "tests"

#: Agent provider keys, read off the registry so a sixth provider is guarded
#: the moment it is added rather than when someone remembers to edit this file.
PROVIDER_KEYS: frozenset[str] = frozenset(d.key for d in agent_descriptors())

#: User-facing labels, likewise registry-derived. A frontend label map is the
#: other half of the duplication FR-020b removes, and it would be spelled with
#: these strings.
PROVIDER_LABELS: frozenset[str] = frozenset(d.label for d in agent_descriptors())

#: The modules that own spawn, status, and validation — the exact three
#: responsibilities the Success Criterion names.
_SPAWN_STATUS_VALIDATION_MODULES: tuple[str, ...] = (
    "ai/agent/terminal.py",
    "api/routes/ai.py",
    "api/routes/ai_pty/__init__.py",
    "api/routes/ai_pty/_state.py",
    "api/routes/ai_pty/engine.py",
    "api/routes/ai_pty/internal_routes.py",
    "blocks/ai/ai_block.py",
    "engine/pty_control.py",
)

#: ``{module: {provider key: why this one literal is legitimate}}``.
#:
#: Every entry is a *named* exception. Nothing here is a wildcard, and a key
#: appearing in a module that is not listed fails the test.
#: ``ai/agent/terminal.py`` was allowlisted for ``claude-code`` and ``codex``
#: while ``spawn_claude`` / ``spawn_codex`` existed as deprecated one-line
#: ``REGISTRY.get()`` lookups. Their ``TODO(#1994)`` removal condition
#: ("``_PROVIDER_SPAWNERS`` is derived from the registry") was met by A2's
#: T-005, and both functions were deleted, so the entry is gone rather than
#: left open: the guard now proves ``terminal.py`` names no provider key at
#: all, which is the stronger statement the spec always wanted.
_BACKEND_KEY_ALLOWLIST: dict[str, dict[str, str]] = {
    # FR-015 requires ``claude-code`` to remain the AI Block default when the
    # enum widens, so the default has to be spelled somewhere. It appears as
    # the schema ``default`` and as the ``config.get`` fallback on the two read
    # paths. This is a default, not a provider fact: no behaviour branches on it.
    "blocks/ai/ai_block.py": {
        "claude-code": "FR-015 default provider; enum itself is registry-derived",
    },
}

_STRING_LITERAL = re.compile(r"""["']([^"'\n]*)["']""")


# ---------------------------------------------------------------------------
# Source scanning helpers
# ---------------------------------------------------------------------------


def _docstring_node_ids(tree: ast.AST) -> set[int]:
    """Ids of every module/class/function docstring constant.

    Prose is documentation, and the Success Criterion exempts documentation
    explicitly. A provider key named in a docstring — ``routes/ai.py`` shows a
    sample status payload in one — is description, not logic.
    """
    ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr):
                value = body[0].value
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    ids.add(id(value))
    return ids


def _executable_string_constants(path: Path) -> list[tuple[int, str]]:
    """``(lineno, value)`` for every string constant that is not a docstring."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docstrings = _docstring_node_ids(tree)
    return [
        (node.lineno, node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings
    ]


def _strip_ts_comments(text: str) -> str:
    """Remove ``/* */`` and ``//`` comments from TypeScript source.

    Several frontend files discuss ``claude-code`` at length in comments —
    ``blockPtyHandlers.ts`` explains that defaulting to it is the bug being
    removed. Those are documentation and must not trip the guard, while a
    string literal in executable code must.
    """
    without_block = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    return re.sub(r"(?m)^\s*//.*$|(?<=[;,)\s])//.*$", "", without_block)


def _frontend_sources() -> list[Path]:
    """Non-test TypeScript sources under ``frontend/src``."""
    files = [*FRONTEND_SRC.rglob("*.ts"), *FRONTEND_SRC.rglob("*.tsx")]
    return sorted(
        p for p in files if ".test." not in p.name and "__tests__" not in p.as_posix() and not p.name.endswith(".d.ts")
    )


# ---------------------------------------------------------------------------
# SC: per-provider knowledge lives in exactly one backend module
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("relpath", _SPAWN_STATUS_VALIDATION_MODULES)
def test_spawn_status_and_validation_modules_name_no_unsanctioned_provider_key(relpath: str) -> None:
    """Spec §5: a provider key outside the registry carries no such logic.

    The registry module itself is excluded because it *is* the single source;
    tests and documentation are excluded by the criterion's own wording, and
    docstrings are filtered above for the same reason.
    """
    path = SRC_ROOT / relpath
    assert path.is_file(), f"guarded module moved or was deleted: {relpath}"

    allowed = _BACKEND_KEY_ALLOWLIST.get(relpath, {})
    offenders = [
        f"{relpath}:{lineno} {value!r}"
        for lineno, value in _executable_string_constants(path)
        if value in PROVIDER_KEYS and value not in allowed
    ]
    assert offenders == [], (
        "provider keys appear in spawn/status/validation code outside the registry: "
        f"{offenders}. Read the fact off a ProviderDescriptor instead, or add a "
        "named entry to _BACKEND_KEY_ALLOWLIST with the reason it is legitimate."
    )


@pytest.mark.parametrize("relpath", _SPAWN_STATUS_VALIDATION_MODULES)
def test_no_backend_branch_compares_against_a_provider_key(relpath: str) -> None:
    """Spec §1: the ``if provider == "claude-code" / elif …`` chains are gone.

    This is the sharper half of the criterion. The allowlist above tolerates
    three key *literals*, but none of them may be branched on: a registry
    lookup and a default value are not per-provider logic, whereas a comparison
    is exactly the branch chain this change replaces. Nothing is allowlisted
    here on purpose.
    """
    path = SRC_ROOT / relpath
    tree = ast.parse(path.read_text(encoding="utf-8"))

    offenders: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Compare):
            continue
        if not any(isinstance(op, ast.Eq | ast.NotEq | ast.In | ast.NotIn) for op in node.ops):
            continue
        operands = [node.left, *node.comparators]
        literals: list[str] = []
        for operand in operands:
            if isinstance(operand, ast.Constant) and isinstance(operand.value, str):
                literals.append(operand.value)
            elif isinstance(operand, ast.Set | ast.List | ast.Tuple):
                literals.extend(
                    e.value for e in operand.elts if isinstance(e, ast.Constant) and isinstance(e.value, str)
                )
        hit = sorted(set(literals) & PROVIDER_KEYS)
        if hit:
            offenders.append(f"{relpath}:{node.lineno} compares against {hit}")

    assert offenders == [], (
        f"per-provider branching survives: {offenders}. Dispatch on a descriptor "
        "field instead — that is what makes a sixth provider a registry row."
    )


def test_the_registry_is_the_only_module_declaring_provider_labels() -> None:
    """FR-020b: labels are descriptor data, served to the frontend by status.

    A second label spelling anywhere in the backend is a label map in disguise,
    and it would drift from the registry the first time a product name changed.
    """
    offenders: list[str] = []
    for path in sorted(SRC_ROOT.rglob("*.py")):
        if path.name == "providers_registry.py":
            continue
        for lineno, value in _executable_string_constants(path):
            if value in PROVIDER_LABELS:
                offenders.append(f"{path.relative_to(SRC_ROOT).as_posix()}:{lineno} {value!r}")
    assert offenders == [], f"provider labels declared outside the registry: {offenders}"


# ---------------------------------------------------------------------------
# SC: the frontend has no hand-maintained provider key or label list
# ---------------------------------------------------------------------------

#: ``{frontend file: {literal: reason}}`` — the single sanctioned survivor.
#:
#: ``SetupScreen`` keeps a ``provider === "codex"`` branch that shows Codex's
#: trust-hooks note (#1859). A5 retained it deliberately and flagged it. It is
#: one provider-specific *UI warning*, not a key list and not a label map, so
#: it does not reintroduce the duplication FR-020a/FR-020b remove: adding a
#: sixth provider still requires no edit to this file. It is permitted here by
#: exact file, exact literal, and stated count — a loose "SetupScreen may
#: mention providers" rule would also let a real regression through.
_FRONTEND_KEY_ALLOWLIST: dict[str, dict[str, str]] = {
    "components/AIChat/SetupScreen.tsx": {
        "codex": "#1859 Codex trust-hooks warning: one UI note, not a key or label list",
    },
}

#: How many times each allowlisted literal may appear. One occurrence is a
#: warning condition; three would be a branch chain growing back.
_FRONTEND_KEY_MAX_OCCURRENCES = 1


def test_frontend_declares_no_hand_maintained_provider_key_list() -> None:
    """FR-020a / spec §5: agent keys are opaque strings from the status payload.

    A hand-maintained TypeScript list would have to be edited for every new
    provider, which is precisely the duplication the registry removes and which
    would break User Story 7's single-file-extension promise.
    """
    offenders: list[str] = []
    for path in _frontend_sources():
        relpath = path.relative_to(FRONTEND_SRC).as_posix()
        allowed = _FRONTEND_KEY_ALLOWLIST.get(relpath, {})
        source = _strip_ts_comments(path.read_text(encoding="utf-8"))
        counts: dict[str, int] = {}
        for match in _STRING_LITERAL.finditer(source):
            value = match.group(1)
            if value in PROVIDER_KEYS:
                counts[value] = counts.get(value, 0) + 1
        for value, count in sorted(counts.items()):
            if value not in allowed:
                offenders.append(f"{relpath}: {value!r} x{count}")
            elif count > _FRONTEND_KEY_MAX_OCCURRENCES:
                offenders.append(f"{relpath}: allowlisted {value!r} appeared {count}x, expected at most 1")
    assert offenders == [], (
        f"hand-maintained agent provider keys in the frontend: {offenders}. Keys are "
        "opaque strings validated against the /api/ai/status payload (FR-020a)."
    )


def test_frontend_declares_no_provider_label_map() -> None:
    """FR-020b: labels come from the backend status payload, never a frontend map."""
    offenders: list[str] = []
    for path in _frontend_sources():
        source = _strip_ts_comments(path.read_text(encoding="utf-8"))
        found = sorted({m.group(1) for m in _STRING_LITERAL.finditer(source)} & PROVIDER_LABELS)
        if found:
            offenders.append(f"{path.relative_to(FRONTEND_SRC).as_posix()}: {found}")
    assert offenders == [], (
        f"provider display labels hardcoded in the frontend: {offenders}. Render "
        "`entry.label` from the status payload instead (FR-020b)."
    )


def test_frontend_declares_no_literal_union_of_agent_provider_keys() -> None:
    """FR-020a: agent keys must not be a TypeScript literal union.

    The union is the shape the duplication took before this change — three
    copies of ``"claude-code" | "codex"`` across ``store/types.ts``,
    ``SetupScreen.parts/types.ts``, and ``usePtyWebSocket.ts``. A string-literal
    guard alone would not catch it being written back as a type alias, so the
    union spelling is checked separately.
    """
    union_member = re.compile(r"""\|\s*["'][^"'\n]+["']""")
    offenders: list[str] = []
    for path in _frontend_sources():
        source = _strip_ts_comments(path.read_text(encoding="utf-8"))
        for match in union_member.finditer(source):
            window = source[max(0, match.start() - 200) : match.end() + 200]
            hit = sorted({m.group(1) for m in _STRING_LITERAL.finditer(window)} & PROVIDER_KEYS)
            if hit:
                line = source[: match.start()].count("\n") + 1
                offenders.append(f"{path.relative_to(FRONTEND_SRC).as_posix()}:{line} {hit}")
    assert offenders == [], f"agent provider keys reappeared as a TypeScript literal union: {offenders}"


# ---------------------------------------------------------------------------
# SC: no test asserts a hardcoded two-provider set
# ---------------------------------------------------------------------------

#: The exact set the pre-ADR-034 suite froze. Spec §4.4 called out replacing it
#: in ``test_provider_discovery.py``; this test proves it did not survive
#: anywhere else, and that it cannot come back.
_TWO_PROVIDER_SET = frozenset({"claude-code", "codex"})


def test_no_python_test_asserts_a_hardcoded_two_provider_set() -> None:
    """Spec §5 / User Story 7: a frozen two-provider literal must not exist.

    A collection whose string elements are exactly ``claude-code`` and
    ``codex`` is the frozen set: it passes today and turns red the moment a
    sixth provider is added, which is the failure mode that made adding a
    provider a sweep. Collections that merely *contain* both are fine — a
    parametrise list of providers to exercise legitimately does.
    """
    offenders: list[str] = []
    for path in sorted(TESTS_ROOT.rglob("test_*.py")):
        # This module has to spell the forbidden pair to recognise it.
        if path.resolve() == Path(__file__).resolve():
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:  # pragma: no cover - a broken test file fails elsewhere
            continue
        relpath = path.relative_to(REPO_ROOT).as_posix()
        for node in ast.walk(tree):
            if isinstance(node, ast.Set | ast.List | ast.Tuple):
                values = [e.value for e in node.elts if isinstance(e, ast.Constant) and isinstance(e.value, str)]
                if len(values) == len(node.elts) and set(values) == _TWO_PROVIDER_SET:
                    offenders.append(f"{relpath}:{node.lineno} collection {values}")
            elif isinstance(node, ast.Dict):
                keys = [k.value for k in node.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)]
                if len(keys) == len(node.keys) and set(keys) == _TWO_PROVIDER_SET:
                    offenders.append(f"{relpath}:{node.lineno} dict keys {keys}")
    assert offenders == [], (
        f"a hardcoded two-provider set survives: {offenders}. Compare against "
        "providers_registry.agent_keys() so the registry stays the single source."
    )


def test_no_frontend_test_asserts_a_hardcoded_two_provider_set() -> None:
    """The same guard on the TypeScript side.

    The frontend has no provider list of its own to freeze, so the way this
    criterion would break here is a test fixture that pins the status payload
    to the old two entries and is then asserted exhaustively.
    """
    offenders: list[str] = []
    test_files = [
        p
        for p in [*FRONTEND_SRC.rglob("*.ts"), *FRONTEND_SRC.rglob("*.tsx")]
        if ".test." in p.name or "__tests__" in p.as_posix()
    ]
    for path in sorted(test_files):
        source = _strip_ts_comments(path.read_text(encoding="utf-8"))
        for match in re.finditer(r"\[([^\[\]]*)\]", source):
            body = match.group(1)
            literals = [m.group(1) for m in _STRING_LITERAL.finditer(body)]
            if not literals or set(literals) != _TWO_PROVIDER_SET:
                continue
            # An array of bare strings only; anything with an identifier
            # followed by ``:`` or ``(`` is a richer structure, not a key list.
            if re.search(r"[A-Za-z_$]\s*[:(]", body):
                continue
            line = source[: match.start()].count("\n") + 1
            offenders.append(f"{path.relative_to(FRONTEND_SRC).as_posix()}:{line} {literals}")
    assert offenders == [], f"a hardcoded two-provider set survives in a frontend test: {offenders}"


def test_the_guards_above_are_not_vacuous() -> None:
    """A guard that can never fire proves nothing.

    Each scan above asserts an empty offender list, so a bug in the scanner —
    a path that resolves nowhere, a comment stripper that eats everything —
    would look exactly like a pass. Pin the inputs instead: the registry has
    more than two agents (so the two-provider set is genuinely obsolete), the
    guarded backend modules all exist, and the frontend scan sees real files.
    """
    assert len(PROVIDER_KEYS) > len(_TWO_PROVIDER_SET)
    assert _TWO_PROVIDER_SET < PROVIDER_KEYS
    assert PROVIDER_LABELS and len(PROVIDER_LABELS) == len(PROVIDER_KEYS)
    for relpath in _SPAWN_STATUS_VALIDATION_MODULES:
        assert (SRC_ROOT / relpath).is_file(), relpath
    sources = _frontend_sources()
    assert len(sources) > 50, f"frontend scan found only {len(sources)} files"
    # The allowlisted survivor must actually be there: if #1859's warning is
    # ever removed, this test fails and the allowlist entry is deleted with it
    # rather than quietly becoming a hole.
    setup_screen = FRONTEND_SRC / "components" / "AIChat" / "SetupScreen.tsx"
    assert '"codex"' in _strip_ts_comments(setup_screen.read_text(encoding="utf-8"))

    # Same rule for the backend allowlist, added when the ``terminal.py`` entry
    # outlived the ``spawn_claude`` / ``spawn_codex`` shims it existed for
    # (#1994). An allowlist entry whose literal is no longer present is a hole
    # standing open, so require every entry to still be earned.
    for relpath, allowed in _BACKEND_KEY_ALLOWLIST.items():
        path = SRC_ROOT / relpath
        assert path.is_file(), f"allowlisted module moved or was deleted: {relpath}"
        present = {value for _lineno, value in _executable_string_constants(path)}
        stale = sorted(set(allowed) - present)
        assert stale == [], (
            f"_BACKEND_KEY_ALLOWLIST[{relpath!r}] still permits {stale}, but the "
            "literal is gone. Delete the entry so the guard tightens instead of "
            "keeping an unused exception open."
        )
