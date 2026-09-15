---
adr: 52
addendum: 2
title: "The Workflow YAML File Format Is Public API With A Generated Reference"
status: Proposed
date_created: 2026-09-15
date_accepted: null
date_superseded: null

supersedes: []
superseded_by: null
related: [42, 44, 52]
closes_issues: [2434]
tracking_issue: 2434

is_code_implementation: true
governs:
  modules:
    - scistudio.workflow.schema
  contracts:
    - scistudio.workflow.schema.WorkflowFileModel
    - scistudio.workflow.validator.validate_workflow
  entry_points: []
  files:
    - docs/adr/ADR-052-addendum2.md
    - scripts/docs/build_workflow_reference.py
    - scripts/docs/build_reference.py
    - src/scistudio/_user_guide/api-reference/workflow-yaml.md
  excludes: []

tests:
  - tests/docs/test_workflow_reference.py
agent_editable: false
assisted_by:
  - "claude-code:claude-opus-5"

phase: implementation
tags: [api, public-contract, stability, documentation, workflow]
owner: "@jiazhenz026"
co_authors: ["@claude"]
language_source: en
translations: []
---

# ADR-052 Addendum 2: The Workflow YAML File Format Is Public API With A Generated Reference

## 1. Decision Summary

ADR-052 generates the public API reference from code so it cannot drift (Section
7), but it covers Python canonical roots only. The workflow YAML file is a
contract authors and agents write by hand, and it is not Python: until now it was
documented only as hand-written prose (the agent reference's workflow schema page
and the workflow-building skill), which already disagrees with the loader on
which keys are required.

This addendum brings the workflow file format into ADR-052's model:

- its surface is declared by the models that load and save the file;
- it is `provisional` as a whole;
- its reference page is generated from those models and the validator, beside the
  Python reference, and a test fails when the committed page differs from a fresh
  render.

It parallels Addendum 1 (the panel contract, proposed in PR #2432), which makes
the same decision for the panel SDK, components, and descriptor. The two addenda
share Section 7 of ADR-052 and the packaged reference directory; neither changes
the other's surface. If Addendum 1 lands under a different number, this
addendum's number and cross-reference follow it.

### 1.1 Problems Addressed

| Problem | Detailed section |
|---|---|
| ADR-052 §2 and §7 cover Python roots only; the workflow file format has no declared public surface. | Section 3 |
| ADR-052 §5's decorators cannot mark a YAML key, so the format's stability is not recorded where readers see it. | Section 4 |
| The format is documented only by hand, which drifts from the loader, serializer, and validator. | Section 5 |

## 2. Scope

In scope: the keys, types, defaults, and load-time rules of a workflow YAML file;
the rules tying a workflow to its file name and run identity; the graph checks
workflow validation runs; the JSON Schema of the file.

Out of scope: the HTTP API's workflow payloads (covered by the OpenAPI contract);
block configuration schemas, which each block declares; rewriting the skills,
user guide, or agent reference, which link to the generated page instead of
restating it.

## 3. Declaring The Public Surface

The format's surface is the pydantic model tree rooted at
`scistudio.workflow.schema.WorkflowFileModel`, the model the loader, the
`write_workflow` agent tool, and the validation tool parse every file through.
The generator enforces that the models describe it:

- every model carries its own docstring, which becomes its section summary;
- every key carries a `Field(description=...)`, which becomes its table entry;
- every field validator carries a docstring, which becomes a load-time rule;
- the handling of keys a model does not declare is read from its `extra` setting.

A key, model, or rule added without its description fails generation.

The graph checks are declared by the docstring of
`scistudio.workflow.validator.validate_workflow`, and the file name and run
identity rules by the `scistudio.workflow.identity` module docstring. The example
files on the page are written by the serializer that saves workflows, and a test
loads, expands, and validates them against the built-in blocks.

## 4. Stability

The whole format is `provisional` (ADR-052 §5): usable, and changeable in a minor
release with a changelog entry. The tier is recorded once, in the generator, and
stamped on the page. Per-key tiers are not recorded; when the format becomes
`stable`, a later addendum decides how a change is versioned for files already
saved in projects.

## 5. Generated Reference And Freshness

`scripts/docs/build_workflow_reference.py` renders `workflow-yaml.md` into the
packaged API reference. `scripts/docs/build_reference.py` calls it and links the
page from the reference index, so the documentation site and the reference
provisioned into projects include it. The page is a generated artifact under
ADR-042's rule. `tests/docs/test_workflow_reference.py` fails when the committed
page differs from a fresh render and exercises each drift guard of Section 3;
`tests/docs/test_reference_language.py` holds the page to the same writing rules
as the rest of the packaged reference.

The generator is plain Python over pydantic's `model_json_schema()`; it adds no
dependency.

## 6. Verification And Tooling Impact

- `tests/docs/test_workflow_reference.py`: freshness, the index link, the
  stability stamp, every model and key rendered, every validation check rendered,
  the examples round-tripping through the loader and validating against the
  built-in blocks, and one test per drift guard.
- `tests/api/test_user_docs.py`: the published sidebar includes the page.

## 7. Consequences

- Hand-written workflow documentation (the agent reference's workflow schema page,
  the workflow-building skill, and the user guide) can link
  to the generated page instead of restating keys and rules.
- Changing a workflow model, a key description, a load-time rule, or the
  validator's documented checks requires regenerating the page in the same change.
- Field descriptions in `scistudio.workflow.schema` and the `validate_workflow`
  docstring become contract text, held to the reference writing rules.

## 8. Alternatives Considered

- **Commit a standalone JSON Schema file.** Rejected as a second source of truth
  beside the models; the page embeds the schema generated from them instead.
- **Keep the hand-written schema page and review it.** Rejected: it already
  disagrees with the loader.
- **Fold the workflow format into Addendum 1.** Rejected: the panel contract and
  the workflow file are separate surfaces with separate owners and version
  signals, and keeping them apart lets either change without the other.
