"""ADR-034 multi-provider agent registry — the single source of per-CLI facts.

ADR-034 claimed that adding a PTY chat provider "changes only the spawned
executable plus a few argv differences". Before this module that was false:
per-provider knowledge lived in fifteen backend locations and two independent
argv builders. This module makes the claim true. Every per-CLI fact consumed by
spawn, discovery, status, and validation lives in exactly one descriptor table
here (FR-001), and adding a sixth provider is a data change plus a discovery
rule rather than a sweep across call sites.

**Layering.** This module is a *leaf*: it MUST NOT import from
:mod:`scistudio.api` or :mod:`scistudio.blocks`, so both the API layer and the
block layer can depend on it without a cycle (spec §4.1, mirroring the
constraint that makes ``ai_pty/_state.py`` safe). It holds data and pure path
resolution only — process spawning lives in
:mod:`scistudio.ai.agent.terminal`.

**Provenance.** Every fact below is transcribed from the verified provider
tables in ``docs/specs/adr-034-multi-provider-agent-chat.md`` §1, observed
against the binaries installed on the owner workstation on **2026-08-06**:

===============  ==========  ================  ===========================
Provider         Binary      Version observed  Well-known install dir
===============  ==========  ================  ===========================
``claude-code``  claude      2.x               ``~/.local/bin``
``codex``        codex       0.139.0           ``~/AppData/Roaming/npm``
``kimi-code``    kimi        0.33.0            ``<KIMI_CODE_HOME>/bin``
``qoder``        qodercli    1.1.15            ``~/.qoder/bin/qodercli``
``qoder-cn``     qoderclicn  1.1.15            ``~/.qoder-cn/bin/qoderclicn``
===============  ==========  ================  ===========================

Re-verify this table when a provider CLI major version changes (spec §4.5).

**Channel variants.** ``qoder`` and ``qoder-cn`` are two *independent*
descriptor instances sharing every strategy field, not one descriptor with two
binary candidates (FR-025, FR-026). A user may install both side by side, with
separate binaries, config roots, and credentials, and must be able to pick
which account and model catalog a chat tab uses. Modelling them as alternative
candidates of one key would also let a missing channel silently resolve to the
sibling channel's binary, which FR-026 forbids.

**Sidecar rejection.** The Qoder security-scan plugin ships its own pinned CLI
copy at ``~/.qodersec/bin/qodercli.exe`` (observed at 1.1.12). It is an
internal dependency of the scanner, not a user-facing chat CLI, and it is stale
relative to the real install. FR-027's promise is unconditional, so keeping it
takes **two** rules, not one:

1. :func:`resolve_binary` matches an exact binary name inside a *registered*
   well-known directory and never globs under the home directory, so a stray
   copy is not discovered.
2. :attr:`ProviderDescriptor.excluded_dirs` names subtrees a resolution may
   never come from, checked against the resolved path whichever source found
   it. Rule 1 alone constrains only the well-known-directory scan; ``which``
   searches whatever the user put on PATH, so a user whose PATH includes
   ``~/.qodersec/bin`` would otherwise be handed the sidecar despite rule 1
   holding.
"""

from __future__ import annotations

import os
import shutil
import sys
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

__all__ = [
    "CONFIG_ROOT",
    "REGISTRY",
    "CredentialProbe",
    "McpInjection",
    "McpStrategy",
    "ProviderDescriptor",
    "ProviderKind",
    "ProviderRegistry",
    "SystemPromptInjection",
    "SystemPromptStrategy",
    "agent_descriptors",
    "agent_keys",
    "get",
    "provider_keys",
    "resolve_binary",
    "resolve_executable",
]

#: Sentinel first segment marking a path as relative to the provider's resolved
#: config root rather than to the user home directory. Kimi Code's install and
#: credential paths both hang off ``KIMI_CODE_HOME`` when it is set, and Kimi's
#: own documentation instructs callers never to assume ``~/.kimi-code``.
CONFIG_ROOT = "<config-root>"

#: Windows launcher extensions, in preference order. npm global installs place
#: both a bare Unix shell wrapper and a ``.cmd`` launcher on PATH; pywinpty's
#: CreateProcess spawn path cannot execute the bare wrapper reliably.
WINDOWS_EXECUTABLE_SUFFIXES = (".cmd", ".bat", ".exe")


