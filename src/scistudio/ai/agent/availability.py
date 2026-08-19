"""Graded agent availability — four states over the ADR-034 provider registry.

ADR-053 spec 2 (`docs/specs/adr-053-work-import.md`, FR-031 to FR-036). ADR-034's
``GET /api/ai/status`` answers *presence*: the binary was found and
``--version`` returned, and a credential file or an auth-status command says the
user is logged in. That is two of the four states a consuming surface needs, and
it is the cheap half.

The half it cannot answer is the one that costs the user the most. A user whose
CLI is installed, whose credential file is on disk, and whose account is out of
quota is reported *ready* by every presence check there is, and then fails
several steps into a session — at the point where recovery is most expensive,
after they have already committed time and answered a dialog. FR-033 therefore
requires a **live minimal call** to separate :attr:`AvailabilityState.READY`
from :attr:`AvailabilityState.CALL_FAILED`: a real one-shot request through the
provider's own CLI, which is the only thing that exercises credentials, quota,
network, and provider health together.

**No second discovery path (FR-032).** Nothing here re-implements presence.
:func:`resolve_availability` consumes the rows ``GET /api/ai/status`` already
produces — ``{name, available, version, logged_in, label}`` — and maps
``available: false`` to ``not_installed`` and ``available: true,
logged_in: false`` to ``not_authenticated``. The binary the live call runs is
resolved through :func:`~scistudio.ai.agent.providers_registry.resolve_binary`,
the same resolver the status endpoint, the spawn path, and the AI Block path
use, so none of the four can disagree about which executable a provider means.

**Shared, not private (FR-036).** Bring In My Work is the first consumer, not
the only one; ADR-053 §5.2 names the Learning Center agent-setup entry as
another. This module therefore lives beside the registry rather than inside a
work-import package, and it is a *leaf* on the same terms the registry is: it
imports stdlib and
:mod:`scistudio.ai.agent.providers_registry` and nothing from
:mod:`scistudio.api` or :mod:`scistudio.blocks`, so the API layer can depend on
it without a cycle.

**Never a stuck surface (FR-035).** Live calls are subprocesses that talk to a
remote service, so any of them can hang. Three independent bounds apply: each
call carries a :data:`LIVE_CALL_TIMEOUT_SECONDS` subprocess timeout, all calls
run concurrently on worker threads, and the whole set is additionally bounded by
:data:`REPORT_BUDGET_SECONDS` — a provider that blows through its own timeout
(a Windows child that ignores termination, say) is reported as a *timed-out*
provider rather than holding the report. Degrading to a reported state is the
required behaviour; blocking is not.

**Cost.** A live call is a real, billed model request. Two things keep that
bounded, and both are deliberate rather than incidental:

* Only providers that got past presence are called at all. ``not_installed``
  and ``not_authenticated`` are decided from the status row, so a user with one
  configured provider pays for one call, not five.
* :func:`probe_availability` memoises the report for
  :data:`CACHE_TTL_SECONDS`. Two surfaces asking within the window — the import
  dialog and the Learning Center entry, or one dialog reopened — share a single
  answer. ``refresh=True`` is the escape hatch a "try again" control needs, so a
  user who has just topped up their quota is never told to wait out a cache.

**What a probe may touch (the tool-restriction invariant).** A call fired on
dialog open must leave nothing behind to reason about, so **no probe may write
to or execute anything on the user's machine**. That bound is stated once, here,
because it is not the same mechanism on every CLI and an invariant restated
per-provider drifts:

* ``claude-code``, ``qoder`` and ``qoder-cn`` pass ``--tools ""`` — an empty
  tool allowlist, so the model has no tools at all and cannot read either.
* ``kimi-code`` has no tool flag, but it does accept ``--agent-file <path>``,
  and an agent definition's ``tools`` frontmatter field **is** its tool
  allowlist. :data:`_KIMI_TOOL_FREE_PROFILE` is written into the probe's own
  throwaway directory with an empty ``tools`` list, which lands in the same
  place a flag would.
* ``codex`` has neither, so ``--sandbox read-only`` is what bounds it: the
  model may **read**, and cannot write or execute.

``tests/api/test_agent_availability.py`` partitions :data:`MINIMAL_CALLS` over
exactly those three mechanisms, so a sixth provider cannot land without stating
which one bounds it.

**Provenance of the per-provider call table.** Every argv in
:data:`MINIMAL_CALLS` was run against the binary installed on the owner's
workstation on **2026-08-07** and its wall-clock time observed; see
:data:`MINIMAL_CALLS` for the per-provider table and the observations. Re-verify
when a provider CLI's non-interactive surface changes.

**Two facts about a provider that are not availability grades.** FR-031's four
states answer "will a call work right now?". Two other things a consuming
surface needs are registry facts rather than grades, and both ride on
:class:`ProviderAvailability` rather than being re-derived per surface:
:attr:`~ProviderAvailability.next_step` names the one action that moves *this*
provider out of *this* state (SC-002), and
:attr:`~ProviderAvailability.session_unsupported_reason` says when a provider
cannot be handed an opening instruction on its command line at all — which is
how every SciStudio-started session reaches its agent, so a provider that
cannot take one cannot run one however ``ready`` it is.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
import subprocess
import tempfile
import time
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from scistudio.ai.agent.providers_registry import (
    CONFIG_ROOT,
    ProviderDescriptor,
    resolve_binary,
    session_unsupported_reason,
)
from scistudio.ai.agent.providers_registry import get as get_descriptor

logger = logging.getLogger(__name__)

__all__ = [
    "CACHE_TTL_SECONDS",
    "LIVE_CALL_TIMEOUT_SECONDS",
    "LOGIN_COMMANDS",
    "MINIMAL_CALLS",
    "REPORT_BUDGET_SECONDS",
    "AvailabilityReport",
    "AvailabilityState",
    "MinimalCall",
    "ProbeFile",
    "ProviderAvailability",
    "StatusRow",
    "aggregate_state",
    "clear_availability_cache",
    "install_hint",
    "login_hint",
    "probe_availability",
    "resolve_availability",
    "session_unsupported_reason",
]


#: One row of ``GET /api/ai/status``: ``{name, available, version, logged_in,
#: label}``. Typed as a loose mapping on purpose — this module consumes that
#: endpoint's contract rather than owning it (FR-032).
StatusRow = Mapping[str, Any]


class AvailabilityState(StrEnum):
    """The four states FR-031 defines, in increasing order of usability.

    The wire values are the contract shared with the frontend client and every
    consuming surface; they are the spec's own spellings.
    """

    #: No agent CLI found. Installation instructions are the right guidance.
    NOT_INSTALLED = "not_installed"
    #: Installed, no valid credentials. Login instructions for the provider.
    NOT_AUTHENTICATED = "not_authenticated"
    #: Authenticated, live call failed. The concrete cause — quota, network,
    #: provider outage — and never reinstall guidance (FR-034).
    CALL_FAILED = "call_failed"
    #: The live call succeeded. This provider will work right now.
    READY = "ready"


#: Aggregate ranking for the states that are *not* ``ready``, most actionable
#: first (checklist contract C1). A user with one failing call and one CLI they
#: never installed should be told about the failing call: it is the one they can
#: act on, and it is evidence they are most of the way to a working setup.
_ACTIONABILITY_ORDER: tuple[AvailabilityState, ...] = (
    AvailabilityState.CALL_FAILED,
    AvailabilityState.NOT_AUTHENTICATED,
    AvailabilityState.NOT_INSTALLED,
)


@dataclass(frozen=True)
class ProviderAvailability:
    """One provider's graded availability."""

    key: str
    """Provider-registry key, e.g. ``claude-code``."""

    label: str
    """User-facing product name, carried through from the status row."""

    state: AvailabilityState

    cause: str | None = None
    """Why the live call failed. Populated **only** for
    :attr:`AvailabilityState.CALL_FAILED`, and never carrying reinstall
    guidance (FR-034)."""

    next_step: str | None = None
    """The one action that moves this provider out of this state (SC-002).

    Populated for :attr:`AvailabilityState.NOT_INSTALLED` (how to install it)
    and :attr:`AvailabilityState.NOT_AUTHENTICATED` (how to sign in), which are
    exactly the two states FR-031 gives a guidance column to. ``None`` for
    ``call_failed`` — there :attr:`cause` is the specific information, and FR-034
    forbids sending a user whose CLI demonstrably runs off to fix their install —
    and ``None`` for ``ready``, which needs no action.

    A *sentence*, not a bare command, because the surface renders it next to a
    provider label and a user has to be able to read it as an instruction.
    """

    session_unsupported_reason: str | None = None
    """Why a SciStudio-started session cannot use this provider, if it cannot.

    Independent of :attr:`state`: this is a fact about the CLI's argument
    surface, not about the user's setup, and no amount of installing or signing
    in changes it. Non-``None`` means the provider declares
    ``prompt_argv_prefix is None`` — it has no positional prompt argument, so
    the opening instruction that every SciStudio-started session is delivered
    with cannot reach it (ADR-034 ``ProviderDescriptor.prompt_argv_prefix``).
    Such a provider is still a perfectly good hand-launched chat tab, which is
    why it is reported rather than hidden, and why this does not downgrade
    :attr:`state`.

    Carries the registry's own :attr:`~...ProviderDescriptor.prompt_unsupported_reason`
    verbatim: the explanation of a CLI's limitation belongs beside the
    descriptor that records the limitation, and paraphrasing it here would give
    the user two subtly different accounts of one fact.
    """

    def as_dict(self) -> dict[str, Any]:
        """Serialise to the wire shape of checklist contract C1."""
        return {
            "key": self.key,
            "label": self.label,
            "state": self.state.value,
            "cause": self.cause,
            "next_step": self.next_step,
            "session_unsupported_reason": self.session_unsupported_reason,
        }


