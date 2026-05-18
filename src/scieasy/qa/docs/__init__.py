"""Doc-set frontmatter schemas (ADR-044 §5).

Per ADR-044 the four documentation categories (``contributing``,
``user``, ``prod-agent``, ``doc-guide``) each receive a dedicated
frontmatter schema, dispatched by file path in
``scripts/audit/frontmatter_lint.py``. This subpackage owns those
shapes; the four ADR / spec frontmatter schemas remain in
``scieasy.qa.schemas``.
"""

from .schemas import (
    AutoGenSource,
    DocAudience,
    DocCategory,
    DocGuideFrontmatter,
    Generation,
    ProdAgentDocFrontmatter,
    UserDocFrontmatter,
    WorkflowDocFrontmatter,
)

__all__ = [
    "AutoGenSource",
    "DocAudience",
    "DocCategory",
    "DocGuideFrontmatter",
    "Generation",
    "ProdAgentDocFrontmatter",
    "UserDocFrontmatter",
    "WorkflowDocFrontmatter",
]