class ProviderKind(StrEnum):
    """Distinguishes agent CLIs from the shell pseudo-provider (FR-003)."""

    AGENT = "agent"
    TERMINAL = "terminal"


class McpStrategy(StrEnum):
    """How a provider learns about the SciStudio MCP server.

    The payload is provider-agnostic in every case (FR-018); only the write
    location and the injection mechanism differ.
    """

    #: Explicit ``--mcp-config <path>`` flag pointing at the SciStudio-owned
    #: ``<project>/.scistudio/mcp.json``.
    FLAG = "flag"
    #: Codex ``-c mcp_servers.<name>.<field>=<value>`` command-line overrides.
    CODEX_OVERRIDES = "codex_overrides"
    #: Merge the SciStudio entry into a *provider-owned* project-scope config
    #: file before spawn (FR-017, FR-017a).
    PROJECT_FILE = "project_file"
    #: No MCP wiring at all — the ``user-terminal`` pseudo-provider.
    NONE = "none"


class SystemPromptStrategy(StrEnum):
    """How a provider receives the composed SciStudio system prompt."""

    #: A flag that accepts ``@<file>`` indirection, so an unbounded prompt never
    #: lands on the command line.
    FLAG_FILE = "flag_file"
    #: Ambient discovery through the already-provisioned skills trees. No new
    #: skills tree is added by ADR-034 (FR-019).
    AMBIENT = "ambient"


@dataclass(frozen=True)
class McpInjection:
    """MCP injection strategy for one provider."""

    strategy: McpStrategy
    #: Flag name for :attr:`McpStrategy.FLAG`, otherwise ``None``.
    flag: str | None = None
    #: Project-relative path segments for :attr:`McpStrategy.PROJECT_FILE`.
    project_file: tuple[str, ...] = ()
    #: Locations the CLI itself scans, recorded for documentation and for the
    #: manual smoke launch. SciStudio does not write to these.
    fallback_discovery: tuple[str, ...] = ()

    def project_file_path(self, project_dir: Path) -> Path | None:
        """Absolute path of the provider-owned project-scope MCP config."""
        if not self.project_file:
            return None
        return project_dir.joinpath(*self.project_file)


@dataclass(frozen=True)
class SystemPromptInjection:
    """System-prompt injection strategy for one provider."""

    strategy: SystemPromptStrategy
    #: Flag name for :attr:`SystemPromptStrategy.FLAG_FILE`, otherwise ``None``.
    flag: str | None = None
    #: Whether ``flag`` accepts ``@<file>`` indirection. Only a flag that does
    #: may carry the composed prompt; see :attr:`ambient_only_reason`.
    supports_file_indirection: bool = False
    #: Skills trees the CLI discovers on its own (ADR-040 provisions these).
    skill_dirs: tuple[str, ...] = ()
    #: Why a provider that *has* a system-prompt flag is nonetheless treated as
    #: ambient-only. Qoder's ``--append-system-prompt`` takes literal text with
    #: no ``@<file>`` indirection, and the composed prompt is unbounded, so it
    #: would land on the command line (spec §4.1). ``None`` when not applicable.
    ambient_only_reason: str | None = None


@dataclass(frozen=True)
class CredentialProbe:
    """How login state is detected for one provider (FR-009)."""

    #: Config-root-relative segments of the credential file.
    credential_path: tuple[str, ...]
    #: Provider-owned auth status command, appended to the resolved binary.
    #: Empty when the CLI exposes no machine-readable auth status command.
    auth_status_argv: tuple[str, ...] = ()

    def credential_file(self, config_root: Path) -> Path:
        """Absolute credential file path under *config_root*."""
        return config_root.joinpath(*self.credential_path)