@dataclass(frozen=True)
class AvailabilityReport:
    """Every provider's state plus the aggregate a surface renders from."""

    state: AvailabilityState
    providers: tuple[ProviderAvailability, ...]

    def as_dict(self) -> dict[str, Any]:
        """Serialise to the wire shape of checklist contract C1."""
        return {
            "state": self.state.value,
            "providers": [provider.as_dict() for provider in self.providers],
        }


# ---------------------------------------------------------------------------
# The live minimal call
# ---------------------------------------------------------------------------


#: Wall-clock budget for one provider's live call. Derived from measurement, not
#: guessed: the slowest observed successful call on the owner's workstation was
#: Qoder at 8.3 s (Claude Code 2.5 s, Codex 4.9 s, Kimi Code 0.7 s), so 15 s
#: leaves roughly 1.8x headroom for a cold CLI start or a slow network without
#: turning a working provider into a reported failure. A user's true failure
#: modes — bad credentials, exhausted quota — surface in well under a second.
LIVE_CALL_TIMEOUT_SECONDS = 15.0

#: Hard ceiling on the whole report, independent of the per-call timeout above.
#: ``subprocess.run(timeout=...)`` can fail to return on time if the child
#: ignores termination or leaves grandchildren holding the pipes, which is a
#: real Windows failure mode; FR-035 forbids that becoming a stuck surface, so
#: the gather is bounded again here and any provider still outstanding is
#: reported as timed out.
REPORT_BUDGET_SECONDS = LIVE_CALL_TIMEOUT_SECONDS + 5.0

