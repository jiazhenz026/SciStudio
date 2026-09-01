---
adr: 22
addendum: 1
title: "Remove The memory_critical Hard Cap — Soft Watermark Plus Polling Retry"
status: Proposed
date_created: 2026-08-26
date_accepted: null
date_superseded: null

supersedes: []
superseded_by: null
related: [22, 27]
closes_issues: [2187]
tracking_issue: 2187

is_code_implementation: true
governs:
  modules:
    - scistudio.engine.resources
    - scistudio.engine.scheduler
  contracts:
    - scistudio.engine.resources.ResourceManager
  entry_points: []
  files:
    - docs/adr/ADR-022-addendum1.md
    - src/scistudio/engine/resources.py
    - src/scistudio/engine/scheduler/__init__.py
    - src/scistudio/engine/scheduler/_dispatch.py
    - tests/engine/test_resources.py
    - tests/engine/test_scheduler.py
  excludes: []

tests:
  - tests/engine/test_resources.py
  - tests/engine/test_scheduler.py
agent_editable: true
assisted_by:
  - "kimi-cli"

phase: implementation
tags: [adr-022, runtime, resources, memory, scheduling]
owner: "@jiazhenz026"
co_authors: []
language_source: en
translations: []
---

# ADR-022 Addendum 1: Remove The memory_critical Hard Cap — Soft Watermark Plus Polling Retry

## 1. Decision Summary

`ResourceManager` no longer has a hard memory cap. The `memory_critical`
constructor parameter and the `can_dispatch()` hard refusal at 95% system
memory are removed. Memory gating is now a single soft high-watermark pause
(default raised from 0.90 to 0.95) that throttles new dispatch only while
other blocks are running; the `active_count == 0` bypass from #495 is kept.

When `can_dispatch` refuses a block, the scheduler schedules a deduplicated
1-second polling retry (`_schedule_resource_retry` /
`_on_resource_retry_timer` in `engine/scheduler/_dispatch.py`, bound onto
`DAGScheduler`) that re-runs `_dispatch_newly_ready` until dispatch succeeds,
the block leaves READY, or the scheduler is disposed (`dispose()` cancels the
pending timer).

### 1.1 Problems Addressed

| Problem | Risk | Addendum response | Detailed section |
|---|---|---|---|
| Hard refusal at `memory_critical` could stall a workflow forever: the only retry fired on terminal block events, and with `active_count == 0` none ever fire | Users watch a block sit in READY indefinitely with no log, event, or UI signal — even after memory pressure passes | Remove the hard cap; add a 1s polling retry for refused READY blocks | Section 2 |
| Modern OSes fill RAM with reclaimable cache/standby memory | The 95% hard wall triggers under routine conditions, not just real exhaustion | Treat memory gating as soft back-pressure only; OOM is surfaced by Layer 3 as a block ERROR | Section 3 |

## 2. Rationale

Issue #2187. Per the owner directive, OOM handling belongs to the existing
Layer 3 defense (ADR-022 §4): the OS kills the worker subprocess, the runner
observes the non-zero exit, and the block transitions to ERROR where the UI
surfaces it. A visible error is strictly better than a silent permanent
stall.

## 3. Consequences

- The `ResourceManager.__init__` signature loses `memory_critical`; the
  constructor sketch in ADR-027 ("Signature-Level Contracts") is superseded
  for that constructor: soft watermark default 0.95, no critical parameter.
- ADR-022 §8 verification guidance referring to "critical thresholds" and
  the §9 consequence about "below the critical threshold" are superseded by
  this addendum; the watermark itself and the three-layer defense model are
  unchanged.
- Back-pressure under sustained memory pressure now relies on the soft
  watermark plus the polling retry rather than a hard refusal.