@dataclass(frozen=True)
class ProviderDescriptor:
    """One agent CLI channel's complete adapter definition (FR-002)."""

    key: str
    """Stable provider key used on the wire, in configs, and in workflow YAML."""

    label: str
    """User-facing product name. Returned by ``GET /api/ai/status`` (FR-020b)."""

    kind: ProviderKind

    binary_candidates: tuple[str, ...]
    """Exact binary names, most preferred first.

    A channel variant is NEVER an alternative candidate here — it gets its own
    descriptor (FR-026). Multiple candidates are for genuine aliases of the
    *same* CLI.
    """

    well_known_dirs: tuple[tuple[str, ...], ...]
    """Install directories absent from PATH, as path segments.

    Each entry is resolved against the user home directory, unless its first
    segment is :data:`CONFIG_ROOT`, in which case it is resolved against the
    provider's resolved config root so environment overrides are honoured.
    """

    config_root: tuple[str, ...]
    """Home-relative segments of the provider's default config root."""

    config_root_env: str | None
    """Environment variable that overrides :attr:`config_root`, if any."""

    mcp: McpInjection
    system_prompt: SystemPromptInjection
    credentials: CredentialProbe | None

    bypass_argv: tuple[str, ...]
    """Argv fragment appended when the user opts into bypass permission mode."""

    manual_argv: tuple[str, ...] = ()
    """Argv fragment appended when the user picks **Manual Approve** (#1994).

    Symmetric with :attr:`bypass_argv`, and it exists because silence is not a
    safe default. Passing no flag in safe mode does not mean "ask me"; it means
    "use whatever permission mode this CLI last persisted", and all of these
    CLIs persist one across sessions. A user who picks Manual Approve and gets
    a CLI that silently resumes its saved auto-accept has been handed a control
    that does nothing — the defect the owner hit on 2026-08-06, where
    ``claude-code`` launched in auto mode and ``codex`` launched in YOLO mode
    despite Manual Approve being selected.

    Empty means the CLI exposes no way to *assert* interactive approval on its
    command line. That is a real observation about a CLI surface, not an
    unfilled row, so it must be explained in
    :attr:`manual_argv_absent_reason`; the registry completeness test requires
    exactly one of the two to be present.
    """

    manual_argv_absent_reason: str | None = None
    """Why :attr:`manual_argv` is empty, when it is. ``None`` otherwise."""

    prompt_argv_prefix: tuple[str, ...] | None = ("--",)
    """Argv placed before a positional initial prompt, or ``None`` (#1994).

    ``("--",)`` — the end-of-options separator — is right for every CLI that
    accepts a positional prompt, and it is required rather than cosmetic
    (#1789): ``--mcp-config`` is variadic, so without it Claude Code swallows
    the trailing prompt as another MCP config path and exits.

    ``None`` means the CLI has **no** positional prompt argument, so an AI
    Block task cannot reach it on the command line at all. Kimi Code is the
    observed case: it is a commander.js CLI whose first positional is parsed as
    a *subcommand*, so ``kimi -- "<task>"`` exits 1 with
    ``unknown command '<task>'``. That is the AI Block launch failure the owner
    reported, and appending the prompt anyway is what produced it.
    """

    prompt_unsupported_reason: str | None = None
    """Why :attr:`prompt_argv_prefix` is ``None``, when it is.

    Surfaced verbatim to the user by the AI Block's config validation, so it
    must explain the CLI's limitation rather than name an internal field.
    """

    hook_trust_argv: tuple[str, ...] = ()
    """Argv that lets SciStudio's own provisioned hooks actually run (#1994).

    SciStudio writes the project's hook definitions itself, in files it owns,
    from templates it ships. A CLI that gates hook execution behind an
    interactive trust review is therefore asking the user to vouch for
    SciStudio's own configuration — a prompt the embedded PTY tab never
    surfaces, so the answer is never given and the hooks never fire. The user
    ends up with an agent that has no data-protection and no tool-use
    enforcement, and nothing anywhere says so.

    Empty for every provider that runs project-scope hooks without a review
    gate. Non-empty only where the CLI documents such a gate *and* the flag was
    observed to lift it.
    """

    excluded_dirs: tuple[tuple[str, ...], ...] = ()
    """Directory subtrees a resolution must never come from, as path segments.

    Vendor sidecar copies of a provider binary: real files, with the right
    name, that are nonetheless not the user-facing CLI. The Qoder security-scan
    plugin ships its own pinned build at ``~/.qodersec/bin/qodercli.exe``,
    stale relative to the real install and unauthenticated.

    Resolved like :attr:`well_known_dirs` (home-relative, or config-root
    relative behind the :data:`CONFIG_ROOT` sentinel) and applied to the
    **whole subtree**, so the entry names ``~/.qodersec`` rather than every
    directory under it. The exclusion is checked against the resolved path
    whichever source produced it — PATH or a well-known directory — because a
    user who puts the sidecar directory on PATH must not thereby be offered the
    sidecar (FR-027).
    """

    def resolve_config_root(
        self,
        *,
        home: Path | None = None,
        env: Mapping[str, str] | None = None,
    ) -> Path:
        """Resolve the config root, honouring :attr:`config_root_env`."""
        environ = os.environ if env is None else env
        if self.config_root_env:
            override = environ.get(self.config_root_env)
            if override:
                return Path(override).expanduser()
        base = Path.home() if home is None else home
        return base.joinpath(*self.config_root)

    def _resolve_dirs(
        self,
        segment_lists: tuple[tuple[str, ...], ...],
        *,
        home: Path | None = None,
        env: Mapping[str, str] | None = None,
    ) -> tuple[Path, ...]:
        """Resolve segment lists against the home dir or the config root."""
        base = Path.home() if home is None else home
        config_root = self.resolve_config_root(home=home, env=env)
        resolved: list[Path] = []
        for segments in segment_lists:
            if segments and segments[0] == CONFIG_ROOT:
                resolved.append(config_root.joinpath(*segments[1:]))
            else:
                resolved.append(base.joinpath(*segments))
        return tuple(resolved)

    def well_known_directories(
        self,
        *,
        home: Path | None = None,
        env: Mapping[str, str] | None = None,
    ) -> tuple[Path, ...]:
        """Resolve :attr:`well_known_dirs` to absolute directories."""
        return self._resolve_dirs(self.well_known_dirs, home=home, env=env)

    def excluded_directories(
        self,
        *,
        home: Path | None = None,
        env: Mapping[str, str] | None = None,
    ) -> tuple[Path, ...]:
        """Resolve :attr:`excluded_dirs` to absolute directory subtrees."""
        return self._resolve_dirs(self.excluded_dirs, home=home, env=env)

    def credential_file(
        self,
        *,
        home: Path | None = None,
        env: Mapping[str, str] | None = None,
    ) -> Path | None:
        """Absolute credential file path, or ``None`` when no probe is declared."""
        if self.credentials is None:
            return None
        return self.credentials.credential_file(self.resolve_config_root(home=home, env=env))

    @property
    def is_agent(self) -> bool:
        return self.kind is ProviderKind.AGENT