#: How long a computed report is reused by :func:`probe_availability`. Long
#: enough that opening the same dialog twice, or two agent-dependent surfaces in
#: one session, do not bill the user twice; short enough that a user who fixes
#: their setup and comes back is not reading a stale answer. ``refresh=True``
#: bypasses it outright for an explicit retry control.
CACHE_TTL_SECONDS = 60.0

#: The prompt every live call sends. Short, unambiguous, and answerable without
#: any tool use or context, so the response is a handful of tokens.
LIVE_CALL_PROMPT = "Reply with the single word: ok"


@dataclass(frozen=True)
class ProbeFile:
    """A file the probe materialises in its throwaway directory before calling.

    The escape hatch for a CLI whose bound is expressed in a *file* rather than
    in a flag. Kimi Code is the observed case and the only one: it has no tool
    switch, but ``--agent-file`` selects an agent definition whose ``tools``
    frontmatter field is that session's tool allowlist, so an empty list there
    is the same bound ``--tools ""`` gives the other CLIs.

    The file is written into the probe's own :class:`tempfile.TemporaryDirectory`
    and dies with it, so nothing survives a probe.
    """

    flag: str
    """Flag that points the CLI at the file, e.g. ``--agent-file``."""

    name: str
    """Filename inside the probe's throwaway directory."""

    content: str
    """The file's exact contents."""


#: Kimi Code's tool restriction, as an agent definition rather than a flag.
#:
#: Verified against the installed ``kimi`` 0.33.0 on 2026-08-07: ``--help`` at
#: that version lists no tool-disabling or sandbox flag, ``--plan`` is refused
#: outright when combined with ``-p`` ("Cannot combine --prompt with --plan"),
#: and ``--agent`` cannot be combined with ``--agent-file``. Passing this file
#: alone is accepted — the CLI parses it and proceeds to its own
#: model-configuration check — while a malformed one is rejected by name, which
#: is how the frontmatter below was confirmed to be read rather than ignored.
#:
#: ``tools: ""`` parses to the empty list, and Kimi's own profile assembly uses
#: a file's ``tools`` verbatim when present and only falls back to the default
#: tool set when the field is absent — so an empty list is an empty allowlist,
#: not "unrestricted". ``disallowedTools: "*"`` is belt and braces on the
#: denylist side, which is evaluated separately against resolved MCP tool names.
_KIMI_TOOL_FREE_PROFILE = """\
---
name: scistudio-availability-probe
description: SciStudio availability probe. Answers in one word and uses no tools.
tools: ""
disallowedTools: "*"
---
Answer the user's message with a single word. You have no tools available; do not attempt to use any.
"""


