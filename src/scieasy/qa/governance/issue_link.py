"""Issue linkage helpers for ADR-042 AI tasks."""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, Field

from scieasy.qa.governance.local_gate import IssueRecord


class IssueQuery(BaseModel):
    repo: str
    title: str
    body: str
    labels: list[str] = Field(default_factory=list)
    close_existing: bool = True


class IssueClient(Protocol):
    def search_issues(self, query: IssueQuery) -> list[IssueRecord]: ...

    def create_issue(self, query: IssueQuery) -> IssueRecord: ...


def resolve_or_create(
    query: IssueQuery,
    *,
    client: IssueClient,
    create_if_missing: bool,
) -> IssueRecord:
    matches = client.search_issues(query)
    if matches:
        return matches[0]
    if not create_if_missing:
        raise RuntimeError("No matching issue and create_if_missing=False")
    return client.create_issue(query)