class ProviderRegistry:
    """Ordered, immutable collection of :class:`ProviderDescriptor` (FR-001)."""

    def __init__(self, descriptors: Sequence[ProviderDescriptor]) -> None:
        by_key: dict[str, ProviderDescriptor] = {}
        for descriptor in descriptors:
            if descriptor.key in by_key:
                raise ValueError(f"duplicate provider key: {descriptor.key!r}")
            by_key[descriptor.key] = descriptor
        self._descriptors: tuple[ProviderDescriptor, ...] = tuple(descriptors)
        self._by_key = by_key

    def __iter__(self) -> Iterator[ProviderDescriptor]:
        return iter(self._descriptors)

    def __len__(self) -> int:
        return len(self._descriptors)

    def __contains__(self, key: object) -> bool:
        return key in self._by_key

    def get(self, key: str) -> ProviderDescriptor:
        """Return the descriptor for *key*.

        Raises
        ------
        KeyError
            When *key* is not a registered provider. The message enumerates the
            accepted set so callers can surface it verbatim (FR-023).
        """
        try:
            return self._by_key[key]
        except KeyError:
            accepted = ", ".join(self._by_key)
            raise KeyError(f"unknown provider {key!r}; expected one of: {accepted}") from None

    @property
    def descriptors(self) -> tuple[ProviderDescriptor, ...]:
        """Every descriptor, agents and the terminal pseudo-provider, in order."""
        return self._descriptors

    def keys(self) -> tuple[str, ...]:
        """Every provider key in registry order, including ``user-terminal``."""
        return tuple(self._by_key)

    def agents(self) -> tuple[ProviderDescriptor, ...]:
        """Agent descriptors only, in registry order (FR-003)."""
        return tuple(d for d in self._descriptors if d.is_agent)

    def agent_keys(self) -> tuple[str, ...]:
        """Agent provider keys only — excludes ``user-terminal`` (FR-003)."""
        return tuple(d.key for d in self.agents())


# ---------------------------------------------------------------------------
# Descriptor table
# ---------------------------------------------------------------------------