@dataclass(frozen=True)
class MinimalCall:
    """How to make one provider's cheapest possible real request.

    Assembled as ``[binary, *argv, *probe_file_argv, *economy_argv, <prompt>]``,
    where the prompt is placed either behind :attr:`prompt_flag` or after
    :attr:`prompt_prefix`.
    """

    argv: tuple[str, ...]
    """Flags that make the call non-interactive, tool-free, and stateless."""

    prompt_prefix: tuple[str, ...] = ()
    """Argv placed before a positional prompt — ``("--",)`` for CLIs whose
    variadic flags would otherwise swallow it, empty when none is needed."""

    prompt_flag: str | None = None
    """Flag carrying the prompt for CLIs with no positional prompt at all.
    Kimi Code is the observed case: its first positional is parsed as a
    subcommand, so the prompt goes through ``-p``."""

    economy_argv: tuple[str, ...] = ()
    """Cheapest-model / lowest-effort hints, dropped on retry.

    These cut the bill by an order of magnitude — pinning Claude Code to Haiku
    took one observed call from $0.0346 to $0.0021 — but they name a model
    alias or a config key, and a user on a gateway, an enterprise proxy, or a
    third-party backend may not have that alias. Reporting such a user
    ``call_failed`` would be a false alarm about a working setup, so a failed
    economy attempt is retried once without these before any failure is
    reported. The success path pays nothing for the safeguard.
    """

    probe_file: ProbeFile | None = None
    """A file this provider's bound is expressed in, or ``None`` for a flag.

    ``workdir`` is required by :meth:`build_argv` because of this: the file's
    path is part of the argv, so argv and directory cannot be decided apart.
    """

    def build_argv(self, binary: str, *, economy: bool, workdir: Path) -> list[str]:
        """Concrete argv for *binary*, with or without the economy hints.

        *workdir* is the throwaway directory the call runs in, and the
        directory :attr:`probe_file` is materialised in by
        :func:`_live_call_cause`.
        """
        argv = [binary, *self.argv]
        if self.probe_file is not None:
            argv.extend([self.probe_file.flag, str(workdir / self.probe_file.name)])
        if economy:
            argv.extend(self.economy_argv)
        if self.prompt_flag is not None:
            argv.extend([self.prompt_flag, LIVE_CALL_PROMPT])
        else:
            argv.extend([*self.prompt_prefix, LIVE_CALL_PROMPT])
        return argv


def _qoder_minimal_call() -> MinimalCall:
    """Build one Qoder channel's minimal call.

    The two Qoder channels are one CLI shipped on two channels; the registry
    models them as independent descriptors sharing every strategy field, and
    their non-interactive surfaces were compared at 1.1.15/1.1.16 and match.
    Building both from one helper keeps them from drifting for the same reason
    the registry's ``_qoder_channel`` helper exists.

    ``--tools ""`` is what makes this safe as well as cheap: with no tools the
    CLI cannot read, write, or execute anything on the user's machine, so a
    probe fired on dialog open has no side effects to reason about.
    ``--max-output-tokens 64`` stands in for the model-alias economy hint the
    other CLIs get — neither channel exposes a stable cheap alias, since
    ``--model`` takes a per-user model name or a custom model id.
    """
    return MinimalCall(
        argv=(
            "--print",
            "--strict-mcp-config",
            "--no-session-persistence",
            "--max-output-tokens",
            "64",
            "--tools",
            "",
        ),
        prompt_prefix=("--",),
    )


#: Per-provider minimal call, keyed by provider-registry key.
#:
#: This table is *consumer* data, not registry data: it says how to ask a
#: provider the cheapest real question, which no other call site in the
#: repository needs. Every row was executed against the installed binary on the
#: owner's Windows workstation on 2026-08-07 and timed:
#:
#: =============  ======================================  ==========  ==================
#: Provider       Observed                                Wall clock  Cost / size
#: =============  ======================================  ==========  ==================
#: ``claude-code``  exit 0, printed ``ok``                  2.5 s       $0.0021 (haiku)
#: ``codex``        exit 0, printed ``ok``                  4.9 s       ~14.9k ctx tokens
#: ``kimi-code``    exit 1, "No model configured. …"        0.7 s       no request billed
#: ``qoder-cn``     exit 0, printed ``ok``                  8.3 s       not reported by CLI
#: ``qoder``        not installed; shares the CN argv       —           —
#: =============  ======================================  ==========  ==================
#:
#: The Kimi row is the FR-033 case observed in the wild rather than contrived:
#: the credential file was present, so presence checks called it logged in, and
#: the live call failed immediately with a readable cause.
#:
#: A provider key missing from this table cannot be graded past presence, which
#: :func:`_live_call_cause` reports rather than silently claiming ``ready``.
#: ``tests/api/test_agent_availability.py`` pins the table against
#: ``providers_registry.agent_keys()`` so a sixth provider cannot land without
#: its own row.
MINIMAL_CALLS: Mapping[str, MinimalCall] = {
    # ``--safe-mode`` disables CLAUDE.md, skills, plugins, hooks, and MCP
    # servers while leaving auth and model selection working normally, so the
    # probe never drags a user's project configuration into a billed request.
    # ``haiku`` is a documented model alias on Claude Code 2.x.
    "claude-code": MinimalCall(
        argv=(
            "--print",
            "--safe-mode",
            "--strict-mcp-config",
            "--no-session-persistence",
            "--tools",
            "",
        ),
        prompt_prefix=("--",),
        economy_argv=("--model", "haiku"),
    ),
    # Codex has no tool-disabling flag, so the read-only sandbox is what bounds
    # it: the model can look but cannot write or execute. ``--ephemeral`` keeps
    # the probe out of the user's session history, ``--skip-git-repo-check``
    # lets it run in the throwaway directory the probe uses as its cwd, and
    # ``--color never`` keeps ANSI escapes out of any reported cause.
    # ``model_reasoning_effort`` is a stable config key; the owner's machine was
    # configured at ``xhigh``, where the same call took 7.8 s instead of 4.9 s.
    "codex": MinimalCall(
        argv=(
            "exec",
            "--sandbox",
            "read-only",
            "--skip-git-repo-check",
            "--ephemeral",
            "--color",
            "never",
        ),
        economy_argv=("-c", 'model_reasoning_effort="low"'),
    ),
    # Kimi Code has no positional prompt (its first positional is parsed as a
    # subcommand); ``-p`` runs one prompt non-interactively and exits, which is
    # exactly the shape this probe wants. It has no tool-restriction *flag*
    # either, so its bound arrives as an agent definition instead — see
    # ``_KIMI_TOOL_FREE_PROFILE`` for what was checked against the installed
    # CLI and why an empty ``tools`` list is an empty allowlist.
    "kimi-code": MinimalCall(
        argv=("--output-format", "text"),
        prompt_flag="-p",
        probe_file=ProbeFile(
            flag="--agent-file",
            name="scistudio-availability-probe.md",
            content=_KIMI_TOOL_FREE_PROFILE,
        ),
    ),
    "qoder": _qoder_minimal_call(),
    "qoder-cn": _qoder_minimal_call(),
}


