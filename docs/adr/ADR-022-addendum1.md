---
adr: 22
addendum: 1
title: "Host Safety Guard Replaces Predictive CPU And GPU Accounting"
status: Accepted
date_created: 2026-08-21
date_accepted: 2026-08-21
date_superseded: null

supersedes: []
superseded_by: null
related: [17, 18, 19, 20, 22, 27]
closes_issues: []
tracking_issue: 1595

is_code_implementation: true
governs:
  modules:
    - scistudio.api.runtime
    - scistudio.engine.resources
    - scistudio.engine.runners
    - scistudio.engine.scheduler
  contracts:
    - scistudio.engine.resources.AdmissionDecision
    - scistudio.engine.resources.AdmissionWaitReason
    - scistudio.engine.resources.ResourcePermit
    - scistudio.engine.resources.ResourceSnapshot
    - scistudio.engine.resources.ResourceManager
    - scistudio.engine.runners.process_handle.ProcessHandle
    - scistudio.engine.scheduler.DAGScheduler
  entry_points: []
  files:
    - docs/adr/ADR-022-addendum1.md
    - docs/architecture/ARCHITECTURE.md
    - docs/package-development/blocks.md
    - src/scistudio/api/runtime/**
    - src/scistudio/engine/resources.py
    - src/scistudio/engine/runners/**
    - src/scistudio/engine/scheduler/**
    - tests/engine/test_resources.py
    - tests/engine/test_scheduler_concurrency.py
  excludes: []

tests:
  - tests/engine/test_resources.py
  - tests/engine/test_scheduler_concurrency.py
agent_editable: false
assisted_by:
  - "Codex:gpt-5"

phase: implementation
tags: [runtime, resources, scheduling, concurrency, host-safety]
owner: "@jiazhenz026"
co_authors: ["@codex"]
language_source: en
translations: []
---

# ADR-022 Addendum 1: Host Safety Guard Replaces Predictive CPU And GPU Accounting

## 1. Decision Summary

SciStudio will not predict, allocate, or enforce per-block CPU cores, GPU slots,
GPU memory, or internal worker counts in the local runtime. A block owns its
algorithmic resource behavior, including device choice, batching, thread pools,
process pools, lazy loading, and application-specific memory strategy.

The engine retains only a host-safety admission boundary before starting a new
block subprocess:

- at most **255 block executions** may run concurrently by default across the
  entire SciStudio runtime, including all concurrently active workflow runs;
- the limit is configurable as a positive integer, with `1` providing an
  explicitly serial mode and values above `255` representing an explicit owner or
  operator throughput choice;
- live host-memory high and critical watermarks may delay new dispatches;
- subprocess isolation, cancellation, termination, and exit observation remain
  the hard failure-containment boundary;
- runtime diagnostics expose why a READY block is waiting without claiming that
  SciStudio reserved or guaranteed compute resources.

This addendum replaces ADR-022's predictive CPU/GPU accounting and ADR-027's
`max_internal_workers`, effective-CPU, and GPU auto-detection decisions wherever
they conflict. It preserves ADR-022's OS-memory-pressure decision and ADR-017's
subprocess-isolation boundary. The implementation is delivered with this
addendum: the scheduler acquires runtime-global permits and no longer carries a
per-block resource request.

### 1.1 Problems Addressed

| Problem | Risk | ADR response | Detailed section |
|---|---|---|---|
| Declarative CPU/GPU accounting is not wired into production dispatch | Documentation and types imply guarantees that the runtime does not provide | Remove predictive per-block accounting instead of completing the unused allocation ledger | Section 3 |
| A scientific block can internally fan out in ways the engine cannot predict | `cpu_cores`, `gpu_memory_gb`, and `max_internal_workers` become inaccurate honor-system values | Make the block responsible for resource consumption and keep local scheduling resource-agnostic | Section 4 |
| Unbounded automatic DAG fan-out can overload a workstation | Several independently READY blocks can launch at once even when each block already uses the host heavily | Apply a runtime-global configurable concurrency limit with a default of 255 | Section 5 |
| System memory pressure can grow when new subprocesses continue to launch | The OS may terminate workers or destabilize the desktop session | Preserve high/critical memory admission checks for new dispatch only | Section 6 |
| Local safety behavior can be mistaken for resource guarantees | Users may expect CPU fairness, GPU exclusivity, or OOM prevention that does not exist | Define explicit non-guarantees and route hard allocation to runner backends | Section 7 |

## 2. Context And Status

ADR-017 established one isolated subprocess as the normal execution boundary for
one block invocation. ADR-020 then moved collection iteration, batching, internal
parallelism, and memory behavior into blocks because a general scheduler cannot
understand domain-specific execution strategy.

ADR-022 retained OS-level memory pressure monitoring but also described
declaration-based CPU and GPU allocation. ADR-027 extended that model with
`max_internal_workers`, `effective_cpu`, and GPU-count auto-detection. The
resulting accounting was never connected to production dispatch: issue #1595
records that the scheduler passes an empty request and that `acquire()` has no
production caller. Core and package blocks do not have a dependable resource
declaration contract.

Completing that design would require every block and package to predict the
behavior of NumPy, MKL, OpenBLAS, PyTorch, external applications, and arbitrary
user code. It would still be advisory rather than enforced. This addendum makes
the local runtime boundary smaller and truthful instead of expanding an
inaccurate prediction system.

## 3. Remove Predictive Per-Block Accounting

The local scheduler will not require or inspect a per-block resource request.
The implementation will remove or retire the following as scheduling inputs:

- `requires_gpu`;
- `gpu_memory_gb`;
- `cpu_cores`;
- `max_internal_workers` and `effective_cpu`;
- GPU-count auto-detection for dispatch;
- GPU and CPU in-use counters;
- per-block resource allocation records whose only purpose is counter release.

`ResourceRequest` and `ProcessHandle.resource_request` are not retained as
reserved plugin extension points. If a remote or container runner needs a
resource profile later, that profile belongs to the runner/provisioner contract
and must not silently reactivate local scheduler accounting.

The implementation may replace or narrow `ResourceManager`, but its remaining
responsibility must be described as host-safety admission, not resource
allocation. There must be one authoritative concurrency-permit state shared by
all schedulers in a runtime.

## 4. Block And Runner Responsibility

A block controls how its invocation uses the execution environment. This
includes:

- selecting CPU, GPU, accelerator, or external application behavior;
- selecting thread, process, batch, and library-level parallelism;
- configuring library-specific environment or APIs;
- loading all inputs, streaming them, or using lazy/chunked access;
- handling device-specific cleanup inside its subprocess.

SciStudio does not promise that those choices are efficient or mutually safe
with other blocks. The stable framework guarantee is containment: normal block
logic runs outside the engine process and can be cancelled or terminated as a
process tree.

A future Kubernetes, Slurm, YARN, container, or remote runner may accept and
enforce backend-specific resource profiles. Such enforcement is a runner
capability analogous to a Jupyter spawner or kernel provisioner. It is not a
reason to put CPU/GPU prediction back into the local DAG scheduler.

## 5. Runtime-Global Concurrency Limit

The local runtime has one concurrency-permit pool shared across all active
workflow schedulers.

The normative default is:

```text
max_concurrent_blocks = 255
```

The value 255 leaves ample room for multimodal workflows and their independent
branches, while still placing a deterministic bound on automatic DAG fan-out.
It is a runaway process-launch guard, not a claim that the host can efficiently
sustain 255 CPU- or GPU-heavy blocks.
A default derived from logical CPU count is rejected because logical cores do
not predict scientific-library fan-out or GPU pressure.

Configuration requirements:

- the value must be a positive integer;
- `1` is supported as an explicitly serial safety mode;
- values greater than `255` are allowed only through explicit runtime/operator
  configuration; there is no automatic scale-up from detected hardware;
- the limit is runtime-global, not per workflow, so two simultaneous workflows
  cannot each consume the full allowance;
- changing the limit while executions are active is not required by this
  addendum.

A permit is acquired before a block transitions to RUNNING or launches worker
work. If no permit is available, the block remains READY. The permit is released
exactly once after DONE, ERROR, CANCELLED, worker launch failure, or abnormal
process exit. Release must be idempotent.

Strict workflow fairness and priority scheduling are out of scope. The runtime
must retry waiting READY blocks when a permit is released, but this addendum does
not define a fairness SLA.

## 6. Host Memory Safety

SciStudio preserves live system-memory checks as advisory admission control for
new work. It does not estimate, reserve, attribute, or release memory per block.

The required behavior is:

```text
memory >= critical                       -> do not start a new block
memory > high and active_blocks > 0      -> do not start a new block
memory <= high                           -> concurrency limit decides
high < memory < critical and no activity -> allow one block to avoid deadlock
```

The default thresholds remain `high = 0.90` and `critical = 0.95` unless a
separate decision changes them. Crossing a threshold does not automatically
terminate an already running block. If a worker exhausts memory, OS process
handling and the runner convert its exit into a block failure while preserving
the engine process where the operating system permits.

## 7. Guarantees, Non-Guarantees, And Diagnostics

The local runtime guarantees:

- a configurable bound on simultaneously active block executions;
- no new dispatch while the critical system-memory threshold is reached;
- subprocess lifecycle observation and best-effort process-tree termination;
- a machine-readable wait reason for concurrency-limit and memory-pressure
  admission decisions.

The local runtime does not guarantee:

- CPU-core reservation, affinity, fairness, or throttling;
- GPU discovery, device assignment, exclusivity, fairness, or VRAM capacity;
- prevention of block, worker, driver, or operating-system OOM;
- enforcement of block-internal thread or child-process counts;
- performance isolation between simultaneous workflows or blocks.

Diagnostics may report host memory, active permit count, configured permit
limit, and wait reason. They must not label these observations as available or
allocated CPU/GPU resources.

## 8. Scope And Migration

In scope for implementation:

- replace CPU/GPU request accounting with runtime-global concurrency permits;
- retain and narrow host-memory admission behavior;
- remove dead resource-request plumbing from scheduler, process, and block
  authoring contracts;
- preserve READY-and-retry scheduling behavior;
- update architecture and block-authoring documentation to state the new
  boundary;
- reclassify issue #1595 from missing resource-accounting wiring to removal of
  the unused accounting model and implementation of the host-safety guard.

Out of scope:

- hard CPU, RAM, or GPU enforcement in the local runner;
- resource-aware workflow optimization;
- GPU mutexes, device leases, MIG, or fractional GPU allocation;
- per-user quotas, priorities, preemption, and fairness guarantees;
- remote-runner resource profile schemas;
- automatic cancellation of running work under memory pressure.

`docs/architecture/ARCHITECTURE.md` is owner-controlled. Its Sections 6.1-6.4
are updated with this implementation to replace CPU/GPU resource-gating claims
with the runtime-global host-safety boundary.

## 9. Verification And Tooling Impact

Implementation tests must use the real host-safety/concurrency implementation,
not a mock that reproduces intended behavior. They must prove:

- 256 independently READY blocks never exceed 255 simultaneous executions under
  the default configuration;
- the limit of 255 is shared across two concurrently active workflow schedulers;
- explicit limits of one and greater than 255 are honored;
- a waiting block remains READY and is retried after permit release;
- permits are released exactly once after success, error, cancellation, launch
  failure, and abnormal process exit;
- the high-watermark idle escape and critical-watermark hard stop behave as
  specified in Section 6;
- a core or package block runs without resource-request metadata;
- diagnostics distinguish concurrency and memory wait reasons without claiming
  CPU/GPU allocation.

Documentation checks must verify ADR frontmatter and structure, architecture
closure, block-authoring guidance, and removal of stale claims that CPU/GPU
accounting is active.

## 10. Consequences

Positive consequences:

- the local runtime contract matches what it can actually observe and enforce;
- block and package authors do not maintain inaccurate resource declarations;
- the scheduler keeps a small, deterministic safety boundary;
- a default of 255 accommodates broad multimodal DAG parallelism without
  hardware guessing;
- future hard resource enforcement can live behind runner/provisioner contracts.

Accepted costs and risks:

- simultaneous CPU- or GPU-heavy blocks may contend;
- two GPU blocks may select the same device and exhaust VRAM;
- users seeking stronger isolation must choose a suitable runner/backend or use
  a lower global concurrency limit;
- removing existing request types and parameters may require compatibility
  migration for downstream code that imported scaffolding;
- the implementation touches protected engine paths and requires the repository
  authorization and gate evidence applicable to that work.

## 11. Alternatives Considered

| Alternative | Reason rejected |
|---|---|
| Complete ADR-022 CPU/GPU allocation wiring | Requires every block to predict opaque library behavior and still provides no local hard enforcement |
| Default concurrency from logical CPU count | Native libraries and GPU workloads make CPU count a poor safety predictor |
| Default concurrency of one | Safe but disables ADR-018 parallel branch behavior by default |
| Default concurrency of twenty or less | Too restrictive for broad multimodal workflows and their independent branches |
| No global concurrency limit | Unlike a normal single-kernel notebook, SciStudio automatically fans out READY DAG branches and could create an unbounded subprocess burst |
| Add GPU-specific locking only | Retains device-specific policy in core while leaving CPU and memory behavior equally uncertain |
