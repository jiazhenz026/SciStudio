---
title: "Alpha Release Audit Criteria"
status: Draft
owners:
  - "@jiazhenz026"
related_adrs:
  - 42
language_source: en
---

# Alpha Release Audit Criteria

## 1. External Standards Survey

This criterion file uses official project documentation as external reference points for moving from pre-alpha work to an alpha-quality release:

- Semantic Versioning treats pre-release versions as unstable and potentially not satisfying compatibility expectations for the associated normal version: https://semver.org/
- Python publishes alpha, beta, and release-candidate builds for advanced-user testing, not production use: https://devguide.python.org/developer-workflow/development-cycle/
- Django aligns alpha with feature freeze for a feature release; unfinished features are deferred, while beta shifts toward conservative bug fixing: https://docs.djangoproject.com/en/dev/internals/release-process/
- Kubernetes defines alpha features as disabled by default, possibly buggy, removable without notice, and recommended only for short-lived testing environments: https://kubernetes.io/docs/reference/command-line-tools-reference/feature-gates/
- Node.js marks experimental APIs as outside normal semantic-versioning guarantees and not recommended for production; its 1.0/1.1/1.2 experimental stages separate early development, active development, and release-candidate experimental status: https://nodejs.org/api/documentation.html
- Rust keeps unstable functionality gated to nightly or explicit feature flags until it has enough testing to be released broadly: https://doc.rust-lang.org/rustdoc/unstable-features.html
- OpenTelemetry requires stability procedures to isolate development-stage work so it does not break stable surfaces, and records versioning/stability policy in repository documentation: https://opentelemetry.io/docs/specs/otel/versioning-and-stability/

Synthesis for SciStudio: an alpha release may be unstable, non-production, and allowed to change incompatibly. It still needs a clearly bounded included surface, a working core path, visible feature/contract boundaries, release evidence, and known-risk classification.

## 2. SciStudio Alpha Scope

For this audit, alpha readiness means the core runtime is ready for a small internal test cohort.

In scope:

- Workflow graph creation, validation, execution, cancellation, failure, and state reporting.
- Block base contracts and representative built-in core blocks needed to demonstrate runtime execution.
- Artifact persistence, storage references, lineage, workflow state/versioning, and recovery behavior.
- Manual review and AI orchestration boundaries when they affect core runtime truth.
- API and desktop bridge behavior needed to launch, observe, and stop core workflows.
- Governance, gate records, CI, test posture, audit evidence, and release notes/known limitations.

Out of scope:

- Package catalog completeness.
- Extension catalog completeness.
- Individual package or extension quality, unless it prevents core startup, import, execution, or release evidence.
- Broad production hardening that is normally expected for beta, release candidate, or general availability.

## 3. Minimum Alpha Entry Bar

The core runtime should not enter alpha unless all of the following are true or explicitly risk-accepted by the owner:

- A fresh checkout of the latest remote code can run the core test/check path without unresolved environment hacks such as `pip install -e .`.
- At least one representative workflow can execute end to end and persist inspectable artifacts/lineage.
- Runtime truth lives in backend/runtime state, not only frontend state.
- Core schemas/contracts reject invalid input or document allowed instability.
- Manual review and AI orchestration cannot silently bypass governance, user intent, or runtime state.
- CI/gate evidence is available and understandable for the release branch.
- Known limitations are documented with severity and follow-up ownership.

## 4. Severity Rubric

### P0: Alpha Release Block

Use P0 when alpha should not proceed.

Examples:

- Core runtime cannot start, import, or execute a representative workflow.
- Artifact, lineage, or workflow state can be silently lost or corrupted on a normal core path.
- Security issue can expose secrets, execute unintended commands, or write outside intended project boundaries in a default alpha scenario.
- CI/gate evidence is absent or fundamentally untrustworthy for the release candidate.
- Docs/specs claim a core guarantee that is materially false and would cause an alpha tester to lose work or trust the wrong runtime truth.

### P1: Pass Only With Must Fix

Use P1 when alpha can pass only after remediation or explicit owner risk acceptance.

Examples:

- A core path works only for narrow happy-path cases and lacks failure-state handling.
- Representative tests for a core contract are missing or stale.
- A documented runtime contract has implementation drift that can mislead internal testers.
- Manual review or AI orchestration behavior is ambiguous enough to create unsafe user expectations.
- CI has failing or skipped checks in core paths, but a bounded fix is plausible before alpha.

### P2: Pass, Good To Fix

Use P2 when alpha can proceed, but the issue should be fixed before broader testing.

Examples:

- Edge-case tests are thin but core path evidence exists.
- Diagnostics are incomplete but failures remain visible and recoverable.
- Documentation is incomplete but not actively misleading for alpha scope.
- Performance or scalability limits are known and acceptable for short-lived internal tests.

### P3: Good To Fix

Use P3 for polish, maintainability, or clarity improvements.

Examples:

- Better messages, naming, report formatting, or developer ergonomics.
- Additional examples that improve onboarding but do not affect alpha safety.
- Non-core package/extension improvements that are explicitly outside alpha scope.

## 5. Final Report Rules

The final manager report must:

- Name the baseline commit and branch.
- List every agent report path.
- Deduplicate and prioritize findings into P0, P1, P2, and P3.
- State an alpha release verdict: block, pass-with-must-fix, pass, or pass-with-good-to-fix.
- Separate core runtime blockers from package/extension non-goals.
- Name checks that passed, failed, or were not run.
- Convert deferred fixes into tracked issue references or mark them as needing issue creation before implementation.