#: Guidance patterns FR-034 forbids in a ``call_failed`` cause. A provider CLI
#: is free to end an error with "try reinstalling"; repeating that to a user
#: whose install demonstrably runs — SciStudio found the binary, read its
#: version, and got an error back *from the provider's service* — sends them to
#: fix something that is not broken.
_REINSTALL_GUIDANCE = re.compile(
    r"re-?install|npm\s+(?:install|i)\s+-g|install\s+(?:it\s+)?again|download\s+.*install(?:er)?\b",
    re.IGNORECASE,
)

#: Cause lines kept, and the character ceiling after joining. A cause is read by
#: a user inside a dialog, so it has to be a sentence or two, not a stack trace.
_CAUSE_MAX_LINES = 4
_CAUSE_MAX_CHARS = 400

#: Fallbacks when a provider fails without saying anything usable. Both are
#: honest about what is known and neither implies a broken installation.
_CAUSE_NO_MESSAGE = "the provider CLI reported an error but produced no readable message"
_CAUSE_NO_OUTPUT = "the provider CLI exited successfully but produced no response"
_CAUSE_NO_BINARY = "the provider CLI could not be located to make a live call"


def _sanitise_cause(text: str) -> str | None:
    """Reduce provider output to a short, user-readable cause (FR-034).

    Keeps the first few non-empty lines — CLIs put their diagnosis first and
    their stack trace last — drops any line offering reinstall guidance, and
    truncates. Returns ``None`` when nothing usable survives, so the caller can
    substitute an honest fallback rather than an empty string.
    """
    kept: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or _REINSTALL_GUIDANCE.search(line):
            continue
        kept.append(line)
        if len(kept) == _CAUSE_MAX_LINES:
            break
    if not kept:
        return None
    cause = " ".join(kept)
    if len(cause) > _CAUSE_MAX_CHARS:
        cause = cause[: _CAUSE_MAX_CHARS - 1].rstrip() + "…"
    return cause


def _run_minimal_call(argv: list[str], *, cwd: str) -> tuple[bool, str | None]:
    """Run one attempt, returning ``(succeeded, cause_when_not)``.

    *cwd* is a throwaway empty directory rather than the server's working
    directory, so a project's own agent configuration is never loaded into a
    probe — which keeps the request small and keeps the probe free of project
    side effects.
    """
    try:
        result = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=LIVE_CALL_TIMEOUT_SECONDS,
            check=False,
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            env=os.environ.copy(),
        )
    except subprocess.TimeoutExpired:
        return False, f"the provider CLI did not respond within {LIVE_CALL_TIMEOUT_SECONDS:.0f} seconds"
    except OSError as error:
        return False, _sanitise_cause(str(error)) or _CAUSE_NO_MESSAGE

    stdout = result.stdout or ""
    stderr = result.stderr or ""
    if result.returncode != 0:
        cause = _sanitise_cause(stderr) or _sanitise_cause(stdout) or _CAUSE_NO_MESSAGE
        return False, cause
    if not stdout.strip():
        return False, _CAUSE_NO_OUTPUT
    return True, None


