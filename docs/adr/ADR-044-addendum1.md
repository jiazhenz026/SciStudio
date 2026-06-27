---
adr: 44
addendum: 1
title: "Usable SubWorkflow Authoring: Auto-Derived Exposed Ports, Port Provenance, And Run-Scoped Status"
status: Accepted
date_created: 2026-06-27
date_accepted: 2026-06-27
date_superseded: null

supersedes: []
superseded_by: null
related: [44]
closes_issues: [890]
tracking_issue: 1357

is_code_implementation: true
governs:
  modules:
    - scistudio.workflow
    - scistudio.api.runtime
  contracts:
    - scistudio.workflow.subworkflow_ports.derive_exposed_ports
    - scistudio.workflow.subworkflow_ports.resolve_port_surface
  entry_points: []
  files:
    - docs/adr/ADR-044-addendum1.md
    - src/scistudio/workflow/subworkflow_ports.py
    - src/scistudio/api/runtime/_workflows.py
    - src/scistudio/api/schemas.py
  excludes:
    - tests/**
    - frontend/**
    - docs/audit/**

tests:
  - tests/workflow/test_subworkflow_ports.py
agent_editable: false
assisted_by:
  - "claude:opus-4-8"
phase: planning
tags:
  - adr-044
  - subworkflow
  - exposed-ports
  - run-status
owner: "@jiazhenz026"
co_authors: []
language_source: en
translations: []
---

# ADR-044 Addendum 1: Usable SubWorkflow Authoring

## 1. Decision Summary

ADR-044 made `SubWorkflowBlock` an authoring-only container whose port surface
is derived from the referenced file's `exposed_ports` section, with the section
**hand-authored** (§6: "Files with no `exposed_ports` are still referenceable
but expose zero ports … legal but not useful"). Live use surfaced that this
makes the feature unusable for the target user (a bench scientist who does not
hand-edit workflow YAML): a freshly imported subworkflow exposes zero ports, so
its open boundary inputs cannot be connected and a run fails strict validation
("required input port has no incoming connection").

This addendum makes subworkflow authoring usable end to end. The decisions
below were taken in an owner-directed live session (issue #890 / PR #1736).

### 1.1 Decisions

1. **Auto-derive `exposed_ports` at import.** When a workflow file is imported
   as a subworkflow and declares no `exposed_ports`, the import writes a derived
   section into the project copy. Every **input port with no incoming edge** and
   every **output port with no outgoing edge** is an *open* boundary port and is
   exposed. A file that already declares `exposed_ports` is left authoritative.
   This realises the ADR-044 §7 note that an import "adds an `exposed_ports`
   section to the copy" rather than requiring manual authoring.

2. **Exposed-port provenance.** Each resolved exposed port carries the owning
   inner block's `block_id`, `block_type`, `block_label` (registry display
   name), and inner `port`. The exposed name is the opaque dot form
   `"<block_id>.<port>"`; provenance lets the editor name the owning block.

3. **Run-scoped status for the collapsed and expanded views.** The collapsed
   container has no run id of its own — at run start its inner nodes are
   flattened to prefixed ids `"<subworkflowNodeId>__<innerId>"`. The collapsed
   node now shows a status glyph rolled up from those inner states, and a child
   canvas opened by double-click carries a *run-scope prefix* so each inner node
   maps to its flattened run id (composed for nesting). Preview data for a
   subworkflow node maps its exposed outputs back to the inner block outputs.

4. **Path-keyed subworkflow tabs.** Imported copies under `subworkflows/` share
   the source file's internal `workflow.id`, so id-based tab dedup opened the
   wrong file on double-click. Workflow tabs gained a `tabKey` dedup identity
   that defaults to `workflowId` (legacy behavior) and is the referenced
   `ref.path` for subworkflow opens, so each copy opens as its own tab.

These are additive: a hand-authored `exposed_ports` section, ordinary workflow
opens, and the load-time flattening contract (ADR-044 §4) are unchanged.

## 2. Open-Port Derivation

`scistudio.workflow.subworkflow_ports.derive_exposed_ports(definition, registry)`
computes the surface from the graph:

- An **input** port `node:port` is open when no edge targets it.
- An **output** port `node:port` is open when no edge sources it.
- Each open port is exposed with `name == internal == "<node_id>.<port>"`. The
  node id is unique within the file, so generated names never collide even when
  several inner nodes share a port name (e.g. two unconnected `spectra` inputs).
- A registry is required to read each node's effective ports; a node whose block
  cannot be instantiated contributes nothing (best-effort, never fails import).

`ApiRuntime.import_subworkflow_file` calls this after copying the file and writes
the derived section only when the file declares none.

## 3. Resolved-Port Provenance

`resolve_port_surface` attaches `block_id` / `block_type` / `block_label` /
`port` to every entry of the response-only `resolved_ports` surface
(`SubworkflowPortEntry`, defaulted for backward compatibility). The label falls
back to `block_type`, then `block_id`, when no registry display name exists.

## 4. Scope

In scope (this addendum's `governs.files`): the derivation helper and import
wiring (`scistudio.workflow`, `scistudio.api.runtime`) and the response schema
field (`scistudio.api.schemas`). The frontend run-status, preview-mapping,
port-panel, tab-identity, and config-layout changes are delivered in the same
PR but are presentation-layer and excluded from this ADR's governed modules.

Out of scope: hand-authored `exposed_ports` preview mapping when the exposed
name is not in `"<block>.<port>"` form (tracked in code; auto-derived ports —
the import default — always encode it). The pre-existing workflowId↔file-path
mapping for an edited subworkflow-copy tab is unchanged.

## 5. Verification

- `tests/workflow/test_subworkflow_ports.py` covers open-port derivation
  (open-only, shared-name disambiguation, no-registry), and provenance
  (`block_id`/`port`/`block_type`/`block_label`, label fallback).
- Frontend unit tests cover the status roll-up, scoped/exposed output mapping,
  path-keyed tab dedup, the subworkflow port panel, and the config layout.
- Live verification (PR #1736): import auto-derives the surface; the collapsed
  and expanded views show run status and preview data; the port panel names the
  owning block; double-click opens the referenced copy.

## 6. Consequences

- Importing a workflow as a subworkflow yields a usable, connectable node with
  no YAML hand-editing — the realistic path for the target user.
- The derived `exposed_ports` section is written into the project copy, so the
  imported file is a normalized artifact (it is re-serialized on import).
- Exposing *all* open ports can surface many handles for a large pipeline; this
  is intentional (open boundary = required wiring) and visible in the port panel.

## 7. References

- ADR-044 (§4 flattening, §6 exposed_ports, §7 import-adds-section note).
- Issue #890; PR #1736.