def _qoder_channel(
    *,
    key: str,
    label: str,
    binary: str,
    config_dir: str,
) -> ProviderDescriptor:
    """Build one Qoder channel descriptor.

    The two Qoder channels differ **only** in identity fields — key, label,
    binary name, well-known directory, config root, and credential location —
    and share every strategy field byte for byte. This helper fills the shared
    strategy fields once so the pair cannot drift, while the registry still
    holds two fully independent descriptor instances so each resolves, probes,
    and spawns on its own (FR-025, FR-026).

    Their ``--help`` surfaces were compared at 1.1.15 and differ only in the
    program name and description line. If a future release diverges, the shared
    fields split per channel with no structural change.
    """
    return ProviderDescriptor(
        key=key,
        label=label,
        kind=ProviderKind.AGENT,
        binary_candidates=(binary,),
        # The installer places the binary in a directory named after itself:
        # ``~/.qoder/bin/qodercli/qodercli.exe``.
        well_known_dirs=((CONFIG_ROOT, "bin", binary),),
        config_root=(config_dir,),
        # Qoder overrides its config root with a ``--config-dir`` CLI flag, not
        # an environment variable, so there is nothing for discovery to read.
        config_root_env=None,
        mcp=McpInjection(
            strategy=McpStrategy.FLAG,
            flag="--mcp-config",
            fallback_discovery=("<project>/.mcp.json",),
        ),
        system_prompt=SystemPromptInjection(
            strategy=SystemPromptStrategy.AMBIENT,
            flag="--append-system-prompt",
            supports_file_indirection=False,
            skill_dirs=(".agents/skills",),
            ambient_only_reason=(
                "--append-system-prompt takes literal text with no @<file> "
                "indirection; the composed SciStudio prompt is unbounded and "
                "would land on the command line. Both Qoder channels receive "
                "the prompt through .agents/skills like Codex does. "
                "ADR-034 spec §4.1 records this as an assumption to revisit "
                "if a later Qoder release gains @<file> indirection."
            ),
        ),
        credentials=CredentialProbe(
            credential_path=(".auth",),
            # No machine-readable auth status command observed on either
            # channel at 1.1.15; login state is inferred from ``.auth``.
            auth_status_argv=(),
        ),
        bypass_argv=("--dangerously-skip-permissions",),
        # ``--permission-mode`` choices at 1.1.15, verified by running the
        # binary with a bogus value: default | plan | auto | bypass_permissions
        # | accept_edits | dont_ask. ``default`` is the ask-before-acting mode.
        manual_argv=("--permission-mode", "default"),
        # The security-scan plugin's pinned internal copy, observed at 1.1.12
        # with ``{"channel": "global"}`` beside ``qodersec.exe``. Both channels
        # exclude it: it carries the international channel's binary name, so
        # only ``qoder`` can match it by name today, but the two descriptors
        # differ solely in identity fields and a China-channel sidecar would
        # otherwise be an asymmetry waiting to be missed.
        excluded_dirs=((".qodersec",),),
    )


#: ``~/.local/bin`` and ``~/AppData/Roaming/npm`` are both scanned for Claude
#: Code and Codex. The spec's identity table records the *primary* directory
#: per provider, but either CLI can be installed through npm or through its own
#: installer, and the pre-registry ``_windows_user_cli_dirs()`` scanned both for
#: every name. Listing both preserves that behaviour exactly; a descriptor
#: accepting a list of directories is the documented extension point (spec §4.5).
_NPM_AND_LOCAL_BIN = ((".local", "bin"), ("AppData", "Roaming", "npm"))


_CLAUDE_CODE = ProviderDescriptor(
    key="claude-code",
    label="Claude Code",
    kind=ProviderKind.AGENT,
    binary_candidates=("claude",),
    well_known_dirs=_NPM_AND_LOCAL_BIN,
    config_root=(".claude",),
    config_root_env=None,
    mcp=McpInjection(
        strategy=McpStrategy.FLAG,
        flag="--mcp-config",
        fallback_discovery=("<project>/.mcp.json",),
    ),
    system_prompt=SystemPromptInjection(
        strategy=SystemPromptStrategy.FLAG_FILE,
        flag="--append-system-prompt",
        supports_file_indirection=True,
        skill_dirs=(".claude/skills",),
    ),
    credentials=CredentialProbe(
        credential_path=(".credentials.json",),
        auth_status_argv=("auth", "status", "--json"),
    ),
    bypass_argv=("--dangerously-skip-permissions",),
    # ``--permission-mode`` choices at 2.x: acceptEdits | auto |
    # bypassPermissions | manual | dontAsk | plan. ``manual`` is the literal
    # ask-me mode. Without it Claude Code resumes the mode persisted in
    # ``~/.claude/settings.json``, which is how a Manual Approve launch came up
    # in auto mode on the owner's machine (#1994 finding 2).
    manual_argv=("--permission-mode", "manual"),
)