def _live_call_cause(descriptor: ProviderDescriptor) -> str | None:
    """Make *descriptor*'s live minimal call. ``None`` means it succeeded.

    A provider whose economy attempt fails is retried once at its own default
    model before any failure is reported, so a user whose backend does not carry
    the cheap model alias is not told their working agent is broken.
    """
    call = MINIMAL_CALLS.get(descriptor.key)
    if call is None:
        # Not a silent ``ready``: FR-033 makes the live call the *only* evidence
        # that permits it, so a provider this module cannot call is reported as
        # ungradable. The completeness test makes this unreachable in practice.
        logger.warning("no live minimal call declared for provider %r", descriptor.key)
        return f"SciStudio has no live-call probe for {descriptor.label}, so it cannot confirm the agent works"

    resolved = resolve_binary(descriptor, which=shutil.which, home=Path.home())
    if resolved is None:
        return _CAUSE_NO_BINARY
    binary = str(resolved)

    with tempfile.TemporaryDirectory(prefix="scistudio-availability-") as workdir:
        work = Path(workdir)
        if call.probe_file is not None:
            # Written before the first attempt and gone with the directory
            # after the last: the tool restriction has to exist on disk for the
            # duration of the call it bounds, and no longer.
            (work / call.probe_file.name).write_text(call.probe_file.content, encoding="utf-8")
        attempts = (True, False) if call.economy_argv else (False,)
        cause: str | None = None
        for economy in attempts:
            argv = call.build_argv(binary, economy=economy, workdir=work)
            succeeded, cause = _run_minimal_call(argv, cwd=workdir)
            if succeeded:
                return None
        return cause


# ---------------------------------------------------------------------------
# Per-provider next steps (SC-002) and session capability
# ---------------------------------------------------------------------------


#: How each provider is signed in, or ``None`` when it has no sign-in command.
#:
#: Verified on 2026-08-07 by reading the installed CLI's own ``--help``:
#: ``claude auth`` lists ``login``; ``codex`` lists a top-level ``login``
#: subcommand; ``kimi`` lists ``login`` ("Authenticate with Kimi Code CLI via
#: the device-code flow"). Neither Qoder channel is installed on the owner's
#: workstation and neither declares an ``auth_status_argv`` in the registry, so
#: no command could be verified for them — their rows are an explicit ``None``,
#: which routes to a hint naming the binary and the credential file SciStudio
#: reads instead of a command that might not exist.
#:
#: A row is required for every registry agent even when it is ``None``: the
#: completeness test in ``tests/api/test_agent_availability.py`` distinguishes
#: "verified that there is no command" from "nobody looked". A **wrong** command
#: here is worse than a vague sentence — it sends a user to a prompt that does
#: not exist and makes SciStudio look like the broken part — so a key is only
#: filled in from that CLI's own help output.
LOGIN_COMMANDS: Mapping[str, str | None] = {
    "claude-code": "claude auth login",
    "codex": "codex login",
    "kimi-code": "kimi login",
    "qoder": None,
    "qoder-cn": None,
}


def _home_relative(descriptor: ProviderDescriptor, segments: tuple[str, ...]) -> str:
    """Render one ``well_known_dirs`` entry as a ``~``-relative display path."""
    parts = (*descriptor.config_root, *segments[1:]) if segments and segments[0] == CONFIG_ROOT else segments
    return "~/" + "/".join(parts)


def _installable_name(descriptor: ProviderDescriptor) -> str:
    """The provider's name with exactly one "CLI" in it.

    Two registry labels already end in it — ``Qoder CLI`` and
    ``Qoder CLI (China)`` — so appending unconditionally produced "Install the
    Qoder CLI CLI". Split on whitespace rather than ``endswith`` because the
    China variant carries the word in the middle, not at the end.
    """
    return descriptor.label if "CLI" in descriptor.label.split() else f"{descriptor.label} CLI"


def install_hint(descriptor: ProviderDescriptor) -> str:
    """Name the executable to install and everywhere SciStudio looked for it.

    Deliberately **not** a command. ADR-034 FR-014 already records why: the one
    install command SciStudio owns, ``scistudio install``, wires this product's
    MCP server and skills into a CLI the user already has and cannot install the
    CLI itself, so an earlier hint pointing at it left discovery failing. The
    same reasoning rules out inventing each vendor's install line here — a
    command that does not work is worse than a fact that does, and SciStudio
    cannot make a vendor's installer corrective.

    What the user can act on is what SciStudio actually checked: the exact
    executable name, and the directories searched. Both are read off the
    descriptor, so a registry change cannot leave this sentence stale.
    """
    names = " or ".join(f"`{name}`" for name in descriptor.binary_candidates)
    if not names:  # pragma: no cover - every agent descriptor declares a binary
        return f"Install {_installable_name(descriptor)} so SciStudio can find it."
    searched = ", ".join(_home_relative(descriptor, segments) for segments in descriptor.well_known_dirs)
    location = f"your PATH and in {searched}" if searched else "your PATH"
    return f"Install {_installable_name(descriptor)} so that {names} is on {location}."


