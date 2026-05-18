"""Doc-category frontmatter schemas (ADR-044 §5).

One schema per documentation category, dispatched by file path:

- ``WorkflowDocFrontmatter`` — ``docs/contributing/workflows/*.md``.
- ``UserDocFrontmatter`` — ``docs/user/**/*.md``.
- ``ProdAgentDocFrontmatter`` — ``docs/prod-agent/**/*.md`` (ADR-040).
- ``DocGuideFrontmatter`` — ``docs/doc-guide/**/*.md`` (meta-meta).

Per SUMMARY ``X3`` / TC-1A.10 manager defaults the vestigial imports of
``RepoRelativePath`` / ``AssistedByLine`` / ``LocaleCode`` /
``AgentEditable`` from ADR-044 §5.1 are dropped (none are used in the
four schemas). The import for ``Translation`` comes from
``scieasy.qa.schemas.frontmatter`` per the ADR; the three scalar type
aliases (``ADRRef``, ``GitHandle``, ``IssueRef``) are sourced from
``scieasy.qa.schemas._common`` directly — they are not re-exported with
explicit ``as`` aliases from ``frontmatter.py`` (1A-a's owned file),
so mypy ``--strict`` raises ``attr-defined`` if we import them from
``frontmatter``. Deviation recorded in the PR body.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from scieasy.qa.schemas._common import ADRRef, GitHandle, IssueRef
from scieasy.qa.schemas.frontmatter import Translation


class Generation(StrEnum):
    """Doc-source authorship kind.

    NOTE: ``Generation`` is independent of ADR-042 ``Translation.auto_generated``.
    ``Generation`` classifies the source-doc authorship
    (``AUTO`` = code-generated / ``HAND`` = hand-authored / ``HYBRID`` =
    mixed). ``Translation.auto_generated`` flags only whether
    ``docs/zh-CN/X.md`` was machine-rendered from the English source. A
    ``HAND`` source doc may still have an auto_generated translation.
    """

    AUTO = "auto"
    HAND = "hand"
    HYBRID = "hybrid"


class DocAudience(StrEnum):
    """Intended-reader tag for a documentation file."""

    HUMAN = "human"
    AGENT = "agent"
    BOTH = "both"
    END_USER = "end-user"
    OPERATOR = "operator"
    MAINTAINER = "maintainer"


class DocCategory(StrEnum):
    """ADR-044 documentation category."""

    CONTRIBUTING = "contributing"
    USER = "user"
    PROD_AGENT = "prod-agent"
    DOC_GUIDE = "doc-guide"


class AutoGenSource(BaseModel):
    """Auto-generation source descriptor for AUTO / HYBRID docs."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal[
        "entry-points",
        "pydantic-model",
        "typer-cli",
        "openapi",
        "sphinx-autoapi",
        "facts-registry",
        "custom",
    ]
    targets: list[str]  # module paths / file paths / EP groups
    generator: str  # dotted path to generator function
    last_generated_sha: str | None = None


class WorkflowDocFrontmatter(BaseModel):
    """Frontmatter for ``docs/contributing/workflows/*.md``."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    workflow_id: Annotated[str, Field(pattern=r"^[a-z][a-z0-9-]+$")]
    title: str = Field(min_length=4, max_length=120)
    audience: list[DocAudience]
    category: Literal[DocCategory.CONTRIBUTING] = DocCategory.CONTRIBUTING
    generation: Literal[Generation.HAND] = Generation.HAND

    related_skills: list[str] = Field(default_factory=list)
    related_adrs: list[ADRRef] = Field(default_factory=list)
    related_personas: list[str] = Field(default_factory=list)
    related_workflows: list[str] = Field(default_factory=list)

    maintenance_owner: GitHandle
    last_reviewed: date

    length_exception_reason: str | None = None
    length_exception_issue: IssueRef | None = None

    translations: list[Translation] = Field(default_factory=list)

    @model_validator(mode="after")
    def _exception_paired_with_issue(self) -> WorkflowDocFrontmatter:
        if self.length_exception_reason and self.length_exception_issue is None:
            raise ValueError("length_exception_reason requires length_exception_issue")
        return self


class UserDocFrontmatter(BaseModel):
    """Frontmatter for ``docs/user/**/*.md``."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    doc_id: Annotated[str, Field(pattern=r"^[a-z][a-z0-9/-]+$")]
    title: str = Field(min_length=4, max_length=120)
    category: Literal[DocCategory.USER] = DocCategory.USER
    audience: list[DocAudience]
    generation: Generation
    source: AutoGenSource | None = None

    related_adrs: list[ADRRef] = Field(default_factory=list)
    related_user_docs: list[str] = Field(default_factory=list)
    related_blocks: list[str] = Field(default_factory=list)

    maintenance_owner: GitHandle
    last_reviewed: date
    translations: list[Translation] = Field(default_factory=list)

    @model_validator(mode="after")
    def _auto_requires_source(self) -> UserDocFrontmatter:
        if self.generation in (Generation.AUTO, Generation.HYBRID) and self.source is None:
            raise ValueError(f"generation={self.generation.value} requires source: AutoGenSource")
        return self


class ProdAgentDocFrontmatter(BaseModel):
    """Frontmatter for ``docs/prod-agent/**/*.md``.

    Specifically governs documentation about ADR-040's
    production-environment embedded-agent reliability stack (see
    ADR-044 Appendix A for the corrected ADR-040 reference card).
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    doc_id: Annotated[str, Field(pattern=r"^[a-z][a-z0-9-]+$")]
    title: str = Field(min_length=4, max_length=120)
    category: Literal[DocCategory.PROD_AGENT] = DocCategory.PROD_AGENT
    audience: list[DocAudience]
    governs_adr: Literal[40] = 40
    generation: Literal[Generation.HAND] = Generation.HAND

    related_addenda: list[Literal["A1", "A2", "A3", "A4"]] = Field(default_factory=list)
    related_user_docs: list[str] = Field(default_factory=list)
    related_known_gaps: list[str] = Field(default_factory=list)

    maintenance_owner: GitHandle
    last_reviewed: date
    translations: list[Translation] = Field(default_factory=list)


class DocGuideFrontmatter(BaseModel):
    """Frontmatter for ``docs/doc-guide/**/*.md`` (meta-meta)."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    doc_id: Annotated[str, Field(pattern=r"^[a-z][a-z0-9-]+$")]
    title: str = Field(min_length=4, max_length=120)
    category: Literal[DocCategory.DOC_GUIDE] = DocCategory.DOC_GUIDE
    generation: Literal[Generation.HAND] = Generation.HAND

    applies_to_categories: list[DocCategory]
    related_adrs: list[ADRRef] = Field(default_factory=list)

    maintenance_owner: GitHandle
    last_reviewed: date
    translations: list[Translation] = Field(default_factory=list)