_CODEX = ProviderDescriptor(
    key="codex",
    label="Codex",
    kind=ProviderKind.AGENT,
    binary_candidates=("codex",),
    well_known_dirs=_NPM_AND_LOCAL_BIN,
    config_root=(".codex",),
    config_root_env=None,
    mcp=McpInjection(
        strategy=McpStrategy.CODEX_OVERRIDES,
        # Codex does not accept ``--mcp-config``; it walks project-scope and
        # user-scope ``config.toml`` files. The embedded chat owns the spawn, so
        # it passes the current project entry explicitly via ``-c`` overrides
        # instead of trusting discovery.
        flag=None,
        fallback_discovery=("~/.codex/config.toml", "<project>/.codex/config.toml"),
    ),
    system_prompt=SystemPromptInjection(
        strategy=SystemPromptStrategy.AMBIENT,
        flag=None,
        supports_file_indirection=False,
        skill_dirs=(".agents/skills",),
    ),
    credentials=CredentialProbe(
        credential_path=("auth.json",),
        auth_status_argv=("login", "status"),
    ),
    bypass_argv=("--dangerously-bypass-approvals-and-sandbox",),
    # ``-a/--ask-for-approval`` policies at 0.139.0: untrusted | on-failure
    # (deprecated) | on-request | never. ``untrusted`` is the only value that
    # guarantees an escalation to the human for anything outside the trusted
    # command set; ``on-request`` delegates the decision to the model, which is
    # not what "Manual Approve" promises the user.
    manual_argv=("--ask-for-approval", "untrusted"),
    # #1994 finding 3. Codex 0.130+ gates project-scope hooks behind an
    # interactive trust review: the TUI opens a panel reading
    # ``SessionStart 2 0 2 … Press t to trust all; enter to review hooks``
    # (declared / trusted / untrusted), and until the user answers it, none of
    # SciStudio's provisioned hooks run. Observed live at 0.139.0 against a
    # project SciStudio had just provisioned — the declarations loaded and
    # parsed, and fired nothing.
    #
    # The trust decision is about SciStudio's *own* hook files, written from
    # SciStudio's own templates, so this is precisely the "automation that
    # already vets hook sources" case the flag is documented for. Without it a
    # SciStudio-launched Codex tab runs with no data-protection and no
    # tool-use enforcement at all, silently.
    hook_trust_argv=("--dangerously-bypass-hook-trust",),
)

_KIMI_CODE = ProviderDescriptor(
    key="kimi-code",
    label="Kimi Code",
    kind=ProviderKind.AGENT,
    binary_candidates=("kimi",),
    # Not on PATH by default. The install dir hangs off the config root so a
    # non-default ``KIMI_CODE_HOME`` is honoured (spec §2 edge cases).
    well_known_dirs=((CONFIG_ROOT, "bin"),),
    config_root=(".kimi-code",),
    config_root_env="KIMI_CODE_HOME",
    mcp=McpInjection(
        strategy=McpStrategy.PROJECT_FILE,
        flag=None,
        project_file=(".kimi-code", "mcp.json"),
        fallback_discovery=(
            "<KIMI_CODE_HOME>/mcp.json",
            "<project>/.mcp.json",
            "<cwd>/.kimi-code/mcp.json",
        ),
    ),
    system_prompt=SystemPromptInjection(
        strategy=SystemPromptStrategy.AMBIENT,
        # ``--agent-file <path>`` exists but selects an agent definition rather
        # than appending to the system prompt, so it is not a prompt carrier.
        flag=None,
        supports_file_indirection=False,
        skill_dirs=(
            ".claude/skills",
            ".codex/skills",
            ".agents/skills",
            ".kimi-code/skills",
        ),
    ),
    credentials=CredentialProbe(
        credential_path=("credentials", "kimi-code.json"),
        auth_status_argv=("doctor",),
    ),
    bypass_argv=("--auto",),
    # Observed at 0.33.0: the only permission flags are ``-y/--yolo`` and
    # ``--auto``, both of which *loosen* approval. There is no flag that
    # asserts interactive approval, so manual mode is the absence of both.
    manual_argv=(),
    manual_argv_absent_reason=(
        "kimi 0.33.0 exposes only the loosening flags -y/--yolo and --auto; it "
        "has no flag that asserts interactive approval, so Manual Approve is "
        "expressed by passing neither. Revisit when Kimi Code gains an explicit "
        "permission-mode flag."
    ),
    # ``kimi --help`` at 0.33.0 shows ``Usage: kimi [options] [command]`` with
    # no ``[prompt]`` positional; the prompt goes through ``-p/--prompt``, which
    # is a one-shot non-interactive mode that prints and exits. A positional
    # argument is parsed as a subcommand, so ``kimi -- "<task>"`` exits 1 with
    # ``unknown command`` — verified by running the installed binary (#1994).
    prompt_argv_prefix=None,
    prompt_unsupported_reason=(
        "Kimi Code has no positional prompt argument: its only prompt flag, "
        "-p/--prompt, runs one prompt non-interactively and exits, so it cannot "
        "seed the interactive session an AI Block needs. Kimi Code works as a "
        "hand-launched chat tab; pick another provider for an AI Block."
    ),
)