def login_hint(descriptor: ProviderDescriptor) -> str:
    """Name the command that signs this provider in, or the next best fact.

    A verified command when :data:`LOGIN_COMMANDS` has one. Otherwise the
    binary to start and the credential file SciStudio reads to decide the
    question, which is a real next action — start it, sign in, come back — with
    nothing invented in it.
    """
    command = LOGIN_COMMANDS.get(descriptor.key)
    if command:
        return f"Sign in by running `{command}` in a terminal."
    binary = descriptor.binary_candidates[0] if descriptor.binary_candidates else descriptor.label
    credential = descriptor.credentials
    if credential is None:  # pragma: no cover - every agent descriptor probes credentials
        return f"Start `{binary}` in a terminal and complete its sign-in."
    where = _home_relative(descriptor, (CONFIG_ROOT, *credential.credential_path))
    return f"Start `{binary}` in a terminal and complete its sign-in; SciStudio reads {where} to confirm it."


# ``session_unsupported_reason`` is defined in ``providers_registry`` and
# re-exported here (it stays in this module's ``__all__``). It lived here first,
# because availability is the shared report every agent-dependent surface reads
# and a surface that must not offer a provider it cannot launch needs the answer
# at the same moment it needs the grade. #2014 gave it a second consumer,
# ``AIBlock.config_schema``, and that is what moved it: ``blocks`` may not
# import ``scistudio.ai`` except for one carved-out lazy edge to the registry,
# and this module runs subprocesses to probe auth — far more than a block layer
# should be able to reach for a question that reads three descriptor fields and
# calls nothing. The registry is where per-CLI facts already live and is the
# leaf both layers may depend on, so the predicate moved there and every caller
# here, in ``api``, and in the tests keeps importing it from wherever it was
# already importing it.


def _next_step(descriptor: ProviderDescriptor, state: AvailabilityState) -> str | None:
    """The action for *descriptor* in *state*, or ``None`` when there is none."""
    if state is AvailabilityState.NOT_INSTALLED:
        return install_hint(descriptor)
    if state is AvailabilityState.NOT_AUTHENTICATED:
        return login_hint(descriptor)
    return None


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------


def _presence_state(row: StatusRow) -> AvailabilityState | None:
    """Map a status row's presence fields, or ``None`` if a live call is owed.

    FR-032's mapping exactly: ``available: false`` is ``not_installed``, and
    ``available: true, logged_in: false`` is ``not_authenticated``. An installed
    and authenticated provider is *not* decided here — that is the whole point
    of FR-033.
    """
    if not row.get("available"):
        return AvailabilityState.NOT_INSTALLED
    if not row.get("logged_in"):
        return AvailabilityState.NOT_AUTHENTICATED
    return None


def aggregate_state(providers: Sequence[ProviderAvailability]) -> AvailabilityState:
    """Collapse per-provider states into the aggregate of contract C1.

    ``ready`` when **any** provider is ready. That asymmetry is deliberate and
    it is what makes FR-005 hold: a user with a working Claude Code and an
    unconfigured Codex has a usable agent, and a surface that reported the worst
    state would block them over a CLI they never intended to use.

    Otherwise the most *actionable* state present, ranked ``call_failed`` >
    ``not_authenticated`` > ``not_installed``, so the guidance a surface shows
    is the one closest to a working setup. An empty registry yields
    ``not_installed``: no agent providers means no agent.
    """
    if not providers:
        return AvailabilityState.NOT_INSTALLED
    if any(provider.state is AvailabilityState.READY for provider in providers):
        return AvailabilityState.READY
    present = {provider.state for provider in providers}
    for state in _ACTIONABILITY_ORDER:
        if state in present:
            return state
    return AvailabilityState.NOT_INSTALLED


def _descriptor_for(row: StatusRow) -> ProviderDescriptor | None:
    """Registry descriptor for a status row, or ``None`` when unregistered."""
    try:
        return get_descriptor(str(row.get("name", "")))
    except KeyError:
        return None


