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
relative to the real install. :func:`resolve_binary` therefore matches an exact
binary name inside a *registered* well-known directory and never globs under
the home directory, which is what keeps the sidecar out of the provider list
(FR-027).
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

    def well_known_directories(
        self,
        *,
        home: Path | None = None,
        env: Mapping[str, str] | None = None,
    ) -> tuple[Path, ...]:
        """Resolve :attr:`well_known_dirs` to absolute directories."""
        base = Path.home() if home is None else home
        config_root = self.resolve_config_root(home=home, env=env)
        resolved: list[Path] = []
        for segments in self.well_known_dirs:
            if segments and segments[0] == CONFIG_ROOT:
                resolved.append(config_root.joinpath(*segments[1:]))
            else:
                resolved.append(base.joinpath(*segments))
        return tuple(resolved)

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
                "the prompt through .agents/skills like Codex does "
                "(spec §4.1). Revisit if Qoder gains @<file> support."
            ),
        ),
        credentials=CredentialProbe(
            credential_path=(".auth",),
            # No machine-readable auth status command observed on either
            # channel at 1.1.15; login state is inferred from ``.auth``.
            auth_status_argv=(),
        ),
        bypass_argv=("--dangerously-skip-permissions",),
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


def resolve_executable(
    name: str,
    *,
    which: Callable[[str], str | None] | None = None,
    well_known_dirs: Sequence[Path] = (),
) -> str | None:
    """Resolve *name* to a concrete executable path, or ``None``.

    Two independent sources, in this order:

    1. **PATH**, via ``which``. On Windows, npm global installs commonly place
       both ``codex`` (a Unix shell wrapper) and ``codex.cmd`` on PATH; Python
       can return the bare wrapper, and pywinpty's CreateProcess spawn path
       cannot execute it reliably, so extensioned launchers win.
    2. **Registered well-known directories**, for CLIs that are not on PATH at
       all (Kimi Code and both Qoder channels never are).

    Matching is by **exact** binary name (plus a Windows launcher extension)
    inside a *registered* directory. There is deliberately no globbing and no
    broad home-directory search, which is what keeps the Qoder security-scan
    sidecar copy at ``~/.qodersec/bin/qodercli.exe`` from ever being offered as
    a chat provider (FR-027).

    The well-known-directory scan runs on every platform, not just Windows:
    Kimi Code and Qoder are off PATH everywhere, and FR-005 requires the chat
    path and the AI Block path to agree on the result on every OS.
    """
    resolver = shutil.which if which is None else which
    on_path = resolver(name)
    directories = tuple(well_known_dirs)

    if sys.platform != "win32":
        if on_path:
            return on_path
        for directory in directories:
            candidate = directory / name
            if candidate.is_file():
                return str(candidate)
        return None

    extensioned: list[str] = []
    for suffix in WINDOWS_EXECUTABLE_SUFFIXES:
        candidate_on_path = resolver(name + suffix)
        if candidate_on_path:
            extensioned.append(candidate_on_path)
    for directory in directories:
        for suffix in WINDOWS_EXECUTABLE_SUFFIXES:
            candidate_path = directory / f"{name}{suffix}"
            if candidate_path.is_file():
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

    ``home`` and ``env`` exist so tests can drive a fake home directory without
    depending on the CLIs installed on the developer's machine.
    """
    directories = descriptor.well_known_directories(home=home, env=env)
    for name in descriptor.binary_candidates:
        resolved = resolve_executable(name, which=which, well_known_dirs=directories)
        if resolved:
            return Path(resolved)
    return None