_QODER = _qoder_channel(
    key="qoder",
    label="Qoder CLI",
    binary="qodercli",
    config_dir=".qoder",
)

_QODER_CN = _qoder_channel(
    key="qoder-cn",
    label="Qoder CLI (China)",
    binary="qoderclicn",
    config_dir=".qoder-cn",
)

_USER_TERMINAL = ProviderDescriptor(
    key="user-terminal",
    label="Terminal",
    kind=ProviderKind.TERMINAL,
    # The shell is resolved from ``SHELL`` / platform defaults, not from a
    # registered CLI name, so there are no binary candidates to match.
    binary_candidates=(),
    well_known_dirs=(),
    config_root=(),
    config_root_env=None,
    mcp=McpInjection(strategy=McpStrategy.NONE),
    system_prompt=SystemPromptInjection(strategy=SystemPromptStrategy.AMBIENT),
    credentials=None,
    bypass_argv=(),
)

#: Ordered registry. Order is the frozen cross-agent contract:
#: ``claude-code``, ``codex``, ``kimi-code``, ``qoder``, ``qoder-cn``, then the
#: ``user-terminal`` TERMINAL-kind entry. It drives the status endpoint order,
#: the WS whitelist, and the AI Block enum.
REGISTRY = ProviderRegistry(
    (
        _CLAUDE_CODE,
        _CODEX,
        _KIMI_CODE,
        _QODER,
        _QODER_CN,
        _USER_TERMINAL,
    )
)


# ---------------------------------------------------------------------------
# Module-level convenience API (the frozen cross-agent import surface)
# ---------------------------------------------------------------------------


def get(key: str) -> ProviderDescriptor:
    """Return the descriptor for *key*, raising ``KeyError`` when unknown."""
    return REGISTRY.get(key)


def agent_descriptors() -> tuple[ProviderDescriptor, ...]:
    """Agent descriptors in registry order (excludes ``user-terminal``)."""
    return REGISTRY.agents()


def agent_keys() -> tuple[str, ...]:
    """Agent provider keys in registry order (excludes ``user-terminal``)."""
    return REGISTRY.agent_keys()


def provider_keys() -> tuple[str, ...]:
    """Every provider key in registry order, including ``user-terminal``."""
    return REGISTRY.keys()


# ---------------------------------------------------------------------------
# Binary discovery
# ---------------------------------------------------------------------------


def _is_inside(path: Path, directory: Path) -> bool:
    """Whether *path* lies anywhere inside the *directory* subtree.

    Compares fully resolved, case-normalised paths, so a symlinked or
    differently-cased spelling of an excluded directory cannot walk around the
    check on Windows or macOS.
    """
    try:
        candidate = Path(os.path.normcase(os.path.realpath(path)))
        root = Path(os.path.normcase(os.path.realpath(directory)))
    except OSError:  # pragma: no cover - realpath is non-raising on all supported OSes
        return False
    return candidate == root or root in candidate.parents