async def resolve_availability(status_rows: Sequence[StatusRow]) -> AvailabilityReport:
    """Grade every row of ``GET /api/ai/status`` into an availability report.

    Uncached and side-effect-free apart from the live calls themselves; callers
    that want the shared memoised answer use :func:`probe_availability`.

    Rows keep their input order, which is registry order, so a surface listing
    providers gets the same order everywhere. Only rows that pass presence cost
    a live call, and those run concurrently under the two bounds described in
    the module docstring, so total latency is the slowest single provider rather
    than their sum.
    """
    graded: list[ProviderAvailability | None] = [None] * len(status_rows)
    pending: list[tuple[int, asyncio.Task[str | None]]] = []

    for index, row in enumerate(status_rows):
        key = str(row.get("name", ""))
        label = str(row.get("label", key))
        descriptor = _descriptor_for(row)
        presence = _presence_state(row)
        if descriptor is None:
            # A row naming a provider the registry does not know cannot be
            # launched by any SciStudio surface, whatever it claims about
            # itself, so it is reported the same way a missing CLI is. No next
            # step either: there is no descriptor to read one off, and inventing
            # "install it" for a provider SciStudio cannot launch would send the
            # user somewhere that does not help.
            graded[index] = ProviderAvailability(key=key, label=label, state=AvailabilityState.NOT_INSTALLED)
            continue
        if presence is not None:
            graded[index] = ProviderAvailability(
                key=key,
                label=label,
                state=presence,
                next_step=_next_step(descriptor, presence),
                session_unsupported_reason=session_unsupported_reason(descriptor),
            )
            continue
        pending.append((index, asyncio.ensure_future(asyncio.to_thread(_live_call_cause, descriptor))))

    if pending:
        await _settle_live_calls(status_rows, graded, pending)

    providers = tuple(entry for entry in graded if entry is not None)
    return AvailabilityReport(state=aggregate_state(providers), providers=providers)


async def _settle_live_calls(
    status_rows: Sequence[StatusRow],
    graded: list[ProviderAvailability | None],
    pending: list[tuple[int, asyncio.Task[str | None]]],
) -> None:
    """Await the live calls under :data:`REPORT_BUDGET_SECONDS` (FR-035).

    Whatever has not finished when the budget expires is written down as a
    timed-out provider and left running: a worker thread blocked in a
    subprocess cannot be cancelled, so the alternative to reporting around it is
    waiting for it, which is the stuck surface FR-035 forbids. The stragglers
    get a done-callback that consumes their eventual result so a late failure
    cannot surface as an unretrieved-exception warning.
    """
    await asyncio.wait([task for _, task in pending], timeout=REPORT_BUDGET_SECONDS)

    for index, task in pending:
        row = status_rows[index]
        key = str(row.get("name", ""))
        label = str(row.get("label", key))
        # Only rows with a descriptor reach a live call, so this cannot be None.
        descriptor = _descriptor_for(row)
        unsupported = session_unsupported_reason(descriptor) if descriptor is not None else None
        if not task.done():
            task.add_done_callback(_consume_late_result)
            graded[index] = ProviderAvailability(
                key=key,
                label=label,
                state=AvailabilityState.CALL_FAILED,
                cause=f"the provider CLI did not respond within {REPORT_BUDGET_SECONDS:.0f} seconds",
                session_unsupported_reason=unsupported,
            )
            continue
        try:
            cause = task.result()
        except Exception as error:  # a probe must never propagate to the caller
            logger.warning("live availability call for %r raised: %s", key, error)
            cause = _sanitise_cause(str(error)) or _CAUSE_NO_MESSAGE
        if cause is None:
            graded[index] = ProviderAvailability(
                key=key,
                label=label,
                state=AvailabilityState.READY,
                session_unsupported_reason=unsupported,
            )
        else:
            graded[index] = ProviderAvailability(
                key=key,
                label=label,
                state=AvailabilityState.CALL_FAILED,
                cause=cause,
                session_unsupported_reason=unsupported,
            )


def _consume_late_result(task: asyncio.Task[str | None]) -> None:
    """Swallow the result of a probe that outlived the report budget."""
    if not task.cancelled():
        task.exception()


# ---------------------------------------------------------------------------
# Shared cached entry point
# ---------------------------------------------------------------------------


#: ``(monotonic_deadline, report)`` for the last computed report, or ``None``.
_cached_report: tuple[float, AvailabilityReport] | None = None


def clear_availability_cache() -> None:
    """Drop the memoised report. Exposed for tests and for explicit invalidation."""
    global _cached_report
    _cached_report = None


async def probe_availability(
    load_status: Callable[[], Awaitable[Sequence[StatusRow]]],
    *,
    refresh: bool = False,
) -> AvailabilityReport:
    """Return the shared availability report, memoised for :data:`CACHE_TTL_SECONDS`.

    *load_status* produces the ``GET /api/ai/status`` rows. It is injected
    rather than imported so this module stays a leaf under
    :mod:`scistudio.ai.agent` while still consuming the API layer's single
    discovery path (FR-032), and so a cache hit costs nothing at all — not even
    the presence probes.

    Concurrent callers arriving on a cold cache may each compute a report. That
    is deliberate: serialising them would need a lock bound to one event loop,
    and the cost of the rare duplicate is one extra minimal call against a
    provider that is by definition responding.
    """
    global _cached_report
    now = time.monotonic()
    cached = _cached_report
    if not refresh and cached is not None and cached[0] > now:
        return cached[1]
    report = await resolve_availability(await load_status())
    _cached_report = (time.monotonic() + CACHE_TTL_SECONDS, report)
    return report