def resolve_executable(
    name: str,
    *,
    which: Callable[[str], str | None] | None = None,
    well_known_dirs: Sequence[Path] = (),
    excluded_dirs: Sequence[Path] = (),
) -> str | None:
    """Resolve *name* to a concrete executable path, or ``None``.

    Two independent sources, in this order:

    1. **PATH**, via ``which``. On Windows, npm global installs commonly place
       both ``codex`` (a Unix shell wrapper) and ``codex.cmd`` on PATH; Python
       can return the bare wrapper, and pywinpty's CreateProcess spawn path
       cannot execute it reliably, so extensioned launchers win.
    2. **Registered well-known directories**, for CLIs that are not on PATH at
       all (Kimi Code and both Qoder channels never are).

    PATH is consulted first on purpose: a CLI genuinely on PATH is the one the
    user's own shell would run, and preferring a copy in a well-known directory
    over it would be surprising.

    Two separate rules keep a vendor sidecar copy out (FR-027), and both are
    needed:

    *Exact names, registered directories only.* Matching is by exact binary
    name plus a Windows launcher extension inside a directory the registry
    named. There is no globbing and no broad home-directory search, so a stray
    ``qodercli.exe`` somewhere under ``$HOME`` is never discovered.

    *Excluded subtrees.* That first rule is not sufficient on its own, because
    it constrains only the well-known-directory scan. ``which`` searches
    whatever the user put on PATH, so a user whose PATH includes
    ``~/.qodersec/bin`` would otherwise be handed the security scanner's stale,
    pinned copy — FR-027's promise is unconditional and does not carve out that
    case. ``excluded_dirs`` is therefore checked against the resolved path
    whichever source produced it, and rejecting a candidate does not fall back
    to a sibling provider's binary: it simply removes that candidate.

    The well-known-directory scan runs on every platform, not just Windows:
    Kimi Code and Qoder are off PATH everywhere, and FR-005 requires the chat
    path and the AI Block path to agree on the result on every OS.
    """
    resolver = shutil.which if which is None else which
    directories = tuple(well_known_dirs)
    excluded = tuple(excluded_dirs)

    def permitted(candidate: str | None) -> str | None:
        """Drop a candidate that resolves inside an excluded subtree."""
        if candidate is None:
            return None
        if any(_is_inside(Path(candidate), directory) for directory in excluded):
            return None
        return candidate

    on_path = permitted(resolver(name))

    if sys.platform != "win32":
        if on_path:
            return on_path
        for directory in directories:
            candidate = directory / name
            if candidate.is_file() and permitted(str(candidate)):
                return str(candidate)
        return None

    extensioned: list[str] = []
    for suffix in WINDOWS_EXECUTABLE_SUFFIXES:
        candidate_on_path = permitted(resolver(name + suffix))
        if candidate_on_path:
            extensioned.append(candidate_on_path)
    for directory in directories:
        for suffix in WINDOWS_EXECUTABLE_SUFFIXES:
            candidate_path = directory / f"{name}{suffix}"
            if candidate_path.is_file() and permitted(str(candidate_path)):
                extensioned.append(str(candidate_path))

    if extensioned:
        if on_path and Path(on_path).suffix.lower() in WINDOWS_EXECUTABLE_SUFFIXES:
            return on_path
        return extensioned[0]
    return on_path


def resolve_binary(
    descriptor: ProviderDescriptor,
    *,
    which: Callable[[str], str | None] | None = None,
    home: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> Path | None:
    """Resolve *descriptor* to an installed binary, or ``None``.

    Off-PATH aware and exact-name only. Because each channel descriptor carries
    its own binary name and its own well-known directory, a missing channel
    binary can never resolve to the sibling channel's binary (FR-026).

    Sidecar exclusion is descriptor data (:attr:`ProviderDescriptor.excluded_dirs`)
    rather than a special case in the resolver, so a future vendor that ships a
    pinned internal copy of its own CLI is one registry row, not a code change.

    ``home`` and ``env`` exist so tests can drive a fake home directory without
    depending on the CLIs installed on the developer's machine.
    """
    directories = descriptor.well_known_directories(home=home, env=env)
    excluded = descriptor.excluded_directories(home=home, env=env)
    for name in descriptor.binary_candidates:
        resolved = resolve_executable(
            name,
            which=which,
            well_known_dirs=directories,
            excluded_dirs=excluded,
        )
        if resolved:
            return Path(resolved)
    return None
