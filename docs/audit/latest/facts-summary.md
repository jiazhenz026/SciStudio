# ADR-042 Facts Audit Summary

## 1. Change Summary

This generated report summarizes the current machine-readable facts registry.
It is intended for human review; drift checks consume the YAML facts directly.

## 2. Overall Status

- Status: `fail`
- Blocks merge: `True`
- Source hash: `960470d6e25392db06bdc28a5239845dd21eda3af11cc1273a5ea59e577601f0`
- Facts file: `docs/facts/generated.yaml`
- Total facts: `1720`
- Symbol facts: `1689`

## 3. Fact Inventory

| Fact kind | Count |
|---|---:|
| `expected-signature` | 31 |
| `symbol` | 1689 |

## 4. Symbol Inventory

| Symbol kind | Count |
|---|---:|
| `attribute` | 821 |
| `class` | 190 |
| `function` | 506 |
| `module` | 172 |

## 5. Largest Symbol Areas

| Package | Count |
|---|---:|
| `scieasy.blocks` | 421 |
| `scieasy.api` | 391 |
| `scieasy.core` | 335 |
| `scieasy.qa` | 214 |
| `scieasy.engine` | 198 |
| `scieasy.workflow` | 58 |
| `scieasy.cli` | 27 |
| `scieasy.utils` | 26 |
| `scieasy.agent_provisioning` | 9 |
| `scieasy.testing` | 9 |
| `scieasy.ai` | 1 |

## 6. Findings

Total error-severity findings: `1513`

- `doc-drift.invalid-frontmatter` at `docs/adr/ADR-031.md:1`: missing YAML frontmatter
- `doc-drift.invalid-frontmatter` at `docs/adr/ADR-032.md:1`: missing YAML frontmatter
- `doc-drift.invalid-frontmatter` at `docs/adr/ADR-033.md:1`: missing YAML frontmatter
- `doc-drift.invalid-frontmatter` at `docs/adr/ADR-034.md:1`: missing YAML frontmatter
- `doc-drift.invalid-frontmatter` at `docs/adr/ADR-035.md:1`: missing YAML frontmatter
- `doc-drift.invalid-frontmatter` at `docs/adr/ADR-036.md:1`: missing YAML frontmatter
- `doc-drift.invalid-frontmatter` at `docs/adr/ADR-037.md:1`: missing YAML frontmatter
- `doc-drift.invalid-frontmatter` at `docs/adr/ADR-038.md:1`: missing YAML frontmatter
- `doc-drift.invalid-frontmatter` at `docs/adr/ADR-039.md:1`: missing YAML frontmatter
- `doc-drift.invalid-frontmatter` at `docs/adr/ADR-040.md:1`: missing YAML frontmatter
- `doc-drift.invalid-frontmatter` at `docs/adr/ADR-041.md:1`: missing YAML frontmatter
- `doc-drift.invalid-frontmatter` at `docs/specs/appblock-variadic-ports.md:1`: missing YAML frontmatter
- `doc-drift.invalid-frontmatter` at `docs/specs/data-preview-3d-viewer.md:1`: missing YAML frontmatter
- `doc-drift.invalid-frontmatter` at `docs/specs/embedded-coding-agent-spec.md:1`: Spec frontmatter validation failed: 15 validation errors for SpecFrontmatter
spec_id
  Field required [type=missing, input_value={'title': 'Embedded codin...etime.date(2026, 5, 12)}, input_type=dict]
    For further information visit https://errors.pydantic.dev/2.12/v/missing
status
  Input should be 'Draft', 'Clarifying', 'Planned', 'Implemented' or 'Deprecated' [type=literal_error, input_value='superseded-by-adr-034', input_type=str]
    For further information visit https://errors.pydantic.dev/2.12/v/literal_error
feature_branch
  Field required [type=missing, input_value={'title': 'Embedded codin...etime.date(2026, 5, 12)}, input_type=dict]
    For further information visit https://errors.pydantic.dev/2.12/v/missing
created
  Field required [type=missing, input_value={'title': 'Embedded codin...etime.date(2026, 5, 12)}, input_type=dict]
    For further information visit https://errors.pydantic.dev/2.12/v/missing
input
  Field required [type=missing, input_value={'title': 'Embedded codin...etime.date(2026, 5, 12)}, input_type=dict]
    For further information visit https://errors.pydantic.dev/2.12/v/missing
owners
  Field required [type=missing, input_value={'title': 'Embedded codin...etime.date(2026, 5, 12)}, input_type=dict]
    For further information visit https://errors.pydantic.dev/2.12/v/missing
related_adrs
  Field required [type=missing, input_value={'title': 'Embedded codin...etime.date(2026, 5, 12)}, input_type=dict]
    For further information visit https://errors.pydantic.dev/2.12/v/missing
related_specs
  Field required [type=missing, input_value={'title': 'Embedded codin...etime.date(2026, 5, 12)}, input_type=dict]
    For further information visit https://errors.pydantic.dev/2.12/v/missing
scope
  Field required [type=missing, input_value={'title': 'Embedded codin...etime.date(2026, 5, 12)}, input_type=dict]
    For further information visit https://errors.pydantic.dev/2.12/v/missing
governs
  Field required [type=missing, input_value={'title': 'Embedded codin...etime.date(2026, 5, 12)}, input_type=dict]
    For further information visit https://errors.pydantic.dev/2.12/v/missing
tests
  Field required [type=missing, input_value={'title': 'Embedded codin...etime.date(2026, 5, 12)}, input_type=dict]
    For further information visit https://errors.pydantic.dev/2.12/v/missing
acceptance_source
  Field required [type=missing, input_value={'title': 'Embedded codin...etime.date(2026, 5, 12)}, input_type=dict]
    For further information visit https://errors.pydantic.dev/2.12/v/missing
issue
  Extra inputs are not permitted [type=extra_forbidden, input_value=697, input_type=int]
    For further information visit https://errors.pydantic.dev/2.12/v/extra_forbidden
adr
  Extra inputs are not permitted [type=extra_forbidden, input_value=27, input_type=int]
    For further information visit https://errors.pydantic.dev/2.12/v/extra_forbidden
date
  Extra inputs are not permitted [type=extra_forbidden, input_value=datetime.date(2026, 5, 12), input_type=date]
    For further information visit https://errors.pydantic.dev/2.12/v/extra_forbidden
- `doc-drift.invalid-frontmatter` at `docs/specs/phase10-implementation-standards.md:1`: missing YAML frontmatter
- `doc-drift.invalid-frontmatter` at `docs/specs/phase11-imaging-block-spec.md:1`: missing YAML frontmatter
- `doc-drift.invalid-frontmatter` at `docs/specs/phase11-implementation-standards.md:1`: Spec frontmatter validation failed: 14 validation errors for SpecFrontmatter
spec_id
  Field required [type=missing, input_value={'title': 'Phase 11 imple...tetime.date(2026, 4, 7)}, input_type=dict]
    For further information visit https://errors.pydantic.dev/2.12/v/missing
status
  Input should be 'Draft', 'Clarifying', 'Planned', 'Implemented' or 'Deprecated' [type=literal_error, input_value='in progress', input_type=str]
    For further information visit https://errors.pydantic.dev/2.12/v/literal_error
feature_branch
  Field required [type=missing, input_value={'title': 'Phase 11 imple...tetime.date(2026, 4, 7)}, input_type=dict]
    For further information visit https://errors.pydantic.dev/2.12/v/missing
created
  Field required [type=missing, input_value={'title': 'Phase 11 imple...tetime.date(2026, 4, 7)}, input_type=dict]
    For further information visit https://errors.pydantic.dev/2.12/v/missing
input
  Field required [type=missing, input_value={'title': 'Phase 11 imple...tetime.date(2026, 4, 7)}, input_type=dict]
    For further information visit https://errors.pydantic.dev/2.12/v/missing
owners
  Field required [type=missing, input_value={'title': 'Phase 11 imple...tetime.date(2026, 4, 7)}, input_type=dict]
    For further information visit https://errors.pydantic.dev/2.12/v/missing
related_adrs
  Field required [type=missing, input_value={'title': 'Phase 11 imple...tetime.date(2026, 4, 7)}, input_type=dict]
    For further information visit https://errors.pydantic.dev/2.12/v/missing
related_specs
  Field required [type=missing, input_value={'title': 'Phase 11 imple...tetime.date(2026, 4, 7)}, input_type=dict]
    For further information visit https://errors.pydantic.dev/2.12/v/missing
scope
  Field required [type=missing, input_value={'title': 'Phase 11 imple...tetime.date(2026, 4, 7)}, input_type=dict]
    For further information visit https://errors.pydantic.dev/2.12/v/missing
governs
  Field required [type=missing, input_value={'title': 'Phase 11 imple...tetime.date(2026, 4, 7)}, input_type=dict]
    For further information visit https://errors.pydantic.dev/2.12/v/missing
tests
  Field required [type=missing, input_value={'title': 'Phase 11 imple...tetime.date(2026, 4, 7)}, input_type=dict]
    For further information visit https://errors.pydantic.dev/2.12/v/missing
acceptance_source
  Field required [type=missing, input_value={'title': 'Phase 11 imple...tetime.date(2026, 4, 7)}, input_type=dict]
    For further information visit https://errors.pydantic.dev/2.12/v/missing
issue
  Extra inputs are not permitted [type=extra_forbidden, input_value='306 (closes', input_type=str]
    For further information visit https://errors.pydantic.dev/2.12/v/extra_forbidden
date
  Extra inputs are not permitted [type=extra_forbidden, input_value=datetime.date(2026, 4, 7), input_type=date]
    For further information visit https://errors.pydantic.dev/2.12/v/extra_forbidden
- `doc-drift.invalid-frontmatter` at `docs/specs/phase11-lcms-block-spec.md:1`: missing YAML frontmatter
- `doc-drift.invalid-frontmatter` at `docs/specs/phase11-srs-block-spec.md:1`: missing YAML frontmatter
- `closure.invalid-frontmatter` at `docs/adr/ADR-031.md:1`: missing YAML frontmatter
- `closure.invalid-frontmatter` at `docs/adr/ADR-032.md:1`: missing YAML frontmatter
- `closure.invalid-frontmatter` at `docs/adr/ADR-033.md:1`: missing YAML frontmatter
- `closure.invalid-frontmatter` at `docs/adr/ADR-034.md:1`: missing YAML frontmatter
- `closure.invalid-frontmatter` at `docs/adr/ADR-035.md:1`: missing YAML frontmatter
- `closure.invalid-frontmatter` at `docs/adr/ADR-036.md:1`: missing YAML frontmatter
- `closure.invalid-frontmatter` at `docs/adr/ADR-037.md:1`: missing YAML frontmatter
- `closure.invalid-frontmatter` at `docs/adr/ADR-038.md:1`: missing YAML frontmatter
- `closure.invalid-frontmatter` at `docs/adr/ADR-039.md:1`: missing YAML frontmatter
- `closure.invalid-frontmatter` at `docs/adr/ADR-040.md:1`: missing YAML frontmatter
- `closure.invalid-frontmatter` at `docs/adr/ADR-041.md:1`: missing YAML frontmatter
- `closure.invalid-frontmatter` at `docs/specs/appblock-variadic-ports.md:1`: missing YAML frontmatter
- `closure.invalid-frontmatter` at `docs/specs/data-preview-3d-viewer.md:1`: missing YAML frontmatter
- `closure.invalid-frontmatter` at `docs/specs/embedded-coding-agent-spec.md:1`: Spec frontmatter validation failed: 15 validation errors for SpecFrontmatter
spec_id
  Field required [type=missing, input_value={'title': 'Embedded codin...etime.date(2026, 5, 12)}, input_type=dict]
    For further information visit https://errors.pydantic.dev/2.12/v/missing
status
  Input should be 'Draft', 'Clarifying', 'Planned', 'Implemented' or 'Deprecated' [type=literal_error, input_value='superseded-by-adr-034', input_type=str]
    For further information visit https://errors.pydantic.dev/2.12/v/literal_error
feature_branch
  Field required [type=missing, input_value={'title': 'Embedded codin...etime.date(2026, 5, 12)}, input_type=dict]
    For further information visit https://errors.pydantic.dev/2.12/v/missing
created
  Field required [type=missing, input_value={'title': 'Embedded codin...etime.date(2026, 5, 12)}, input_type=dict]
    For further information visit https://errors.pydantic.dev/2.12/v/missing
input
  Field required [type=missing, input_value={'title': 'Embedded codin...etime.date(2026, 5, 12)}, input_type=dict]
    For further information visit https://errors.pydantic.dev/2.12/v/missing
owners
  Field required [type=missing, input_value={'title': 'Embedded codin...etime.date(2026, 5, 12)}, input_type=dict]
    For further information visit https://errors.pydantic.dev/2.12/v/missing
related_adrs
  Field required [type=missing, input_value={'title': 'Embedded codin...etime.date(2026, 5, 12)}, input_type=dict]
    For further information visit https://errors.pydantic.dev/2.12/v/missing
related_specs
  Field required [type=missing, input_value={'title': 'Embedded codin...etime.date(2026, 5, 12)}, input_type=dict]
    For further information visit https://errors.pydantic.dev/2.12/v/missing
scope
  Field required [type=missing, input_value={'title': 'Embedded codin...etime.date(2026, 5, 12)}, input_type=dict]
    For further information visit https://errors.pydantic.dev/2.12/v/missing
governs
  Field required [type=missing, input_value={'title': 'Embedded codin...etime.date(2026, 5, 12)}, input_type=dict]
    For further information visit https://errors.pydantic.dev/2.12/v/missing
tests
  Field required [type=missing, input_value={'title': 'Embedded codin...etime.date(2026, 5, 12)}, input_type=dict]
    For further information visit https://errors.pydantic.dev/2.12/v/missing
acceptance_source
  Field required [type=missing, input_value={'title': 'Embedded codin...etime.date(2026, 5, 12)}, input_type=dict]
    For further information visit https://errors.pydantic.dev/2.12/v/missing
issue
  Extra inputs are not permitted [type=extra_forbidden, input_value=697, input_type=int]
    For further information visit https://errors.pydantic.dev/2.12/v/extra_forbidden
adr
  Extra inputs are not permitted [type=extra_forbidden, input_value=27, input_type=int]
    For further information visit https://errors.pydantic.dev/2.12/v/extra_forbidden
date
  Extra inputs are not permitted [type=extra_forbidden, input_value=datetime.date(2026, 5, 12), input_type=date]
    For further information visit https://errors.pydantic.dev/2.12/v/extra_forbidden
- `closure.invalid-frontmatter` at `docs/specs/phase10-implementation-standards.md:1`: missing YAML frontmatter
- `closure.invalid-frontmatter` at `docs/specs/phase11-imaging-block-spec.md:1`: missing YAML frontmatter
- `closure.invalid-frontmatter` at `docs/specs/phase11-implementation-standards.md:1`: Spec frontmatter validation failed: 14 validation errors for SpecFrontmatter
spec_id
  Field required [type=missing, input_value={'title': 'Phase 11 imple...tetime.date(2026, 4, 7)}, input_type=dict]
    For further information visit https://errors.pydantic.dev/2.12/v/missing
status
  Input should be 'Draft', 'Clarifying', 'Planned', 'Implemented' or 'Deprecated' [type=literal_error, input_value='in progress', input_type=str]
    For further information visit https://errors.pydantic.dev/2.12/v/literal_error
feature_branch
  Field required [type=missing, input_value={'title': 'Phase 11 imple...tetime.date(2026, 4, 7)}, input_type=dict]
    For further information visit https://errors.pydantic.dev/2.12/v/missing
created
  Field required [type=missing, input_value={'title': 'Phase 11 imple...tetime.date(2026, 4, 7)}, input_type=dict]
    For further information visit https://errors.pydantic.dev/2.12/v/missing
input
  Field required [type=missing, input_value={'title': 'Phase 11 imple...tetime.date(2026, 4, 7)}, input_type=dict]
    For further information visit https://errors.pydantic.dev/2.12/v/missing
owners
  Field required [type=missing, input_value={'title': 'Phase 11 imple...tetime.date(2026, 4, 7)}, input_type=dict]
    For further information visit https://errors.pydantic.dev/2.12/v/missing
related_adrs
  Field required [type=missing, input_value={'title': 'Phase 11 imple...tetime.date(2026, 4, 7)}, input_type=dict]
    For further information visit https://errors.pydantic.dev/2.12/v/missing
related_specs
  Field required [type=missing, input_value={'title': 'Phase 11 imple...tetime.date(2026, 4, 7)}, input_type=dict]
    For further information visit https://errors.pydantic.dev/2.12/v/missing
scope
  Field required [type=missing, input_value={'title': 'Phase 11 imple...tetime.date(2026, 4, 7)}, input_type=dict]
    For further information visit https://errors.pydantic.dev/2.12/v/missing
governs
  Field required [type=missing, input_value={'title': 'Phase 11 imple...tetime.date(2026, 4, 7)}, input_type=dict]
    For further information visit https://errors.pydantic.dev/2.12/v/missing
tests
  Field required [type=missing, input_value={'title': 'Phase 11 imple...tetime.date(2026, 4, 7)}, input_type=dict]
    For further information visit https://errors.pydantic.dev/2.12/v/missing
acceptance_source
  Field required [type=missing, input_value={'title': 'Phase 11 imple...tetime.date(2026, 4, 7)}, input_type=dict]
    For further information visit https://errors.pydantic.dev/2.12/v/missing
issue
  Extra inputs are not permitted [type=extra_forbidden, input_value='306 (closes', input_type=str]
    For further information visit https://errors.pydantic.dev/2.12/v/extra_forbidden
date
  Extra inputs are not permitted [type=extra_forbidden, input_value=datetime.date(2026, 4, 7), input_type=date]
    For further information visit https://errors.pydantic.dev/2.12/v/extra_forbidden
- `closure.invalid-frontmatter` at `docs/specs/phase11-lcms-block-spec.md:1`: missing YAML frontmatter
- `closure.invalid-frontmatter` at `docs/specs/phase11-srs-block-spec.md:1`: missing YAML frontmatter
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.agent_provisioning
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.agent_provisioning.claude_agents_md
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.agent_provisioning.claude_agents_md.write_claude_agents_md
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.agent_provisioning.codex_config
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.agent_provisioning.codex_config.write_codex_config
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.agent_provisioning.hooks
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.agent_provisioning.hooks.write_hooks
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.agent_provisioning.skills
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.agent_provisioning.skills.write_skills
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.ai
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.app
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.app.create_app
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.app.lifespan
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.deps
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.deps.get_block_registry
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.deps.get_engine
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.deps.get_lineage_store
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.deps.get_process_registry
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.deps.get_runtime
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.deps.get_type_registry
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.ai
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.ai.logger
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.ai.provider_status
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.ai.router
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.ai_pty
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.ai_pty.MAX_ACTIVE_PTYS
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.ai_pty.broadcast_ai_pty_message
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.ai_pty.get_block_run_id_for_tab
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.ai_pty.get_run_dir_for_block_run
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.ai_pty.logger
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.ai_pty.open_engine_initiated_tab
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.ai_pty.pty_endpoint
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.ai_pty.register_ai_pty_subscriber
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.ai_pty.router
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.ai_pty.unregister_ai_pty_subscriber
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.blocks
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.blocks.BlockRegistryDep
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.blocks.BlockTemplateResponse
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.blocks.BlockTemplateResponse.content
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.blocks.BlockTemplateResponse.kind
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.blocks.BlockTemplateResponse.suggested_filename
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.blocks.TypeRegistryDep
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.blocks.get_block_schema
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.blocks.get_block_template
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.blocks.list_blocks
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.blocks.logger
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.blocks.router
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.blocks.validate_connection_route
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.data
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.data.MAX_UPLOAD_SIZE
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.data.RuntimeDep
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.data.UploadFileParam
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.data.get_data_metadata
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.data.preview_data
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.data.router
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.data.upload_data
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.filesystem
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.filesystem.FilesystemBrowseResponse
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.filesystem.FilesystemBrowseResponse.entries
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.filesystem.FilesystemBrowseResponse.path
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.filesystem.FilesystemEntry
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.filesystem.FilesystemEntry.name
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.filesystem.FilesystemEntry.size
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.filesystem.FilesystemEntry.type
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.filesystem.NativeDialogRequest
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.filesystem.NativeDialogRequest.default_filename
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.filesystem.NativeDialogRequest.file_filter
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.filesystem.NativeDialogRequest.initial_dir
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.filesystem.NativeDialogRequest.mode
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.filesystem.NativeDialogResponse
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.filesystem.NativeDialogResponse.paths
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.filesystem.RevealRequest
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.filesystem.RevealRequest.path
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.filesystem.RuntimeDep
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.filesystem.TreeEntry
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.filesystem.TreeEntry.name
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.filesystem.TreeEntry.size
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.filesystem.TreeEntry.type
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.filesystem.TreeResponse
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.filesystem.TreeResponse.entries
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.filesystem.browse_filesystem
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.filesystem.native_file_dialog
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.filesystem.project_tree
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.filesystem.reveal_in_explorer
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.filesystem.router
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.git
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.git.BranchCreateRequest
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.git.BranchCreateRequest.base_sha
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.git.BranchCreateRequest.name
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.git.BranchSwitchRequest
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.git.BranchSwitchRequest.branch_name
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.git.CherryPickRequest
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.git.CherryPickRequest.commit_sha
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.git.CommitRequest
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.git.CommitRequest.author
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.git.CommitRequest.files
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.git.CommitRequest.message
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.git.CommitResponse
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.git.CommitResponse.commit_sha
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.git.MergeRequest
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.git.MergeRequest.source_branch
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.git.MergeStageFileRequest
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.git.MergeStageFileRequest.file
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.git.RestoreRequest
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.git.RestoreRequest.commit_sha
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.git.RestoreRequest.files
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.git.StashApplyRequest
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.git.StashApplyRequest.stash_id
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.git.StashSaveRequest
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.git.StashSaveRequest.message
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.git.branch_create
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.git.branch_delete
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.git.branch_switch
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.git.branches
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.git.cherry_pick
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.git.commit
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.git.diff
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.git.log
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.git.logger
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.git.merge
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.git.merge_abort
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.git.merge_complete
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.git.merge_stage_file
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.git.restore
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.git.router
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.git.stash_apply
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.git.stash_drop
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.git.stash_list
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.git.stash_save
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.git.status_endpoint
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.lint
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.lint.LintDiagnostic
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.lint.LintDiagnostic.code
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.lint.LintDiagnostic.column
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.lint.LintDiagnostic.end_column
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.lint.LintDiagnostic.end_line
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.lint.LintDiagnostic.line
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.lint.LintDiagnostic.message
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.lint.LintDiagnostic.severity
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.lint.LintRequest
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.lint.LintRequest.content
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.lint.LintRequest.filename
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.lint.LintResponse
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.lint.LintResponse.diagnostics
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.lint.LintResponse.note
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.lint.lint_python
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.lint.lint_python_source
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.lint.logger
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.lint.router
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.projects
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.projects.ADR036_FILE_ALLOWLIST
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.projects.ADR036_FILE_SIZE_CAP_BYTES
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.projects.BLOCKS_RELOADED_EVENT_TYPE
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.projects.FileReadResponse
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.projects.FileReadResponse.content
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.projects.FileReadResponse.encoding
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.projects.FileReadResponse.mtime
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.projects.FileReadResponse.size
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.projects.FileWriteRequest
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.projects.FileWriteRequest.content
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.projects.FileWriteResponse
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.projects.FileWriteResponse.mtime
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.projects.FileWriteResponse.size
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.projects.RuntimeDep
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.projects.create_project
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.projects.delete_project
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.projects.get_project
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.projects.list_projects
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.projects.logger
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.projects.read_project_file
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.projects.router
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.projects.update_project
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.projects.write_project_file
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.runs
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.runs.RerunRequest
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.runs.RerunRequest.execute_from_block_id
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.runs.get_run
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.runs.get_run_methods
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.runs.list_runs
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.runs.logger
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.runs.rerun_run
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.runs.router
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.runs.runs_health
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.workflow_watcher
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.workflow_watcher.WorkflowWatcher
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.workflow_watcher.WorkflowWatcher.git_handler
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.workflow_watcher.WorkflowWatcher.handler
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.workflow_watcher.WorkflowWatcher.mark_self_write
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.workflow_watcher.WorkflowWatcher.start_for_project
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.workflow_watcher.WorkflowWatcher.stop
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.workflow_watcher.WorkflowWatcher.watched_dir
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.workflow_watcher.WorkflowWatcher.watched_git_dir
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.workflow_watcher.get_active_watcher
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.workflow_watcher.logger
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.workflow_watcher.mark_self_write
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.workflow_watcher.set_active_watcher
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.workflows
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.workflows.RuntimeDep
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.workflows.cancel_block
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.workflows.cancel_workflow
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.workflows.create_workflow
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.workflows.delete_workflow
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.workflows.execute_from_workflow
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.workflows.execute_workflow
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.workflows.export_workflow_to_path
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.workflows.get_workflow
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.workflows.import_workflow
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.workflows.import_workflow_from_path
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.workflows.list_workflows
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.workflows.logger
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.workflows.pause_workflow
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.workflows.resume_workflow
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.workflows.router
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.routes.workflows.update_workflow
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.runtime
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.runtime.ApiRuntime
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.runtime.ApiRuntime.active_project
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.runtime.ApiRuntime.block_registry
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.runtime.ApiRuntime.checkpoint_dir_for
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.runtime.ApiRuntime.create_project
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.runtime.ApiRuntime.data_catalog
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.runtime.ApiRuntime.delete_project
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.runtime.ApiRuntime.delete_workflow
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.runtime.ApiRuntime.describe_ref
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.runtime.ApiRuntime.event_bus
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.runtime.ApiRuntime.get_data_record
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.runtime.ApiRuntime.get_run
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.runtime.ApiRuntime.known_projects
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.runtime.ApiRuntime.known_projects_path
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.runtime.ApiRuntime.lineage_store
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.runtime.ApiRuntime.list_project_workflows
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.runtime.ApiRuntime.list_projects
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.runtime.ApiRuntime.load_workflow
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.runtime.ApiRuntime.log_broadcaster
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.runtime.ApiRuntime.open_project
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.runtime.ApiRuntime.preview_data
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.runtime.ApiRuntime.process_registry
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.runtime.ApiRuntime.project_response
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.runtime.ApiRuntime.refresh_block_registry
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.runtime.ApiRuntime.register_data_ref
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.runtime.ApiRuntime.register_output_payload
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.runtime.ApiRuntime.registry_dir
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.runtime.ApiRuntime.require_active_project
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.runtime.ApiRuntime.resource_manager
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.runtime.ApiRuntime.runner
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.runtime.ApiRuntime.save_workflow
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.runtime.ApiRuntime.set_mcp_port
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.runtime.ApiRuntime.start_workflow
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.runtime.ApiRuntime.type_registry
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.runtime.ApiRuntime.update_project
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.runtime.ApiRuntime.upload_file
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.runtime.ApiRuntime.workflow_path
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.runtime.ApiRuntime.workflow_runs
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.runtime.DataRecord
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.runtime.DataRecord.id
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.runtime.DataRecord.metadata
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.runtime.DataRecord.ref
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.runtime.DataRecord.type_chain
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.runtime.DataRecord.type_name
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.runtime.KnownProject
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.runtime.KnownProject.description
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.runtime.KnownProject.id
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.runtime.KnownProject.last_opened
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.runtime.KnownProject.name
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.runtime.KnownProject.path
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.runtime.LogBroadcaster
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.runtime.LogBroadcaster.publish
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.runtime.LogBroadcaster.subscribe
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.runtime.LogBroadcaster.unsubscribe
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.runtime.MAX_TABLE_PAGE_SIZE
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.runtime.WorkflowRun
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.runtime.WorkflowRun.checkpoint_manager
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.runtime.WorkflowRun.scheduler
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.runtime.WorkflowRun.task
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.runtime.WorkflowRun.workflow_git_commit
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.runtime.logger
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.schemas
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.schemas.BlockConnectionValidation
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.schemas.BlockConnectionValidation.source_block
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.schemas.BlockConnectionValidation.source_port
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.schemas.BlockConnectionValidation.target_block
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.schemas.BlockConnectionValidation.target_port
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.schemas.BlockListResponse
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.schemas.BlockListResponse.blocks
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.schemas.BlockPortResponse
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.schemas.BlockPortResponse.accepted_types
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.schemas.BlockPortResponse.constraint_description
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.schemas.BlockPortResponse.description
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.schemas.BlockPortResponse.direction
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.schemas.BlockPortResponse.is_collection
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.schemas.BlockPortResponse.name
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.schemas.BlockPortResponse.required
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.schemas.BlockSchemaResponse
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.schemas.BlockSchemaResponse.allowed_input_types
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.schemas.BlockSchemaResponse.allowed_output_types
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.schemas.BlockSchemaResponse.config_schema
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.schemas.BlockSchemaResponse.direction
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.schemas.BlockSchemaResponse.dynamic_ports
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.schemas.BlockSchemaResponse.max_input_ports
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.schemas.BlockSchemaResponse.max_output_ports
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.schemas.BlockSchemaResponse.min_input_ports
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.schemas.BlockSchemaResponse.min_output_ports
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.schemas.BlockSchemaResponse.type_hierarchy
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.schemas.BlockSummary
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.schemas.BlockSummary.base_category
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.schemas.BlockSummary.description
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.schemas.BlockSummary.direction
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.schemas.BlockSummary.input_ports
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.schemas.BlockSummary.name
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.schemas.BlockSummary.output_ports
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.schemas.BlockSummary.package_name
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.schemas.BlockSummary.source
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.schemas.BlockSummary.subcategory
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.schemas.BlockSummary.type_name
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.schemas.BlockSummary.variadic_inputs
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.schemas.BlockSummary.variadic_outputs
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.schemas.BlockSummary.version
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.schemas.CancelBlockRequest
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.schemas.CancelBlockRequest.block_id
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.schemas.CancelPropagationResponse
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.schemas.CancelPropagationResponse.cancelled_blocks
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.schemas.CancelPropagationResponse.skip_reasons
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.schemas.CancelPropagationResponse.skipped_blocks
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.schemas.CancelWorkflowRequest
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.schemas.ConnectionValidationResponse
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.schemas.ConnectionValidationResponse.compatible
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.schemas.ConnectionValidationResponse.reason
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.schemas.DataMetadataResponse
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.schemas.DataMetadataResponse.metadata
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.schemas.DataMetadataResponse.ref
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.schemas.DataMetadataResponse.type_name
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.schemas.DataPreviewResponse
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.schemas.DataPreviewResponse.preview
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.schemas.DataPreviewResponse.ref
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.schemas.DataPreviewResponse.type_name
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.schemas.DataUploadResponse
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.schemas.DataUploadResponse.metadata
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.schemas.DataUploadResponse.ref
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.schemas.DataUploadResponse.type_name
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.schemas.ErrorResponse
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.schemas.ErrorResponse.detail
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.schemas.ErrorResponse.error_code
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.schemas.ExecuteFromRequest
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.schemas.ExecuteFromRequest.block_id
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.schemas.ExecuteFromResponse
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.schemas.ExecuteFromResponse.reset_blocks
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.schemas.ExecuteFromResponse.reused_blocks
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.schemas.ProjectCreate
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.schemas.ProjectCreate.description
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.schemas.ProjectCreate.name
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.schemas.ProjectCreate.path
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.schemas.ProjectResponse
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.schemas.ProjectResponse.current_workflow_id
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.schemas.ProjectResponse.description
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.schemas.ProjectResponse.id
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.schemas.ProjectResponse.last_opened
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.schemas.ProjectResponse.name
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.schemas.ProjectResponse.path
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.schemas.ProjectResponse.workflow_count
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.schemas.ProjectResponse.workflows
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.schemas.ProjectUpdate
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.schemas.ProjectUpdate.description
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.schemas.ProjectUpdate.name
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.schemas.TypeHierarchyEntry
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.schemas.TypeHierarchyEntry.base_type
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.schemas.TypeHierarchyEntry.description
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.schemas.TypeHierarchyEntry.name
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.schemas.TypeHierarchyEntry.ui_ring_color
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.schemas.WorkflowCreate
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.schemas.WorkflowCreate.description
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.schemas.WorkflowCreate.edges
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.schemas.WorkflowCreate.id
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.schemas.WorkflowCreate.metadata
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.schemas.WorkflowCreate.nodes
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.schemas.WorkflowCreate.version
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.schemas.WorkflowEdge
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.schemas.WorkflowEdge.source
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.schemas.WorkflowEdge.target
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.schemas.WorkflowExecutionResponse
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.schemas.WorkflowExecutionResponse.message
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.schemas.WorkflowExecutionResponse.status
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.schemas.WorkflowExecutionResponse.workflow_id
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.schemas.WorkflowNode
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.schemas.WorkflowNode.block_type
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.schemas.WorkflowNode.config
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.schemas.WorkflowNode.execution_mode
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.schemas.WorkflowNode.id
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.schemas.WorkflowNode.layout
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.schemas.WorkflowResponse
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.spa
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.spa.SPAStaticFiles
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.spa.SPAStaticFiles.lookup_path
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.sse
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.sse.sse_handler
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.ws
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.ws.BLOCKS_RELOADED
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.ws.logger
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.ws.serialise_event
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.api.ws.websocket_handler
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.ai
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.ai.ai_block
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.ai.ai_block.AIBlock
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.ai.ai_block.AIBlock.allowed_input_types
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.ai.ai_block.AIBlock.allowed_output_types
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.ai.ai_block.AIBlock.config_schema
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.ai.ai_block.AIBlock.description
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.ai.ai_block.AIBlock.execution_mode
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.ai.ai_block.AIBlock.input_ports
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.ai.ai_block.AIBlock.name
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.ai.ai_block.AIBlock.output_ports
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.ai.ai_block.AIBlock.run
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.ai.ai_block.AIBlock.subcategory
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.ai.ai_block.AIBlock.terminate_grace_sec
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.ai.ai_block.AIBlock.type_name
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.ai.ai_block.AIBlock.validate_config
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.ai.ai_block.AIBlock.variadic_inputs
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.ai.ai_block.AIBlock.variadic_outputs
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.ai.ai_block.AIBlock.version
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.ai.ai_block.logger
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.ai.completion
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.ai.completion.CompletionEvent
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.ai.completion.CompletionEvent.detail
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.ai.completion.CompletionEvent.outputs
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.ai.completion.CompletionEvent.source
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.ai.completion.CompletionSource
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.ai.completion.CompletionSource.FILE_WATCHER
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.ai.completion.CompletionSource.MCP_FINISH_TOOL
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.ai.completion.CompletionSource.USER_MARK_DONE
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.ai.completion.CompletionWatcher
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.ai.completion.CompletionWatcher.cancel
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.ai.completion.CompletionWatcher.poll_interval
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.ai.completion.CompletionWatcher.project_dir
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.ai.completion.CompletionWatcher.run_dir
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.ai.completion.CompletionWatcher.stability_period
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.ai.completion.CompletionWatcher.wait
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.ai.completion.WatcherCancelledError
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.ai.completion.logger
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.ai.parsers
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.ai.parsers.extract_code
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.ai.parsers.extract_json
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.ai.providers
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.ai.providers.AnthropicProvider
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.ai.providers.AnthropicProvider.generate
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.ai.providers.LLMProvider
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.ai.providers.LLMProvider.generate
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.ai.providers.OpenAIProvider
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.ai.providers.OpenAIProvider.generate
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.ai.providers.logger
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.ai.run_dir
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.ai.run_dir.RunDir
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.ai.run_dir.RunDir.block_execution_id
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.ai.run_dir.RunDir.copy_transcript
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.ai.run_dir.RunDir.create
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.ai.run_dir.RunDir.mark_done_signal_path
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.ai.run_dir.RunDir.mcp_signal_path
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.ai.run_dir.RunDir.path
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.ai.run_dir.RunDir.project_dir
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.ai.run_dir.RunDir.write_manifest
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.ai.run_dir.logger
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.app
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.app.app_block
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.app.app_block.AppBlock
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.app.app_block.AppBlock.app_command
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.app.app_block.AppBlock.config_schema
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.app.app_block.AppBlock.description
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.app.app_block.AppBlock.execution_mode
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.app.app_block.AppBlock.input_ports
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.app.app_block.AppBlock.name
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.app.app_block.AppBlock.output_patterns
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.app.app_block.AppBlock.output_ports
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.app.app_block.AppBlock.run
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.app.app_block.AppBlock.terminate_grace_sec
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.app.app_block.AppBlock.variadic_inputs
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.app.app_block.AppBlock.variadic_outputs
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.app.app_block.logger
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.app.bridge
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.app.bridge.ExternalAppBridge
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.app.bridge.ExternalAppBridge.collect
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.app.bridge.ExternalAppBridge.launch
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.app.bridge.ExternalAppBridge.prepare
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.app.bridge.ExternalAppBridge.watch
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.app.bridge.FileExchangeBridge
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.app.bridge.FileExchangeBridge.collect
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.app.bridge.FileExchangeBridge.launch
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.app.bridge.FileExchangeBridge.prepare
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.app.bridge.FileExchangeBridge.watch
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.app.command_validator
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.app.command_validator.validate_app_command
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.app.watcher
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.app.watcher.FileWatcher
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.app.watcher.FileWatcher.directory
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.app.watcher.FileWatcher.patterns
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.app.watcher.FileWatcher.poll_interval
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.app.watcher.FileWatcher.start
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.app.watcher.FileWatcher.stop
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.app.watcher.FileWatcher.timeout
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.app.watcher.FileWatcher.wait_for_output
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.app.watcher.ProcessExitedWithoutOutputError
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.base
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.base.block
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.base.block.Block
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.base.block.Block.allowed_input_types
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.base.block.Block.allowed_output_types
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.base.block.Block.config
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.base.block.Block.config_schema
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.base.block.Block.description
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.base.block.Block.dynamic_ports
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.base.block.Block.execution_mode
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.base.block.Block.get_effective_input_ports
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.base.block.Block.get_effective_output_ports
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.base.block.Block.input_ports
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.base.block.Block.key_dependencies
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.base.block.Block.map_items
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.base.block.Block.max_input_ports
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.base.block.Block.max_output_ports
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.base.block.Block.min_input_ports
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.base.block.Block.min_output_ports
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.base.block.Block.name
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.base.block.Block.output_ports
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.base.block.Block.pack
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.base.block.Block.parallel_map
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.base.block.Block.persist_array
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.base.block.Block.persist_table
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.base.block.Block.postprocess
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.base.block.Block.process_item
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.base.block.Block.run
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.base.block.Block.state
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.base.block.Block.subcategory
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.base.block.Block.terminate_grace_sec
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.base.block.Block.transition
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.base.block.Block.unpack
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.base.block.Block.unpack_single
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.base.block.Block.validate
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.base.block.Block.variadic_inputs
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.base.block.Block.variadic_outputs
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.base.block.Block.version
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.base.config
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.base.config.BlockConfig
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.base.config.BlockConfig.get
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.base.config.BlockConfig.model_config
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.base.config.BlockConfig.params
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.base.package_info
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.base.package_info.PackageInfo
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.base.package_info.PackageInfo.author
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.base.package_info.PackageInfo.description
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.base.package_info.PackageInfo.name
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.base.package_info.PackageInfo.version
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.base.ports
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.base.ports.InputPort
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.base.ports.InputPort.constraint
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.base.ports.InputPort.constraint_description
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.base.ports.InputPort.default
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.base.ports.OutputPort
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.base.ports.Port
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.base.ports.Port.accepted_types
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.base.ports.Port.description
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.base.ports.Port.is_collection
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.base.ports.Port.name
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.base.ports.Port.required
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.base.ports.port_accepts_signature
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.base.ports.port_accepts_type
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.base.ports.ports_from_config_dicts
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.base.ports.validate_connection
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.base.ports.validate_port_constraint
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.base.result
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.base.result.BlockResult
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.base.result.BlockResult.duration_ms
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.base.result.BlockResult.error
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.base.result.BlockResult.outputs
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.base.state
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.base.state.BlockState
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.base.state.BlockState.CANCELLED
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.base.state.BlockState.DONE
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.base.state.BlockState.ERROR
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.base.state.BlockState.IDLE
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.base.state.BlockState.PAUSED
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.base.state.BlockState.READY
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.base.state.BlockState.RUNNING
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.base.state.BlockState.SKIPPED
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.base.state.ExecutionMode
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.base.state.ExecutionMode.AUTO
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.base.state.ExecutionMode.EXTERNAL
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.base.state.ExecutionMode.INTERACTIVE
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.code
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.code.code_block
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.code.code_block.CodeBlock
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.code.code_block.CodeBlock.config_schema
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.code.code_block.CodeBlock.description
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.code.code_block.CodeBlock.input_ports
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.code.code_block.CodeBlock.language
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.code.code_block.CodeBlock.mode
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.code.code_block.CodeBlock.name
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.code.code_block.CodeBlock.output_ports
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.code.code_block.CodeBlock.run
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.code.introspect
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.code.introspect.introspect_script
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.code.lazy_list
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.code.lazy_list.LazyList
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.code.lazy_list.LazyList.to_list
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.code.runner_registry
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.code.runner_registry.RunnerRegistry
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.code.runner_registry.RunnerRegistry.all_runners
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.code.runner_registry.RunnerRegistry.get
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.code.runner_registry.RunnerRegistry.register
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.code.runner_registry.RunnerRegistry.register_defaults
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.code.runners
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.code.runners.base
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.code.runners.base.CodeRunner
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.code.runners.base.CodeRunner.execute_inline
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.code.runners.base.CodeRunner.execute_script
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.code.runners.julia_runner
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.code.runners.julia_runner.JuliaRunner
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.code.runners.julia_runner.JuliaRunner.execute_inline
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.code.runners.julia_runner.JuliaRunner.execute_script
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.code.runners.python_runner
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.code.runners.python_runner.PythonRunner
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.code.runners.python_runner.PythonRunner.execute_inline
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.code.runners.python_runner.PythonRunner.execute_script
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.code.runners.r_runner
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.code.runners.r_runner.RRunner
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.code.runners.r_runner.RRunner.execute_inline
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.code.runners.r_runner.RRunner.execute_script
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.io
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.io.io_block
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.io.io_block.IOBlock
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.io.io_block.IOBlock.config_schema
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.io.io_block.IOBlock.description
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.io.io_block.IOBlock.direction
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.io.io_block.IOBlock.input_ports
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.io.io_block.IOBlock.load
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.io.io_block.IOBlock.name
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.io.io_block.IOBlock.output_ports
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.io.io_block.IOBlock.run
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.io.io_block.IOBlock.save
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.io.io_block.IOBlock.subcategory
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.io.io_block.IOBlock.supported_extensions
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.io.loaders
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.io.loaders.load_data
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.io.loaders.load_data.LoadData
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.io.loaders.load_data.LoadData.config_schema
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.io.loaders.load_data.LoadData.description
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.io.loaders.load_data.LoadData.direction
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.io.loaders.load_data.LoadData.dynamic_ports
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.io.loaders.load_data.LoadData.get_effective_output_ports
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.io.loaders.load_data.LoadData.load
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.io.loaders.load_data.LoadData.name
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.io.loaders.load_data.LoadData.output_ports
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.io.loaders.load_data.LoadData.save
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.io.loaders.load_data.LoadData.subcategory
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.io.loaders.load_data.LoadData.supported_extensions
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.io.loaders.load_data.LoadData.type_name
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.io.savers
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.io.savers.save_data
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.io.savers.save_data.SaveData
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.io.savers.save_data.SaveData.config_schema
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.io.savers.save_data.SaveData.description
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.io.savers.save_data.SaveData.direction
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.io.savers.save_data.SaveData.dynamic_ports
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.io.savers.save_data.SaveData.get_effective_input_ports
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.io.savers.save_data.SaveData.input_ports
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.io.savers.save_data.SaveData.load
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.io.savers.save_data.SaveData.name
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.io.savers.save_data.SaveData.output_ports
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.io.savers.save_data.SaveData.save
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.io.savers.save_data.SaveData.subcategory
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.io.savers.save_data.SaveData.supported_extensions
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.io.savers.save_data.SaveData.type_name
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.io.savers.save_data.logger
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.process
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.process.builtins
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.process.builtins.data_router
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.process.builtins.data_router.DataRouter
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.process.builtins.data_router.DataRouter.algorithm
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.process.builtins.data_router.DataRouter.allowed_input_types
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.process.builtins.data_router.DataRouter.allowed_output_types
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.process.builtins.data_router.DataRouter.description
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.process.builtins.data_router.DataRouter.execution_mode
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.process.builtins.data_router.DataRouter.min_input_ports
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.process.builtins.data_router.DataRouter.min_output_ports
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.process.builtins.data_router.DataRouter.name
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.process.builtins.data_router.DataRouter.prepare_prompt
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.process.builtins.data_router.DataRouter.run
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.process.builtins.data_router.DataRouter.subcategory
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.process.builtins.data_router.DataRouter.variadic_inputs
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.process.builtins.data_router.DataRouter.variadic_outputs
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.process.builtins.data_router.logger
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.process.builtins.expression_evaluator
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.process.builtins.expression_evaluator.ExpressionEvaluator
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.process.builtins.expression_evaluator.ExpressionEvaluator.evaluate
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.process.builtins.expression_evaluator.ExpressionEvaluator.source
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.process.builtins.expression_evaluator.build_scope
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.process.builtins.filter_collection
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.process.builtins.filter_collection.FilterCollection
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.process.builtins.filter_collection.FilterCollection.algorithm
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.process.builtins.filter_collection.FilterCollection.description
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.process.builtins.filter_collection.FilterCollection.input_ports
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.process.builtins.filter_collection.FilterCollection.name
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.process.builtins.filter_collection.FilterCollection.output_ports
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.process.builtins.filter_collection.FilterCollection.run
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.process.builtins.merge
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.process.builtins.merge.MergeBlock
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.process.builtins.merge.MergeBlock.algorithm
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.process.builtins.merge.MergeBlock.description
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.process.builtins.merge.MergeBlock.input_ports
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.process.builtins.merge.MergeBlock.name
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.process.builtins.merge.MergeBlock.output_ports
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.process.builtins.merge.MergeBlock.run
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.process.builtins.merge_collection
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.process.builtins.merge_collection.MergeCollection
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.process.builtins.merge_collection.MergeCollection.algorithm
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.process.builtins.merge_collection.MergeCollection.description
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.process.builtins.merge_collection.MergeCollection.input_ports
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.process.builtins.merge_collection.MergeCollection.name
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.process.builtins.merge_collection.MergeCollection.output_ports
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.process.builtins.merge_collection.MergeCollection.run
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.process.builtins.pair_editor
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.process.builtins.pair_editor.PairEditor
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.process.builtins.pair_editor.PairEditor.algorithm
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.process.builtins.pair_editor.PairEditor.allowed_input_types
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.process.builtins.pair_editor.PairEditor.allowed_output_types
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.process.builtins.pair_editor.PairEditor.description
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.process.builtins.pair_editor.PairEditor.execution_mode
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.process.builtins.pair_editor.PairEditor.max_input_ports
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.process.builtins.pair_editor.PairEditor.min_input_ports
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.process.builtins.pair_editor.PairEditor.name
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.process.builtins.pair_editor.PairEditor.prepare_prompt
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.process.builtins.pair_editor.PairEditor.run
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.process.builtins.pair_editor.PairEditor.subcategory
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.process.builtins.pair_editor.PairEditor.variadic_inputs
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.process.builtins.pair_editor.PairEditor.variadic_outputs
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.process.builtins.pair_editor.logger
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.process.builtins.slice_collection
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.process.builtins.slice_collection.SliceCollection
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.process.builtins.slice_collection.SliceCollection.algorithm
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.process.builtins.slice_collection.SliceCollection.description
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.process.builtins.slice_collection.SliceCollection.input_ports
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.process.builtins.slice_collection.SliceCollection.name
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.process.builtins.slice_collection.SliceCollection.output_ports
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.process.builtins.slice_collection.SliceCollection.run
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.process.builtins.split
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.process.builtins.split.SplitBlock
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.process.builtins.split.SplitBlock.algorithm
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.process.builtins.split.SplitBlock.description
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.process.builtins.split.SplitBlock.input_ports
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.process.builtins.split.SplitBlock.name
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.process.builtins.split.SplitBlock.output_ports
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.process.builtins.split.SplitBlock.run
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.process.builtins.split_collection
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.process.builtins.split_collection.SplitCollection
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.process.builtins.split_collection.SplitCollection.algorithm
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.process.builtins.split_collection.SplitCollection.description
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.process.builtins.split_collection.SplitCollection.input_ports
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.process.builtins.split_collection.SplitCollection.name
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.process.builtins.split_collection.SplitCollection.output_ports
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.process.builtins.split_collection.SplitCollection.run
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.process.process_block
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.process.process_block.ProcessBlock
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.process.process_block.ProcessBlock.algorithm
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.process.process_block.ProcessBlock.process_item
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.process.process_block.ProcessBlock.run
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.process.process_block.ProcessBlock.setup
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.process.process_block.ProcessBlock.teardown
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.process.utils
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.process.utils.to_arrow
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.registry
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.registry.BlockRegistrationError
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.registry.BlockRegistry
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.registry.BlockRegistry.add_scan_dir
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.registry.BlockRegistry.all_specs
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.registry.BlockRegistry.find_io_blocks_for_type
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.registry.BlockRegistry.find_loader
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.registry.BlockRegistry.find_saver
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.registry.BlockRegistry.get_spec
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.registry.BlockRegistry.hot_reload
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.registry.BlockRegistry.instantiate
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.registry.BlockRegistry.packages
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.registry.BlockRegistry.scan
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.registry.BlockRegistry.specs_by_package
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.registry.BlockSpec
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.registry.BlockSpec.allowed_input_types
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.registry.BlockSpec.allowed_output_types
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.registry.BlockSpec.base_category
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.registry.BlockSpec.class_name
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.registry.BlockSpec.config_schema
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.registry.BlockSpec.description
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.registry.BlockSpec.direction
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.registry.BlockSpec.dynamic_ports
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.registry.BlockSpec.file_mtime
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.registry.BlockSpec.file_path
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.registry.BlockSpec.input_ports
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.registry.BlockSpec.max_input_ports
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.registry.BlockSpec.max_output_ports
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.registry.BlockSpec.min_input_ports
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.registry.BlockSpec.min_output_ports
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.registry.BlockSpec.module_path
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.registry.BlockSpec.name
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.registry.BlockSpec.output_ports
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.registry.BlockSpec.package_name
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.registry.BlockSpec.source
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.registry.BlockSpec.subcategory
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.registry.BlockSpec.supported_extensions
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.registry.BlockSpec.type_name
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.registry.BlockSpec.variadic_inputs
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.registry.BlockSpec.variadic_outputs
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.registry.BlockSpec.version
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.registry.logger
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.subworkflow
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.subworkflow.subworkflow_block
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.subworkflow.subworkflow_block.SubWorkflowBlock
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.subworkflow.subworkflow_block.SubWorkflowBlock.config_schema
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.subworkflow.subworkflow_block.SubWorkflowBlock.description
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.subworkflow.subworkflow_block.SubWorkflowBlock.input_mapping
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.subworkflow.subworkflow_block.SubWorkflowBlock.input_ports
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.subworkflow.subworkflow_block.SubWorkflowBlock.name
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.subworkflow.subworkflow_block.SubWorkflowBlock.output_mapping
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.subworkflow.subworkflow_block.SubWorkflowBlock.output_ports
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.subworkflow.subworkflow_block.SubWorkflowBlock.run
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.subworkflow.subworkflow_block.SubWorkflowBlock.workflow_ref
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.blocks.subworkflow.subworkflow_block.logger
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.cli
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.cli.install
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.cli.install.InstallResult
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.cli.install.InstallResult.action
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.cli.install.InstallResult.detail
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.cli.install.InstallResult.path
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.cli.install.InstallResult.scope
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.cli.install.InstallResult.target
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.cli.install.MCP_SERVER_NAME
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.cli.install.app
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.cli.install.logger
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.cli.install.perform_install
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.cli.install.register
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.cli.main
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.cli.main.app
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.cli.main.blocks
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.cli.main.gui
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.cli.main.init
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.cli.main.init_block_package
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.cli.main.run
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.cli.main.serve
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.cli.main.validate
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.cli.mcp_bridge
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.cli.mcp_bridge.logger
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.cli.mcp_bridge.register
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.cli.mcp_bridge.run
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.cli.templates
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.lineage
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.lineage.environment
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.lineage.environment.EnvironmentSnapshot
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.lineage.environment.EnvironmentSnapshot.capture
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.lineage.environment.EnvironmentSnapshot.conda_env
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.lineage.environment.EnvironmentSnapshot.from_dict
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.lineage.environment.EnvironmentSnapshot.full_freeze
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.lineage.environment.EnvironmentSnapshot.key_packages
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.lineage.environment.EnvironmentSnapshot.platform
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.lineage.environment.EnvironmentSnapshot.python_version
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.lineage.environment.EnvironmentSnapshot.to_dict
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.lineage.methods_export
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.lineage.methods_export.render_methods_markdown
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.lineage.record
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.lineage.record.BlockExecutionRecord
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.lineage.record.BlockExecutionRecord.block_config_resolved
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.lineage.record.BlockExecutionRecord.block_execution_id
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.lineage.record.BlockExecutionRecord.block_id
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.lineage.record.BlockExecutionRecord.block_type
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.lineage.record.BlockExecutionRecord.block_version
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.lineage.record.BlockExecutionRecord.duration_ms
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.lineage.record.BlockExecutionRecord.finished_at
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.lineage.record.BlockExecutionRecord.run_id
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.lineage.record.BlockExecutionRecord.started_at
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.lineage.record.BlockExecutionRecord.termination
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.lineage.record.BlockExecutionRecord.termination_detail
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.lineage.record.BlockIORow
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.lineage.record.BlockIORow.block_execution_id
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.lineage.record.BlockIORow.direction
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.lineage.record.BlockIORow.object_id
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.lineage.record.BlockIORow.port_name
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.lineage.record.BlockIORow.position
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.lineage.record.DataObjectRow
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.lineage.record.DataObjectRow.backend
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.lineage.record.DataObjectRow.created_at
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.lineage.record.DataObjectRow.derived_from
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.lineage.record.DataObjectRow.mtime_at_write
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.lineage.record.DataObjectRow.object_id
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.lineage.record.DataObjectRow.produced_by_execution
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.lineage.record.DataObjectRow.size_bytes
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.lineage.record.DataObjectRow.storage_path
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.lineage.record.DataObjectRow.type_name
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.lineage.record.DataObjectRow.wire_payload
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.lineage.record.RunRecord
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.lineage.record.RunRecord.environment_snapshot
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.lineage.record.RunRecord.execute_from_block_id
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.lineage.record.RunRecord.finished_at
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.lineage.record.RunRecord.parent_run_id
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.lineage.record.RunRecord.run_id
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.lineage.record.RunRecord.started_at
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.lineage.record.RunRecord.status
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.lineage.record.RunRecord.triggered_by
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.lineage.record.RunRecord.user_notes
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.lineage.record.RunRecord.workflow_dirty
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.lineage.record.RunRecord.workflow_git_commit
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.lineage.record.RunRecord.workflow_id
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.lineage.record.RunRecord.workflow_yaml_snapshot
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.lineage.recorder
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.lineage.recorder.LineageRecorder
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.lineage.recorder.LineageRecorder.begin_run
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.lineage.recorder.LineageRecorder.dispose
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.lineage.recorder.LineageRecorder.finalize_run
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.lineage.recorder.LineageRecorder.record_start
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.lineage.recorder.LineageRecorder.run_id
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.lineage.recorder.logger
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.lineage.run_context
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.lineage.run_context.RunContext
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.lineage.run_context.RunContext.block_execution_id
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.lineage.run_context.RunContext.run_id
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.lineage.run_context.get_run_context
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.lineage.run_context.reset_run_context
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.lineage.run_context.set_run_context
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.lineage.store
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.lineage.store.LineageStore
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.lineage.store.LineageStore.close
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.lineage.store.LineageStore.count
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.lineage.store.LineageStore.execute_query
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.lineage.store.LineageStore.finalize_run
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.lineage.store.LineageStore.get_data_object
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.lineage.store.LineageStore.get_run
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.lineage.store.LineageStore.insert_block_execution
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.lineage.store.LineageStore.insert_block_io
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.lineage.store.LineageStore.insert_run
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.lineage.store.LineageStore.list_block_executions
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.lineage.store.LineageStore.list_block_io
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.lineage.store.LineageStore.list_block_io_with_objects
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.lineage.store.LineageStore.list_runs
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.lineage.store.LineageStore.set_pending_git_commit
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.lineage.store.LineageStore.upsert_data_object
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.lineage.store.logger
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.meta
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.meta.channel
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.meta.channel.ChannelInfo
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.meta.channel.ChannelInfo.dye
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.meta.channel.ChannelInfo.emission_nm
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.meta.channel.ChannelInfo.excitation_nm
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.meta.channel.ChannelInfo.model_config
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.meta.channel.ChannelInfo.name
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.meta.framework
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.meta.framework.FrameworkMeta
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.meta.framework.FrameworkMeta.created_at
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.meta.framework.FrameworkMeta.derive
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.meta.framework.FrameworkMeta.derived_from
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.meta.framework.FrameworkMeta.lineage_id
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.meta.framework.FrameworkMeta.model_config
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.meta.framework.FrameworkMeta.object_id
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.meta.framework.FrameworkMeta.source
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.meta.framework.FrameworkMeta.with_lineage_id
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.metadata_store
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.metadata_store.MetadataStore
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.metadata_store.MetadataStore.ancestors
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.metadata_store.MetadataStore.close
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.metadata_store.MetadataStore.delete
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.metadata_store.MetadataStore.descendants
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.metadata_store.MetadataStore.get
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.metadata_store.MetadataStore.get_by_storage_path
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.metadata_store.MetadataStore.get_wire
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.metadata_store.MetadataStore.get_wire_by_storage_path
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.metadata_store.MetadataStore.list_by_type
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.metadata_store.MetadataStore.list_by_workflow
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.metadata_store.MetadataStore.put
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.metadata_store.MetadataStore.put_wire
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.metadata_store.MetadataStore.put_wire_if_missing
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.metadata_store.MetadataStore.vacuum
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.metadata_store.get_metadata_store
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.metadata_store.logger
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.metadata_store.set_metadata_store
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.storage
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.storage.arrow_backend
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.storage.arrow_backend.ArrowBackend
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.storage.arrow_backend.ArrowBackend.get_metadata
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.storage.arrow_backend.ArrowBackend.iter_chunks
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.storage.arrow_backend.ArrowBackend.read
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.storage.arrow_backend.ArrowBackend.slice
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.storage.arrow_backend.ArrowBackend.write
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.storage.arrow_backend.ArrowBackend.write_from_memory
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.storage.backend_router
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.storage.backend_router.BackendRouter
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.storage.backend_router.BackendRouter.backend_for
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.storage.backend_router.BackendRouter.backend_name_for
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.storage.backend_router.BackendRouter.extension_for
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.storage.backend_router.BackendRouter.register
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.storage.backend_router.BackendRouter.resolve
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.storage.backend_router.get_router
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.storage.base
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.storage.base.StorageBackend
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.storage.base.StorageBackend.get_metadata
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.storage.base.StorageBackend.iter_chunks
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.storage.base.StorageBackend.read
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.storage.base.StorageBackend.slice
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.storage.base.StorageBackend.write
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.storage.base.StorageBackend.write_from_memory
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.storage.composite_store
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.storage.composite_store.CompositeStore
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.storage.composite_store.CompositeStore.get_metadata
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.storage.composite_store.CompositeStore.iter_chunks
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.storage.composite_store.CompositeStore.read
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.storage.composite_store.CompositeStore.slice
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.storage.composite_store.CompositeStore.write
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.storage.composite_store.CompositeStore.write_from_memory
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.storage.filesystem
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.storage.filesystem.FilesystemBackend
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.storage.filesystem.FilesystemBackend.get_metadata
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.storage.filesystem.FilesystemBackend.iter_chunks
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.storage.filesystem.FilesystemBackend.read
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.storage.filesystem.FilesystemBackend.slice
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.storage.filesystem.FilesystemBackend.write
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.storage.filesystem.FilesystemBackend.write_from_memory
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.storage.flush_context
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.storage.flush_context.clear
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.storage.flush_context.get_output_dir
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.storage.flush_context.set_output_dir
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.storage.ref
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.storage.ref.StorageReference
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.storage.ref.StorageReference.backend
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.storage.ref.StorageReference.format
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.storage.ref.StorageReference.metadata
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.storage.ref.StorageReference.path
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.storage.zarr_backend
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.storage.zarr_backend.ZarrBackend
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.storage.zarr_backend.ZarrBackend.get_metadata
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.storage.zarr_backend.ZarrBackend.iter_chunks
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.storage.zarr_backend.ZarrBackend.read
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.storage.zarr_backend.ZarrBackend.slice
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.storage.zarr_backend.ZarrBackend.write
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.storage.zarr_backend.ZarrBackend.write_from_memory
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.types
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.types.array
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.types.array.Array
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.types.array.Array.allowed_axes
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.types.array.Array.axes
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.types.array.Array.canonical_order
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.types.array.Array.chunk_shape
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.types.array.Array.dtype
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.types.array.Array.iter_over
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.types.array.Array.ndim
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.types.array.Array.required_axes
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.types.array.Array.sel
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.types.array.Array.shape
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.types.array.Array.to_memory
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.types.array.Array.with_meta
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.types.artifact
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.types.artifact.Artifact
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.types.artifact.Artifact.description
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.types.artifact.Artifact.file_path
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.types.artifact.Artifact.get_in_memory_data
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.types.artifact.Artifact.mime_type
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.types.artifact.Artifact.with_meta
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.types.base
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.types.base.DataObject
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.types.base.DataObject.Meta
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.types.base.DataObject.dtype_info
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.types.base.DataObject.framework
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.types.base.DataObject.get_in_memory_data
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.types.base.DataObject.iter_chunks
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.types.base.DataObject.meta
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.types.base.DataObject.metadata
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.types.base.DataObject.save
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.types.base.DataObject.slice
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.types.base.DataObject.storage_ref
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.types.base.DataObject.to_memory
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.types.base.DataObject.user
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.types.base.DataObject.with_meta
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.types.base.TypeSignature
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.types.base.TypeSignature.from_type
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.types.base.TypeSignature.matches
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.types.base.TypeSignature.required_axes
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.types.base.TypeSignature.slot_schema
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.types.base.TypeSignature.type_chain
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.types.collection
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.types.collection.Collection
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.types.collection.Collection.item_type
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.types.collection.Collection.length
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.types.collection.Collection.storage_refs
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.types.composite
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.types.composite.CompositeData
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.types.composite.CompositeData.expected_slots
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.types.composite.CompositeData.get
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.types.composite.CompositeData.get_in_memory_data
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.types.composite.CompositeData.set
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.types.composite.CompositeData.slot_names
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.types.composite.CompositeData.slot_types
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.types.composite.CompositeData.with_meta
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.types.dataframe
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.types.dataframe.DataFrame
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.types.dataframe.DataFrame.columns
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.types.dataframe.DataFrame.row_count
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.types.dataframe.DataFrame.schema
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.types.dataframe.DataFrame.with_meta
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.types.registry
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.types.registry.TypeRegistry
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.types.registry.TypeRegistry.all_types
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.types.registry.TypeRegistry.is_instance
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.types.registry.TypeRegistry.load_class
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.types.registry.TypeRegistry.register
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.types.registry.TypeRegistry.register_class
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.types.registry.TypeRegistry.resolve
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.types.registry.TypeRegistry.scan_all
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.types.registry.TypeRegistry.scan_builtins
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.types.registry.TypeSpec
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.types.registry.TypeSpec.base_type
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.types.registry.TypeSpec.class_name
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.types.registry.TypeSpec.description
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.types.registry.TypeSpec.module_path
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.types.registry.TypeSpec.name
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.types.registry.logger
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.types.serialization
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.types.series
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.types.series.Series
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.types.series.Series.index_name
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.types.series.Series.length
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.types.series.Series.value_name
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.types.series.Series.with_meta
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.types.text
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.types.text.Text
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.types.text.Text.content
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.types.text.Text.encoding
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.types.text.Text.format
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.types.text.Text.get_in_memory_data
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.types.text.Text.with_meta
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.units
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.units.PhysicalQuantity
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.units.PhysicalQuantity.to
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.units.PhysicalQuantity.unit
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.units.PhysicalQuantity.value
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.versioning
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.versioning.git_binary
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.versioning.git_binary.BundledGitMissing
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.versioning.git_binary.GitBinary
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.versioning.git_binary.GitBinary.locate
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.versioning.git_binary.GitBinary.path
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.versioning.git_binary.GitBinary.run
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.versioning.git_binary.GitBinary.version
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.versioning.git_binary.logger
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.versioning.git_engine
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.versioning.git_engine.GitEngine
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.versioning.git_engine.GitEngine.branch_create
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.versioning.git_engine.GitEngine.branch_delete
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.versioning.git_engine.GitEngine.branch_switch
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.versioning.git_engine.GitEngine.branches
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.versioning.git_engine.GitEngine.cherry_pick
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.versioning.git_engine.GitEngine.commit
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.versioning.git_engine.GitEngine.current_branch
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.versioning.git_engine.GitEngine.diff
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.versioning.git_engine.GitEngine.head_state
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.versioning.git_engine.GitEngine.init_repository
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.versioning.git_engine.GitEngine.is_repository
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.versioning.git_engine.GitEngine.log
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.versioning.git_engine.GitEngine.merge
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.versioning.git_engine.GitEngine.merge_abort
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.versioning.git_engine.GitEngine.merge_complete
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.versioning.git_engine.GitEngine.merge_stage_file
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.versioning.git_engine.GitEngine.project_path
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.versioning.git_engine.GitEngine.restore
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.versioning.git_engine.GitEngine.stash_apply
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.versioning.git_engine.GitEngine.stash_drop
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.versioning.git_engine.GitEngine.stash_list
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.versioning.git_engine.GitEngine.stash_save
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.versioning.git_engine.GitEngine.status
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.versioning.git_engine.GitError
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.versioning.git_engine.GitError.git_args
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.versioning.git_engine.GitError.returncode
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.versioning.git_engine.GitError.stderr
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.versioning.git_engine.HeadState
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.versioning.git_engine.HeadState.commit_sha
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.versioning.git_engine.HeadState.dirty
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.versioning.git_engine.MergeResult
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.versioning.git_engine.logger
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.versioning.gitignore_template
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.versioning.gitignore_template.DEFAULT_GITIGNORE
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.versioning.gitignore_template.write_default_gitignore
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.versioning.status
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.versioning.status.is_dirty
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.core.versioning.status.modified_files
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.checkpoint
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.checkpoint.CheckpointManager
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.checkpoint.CheckpointManager.latest
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.checkpoint.CheckpointManager.load
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.checkpoint.CheckpointManager.save
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.checkpoint.WorkflowCheckpoint
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.checkpoint.WorkflowCheckpoint.block_states
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.checkpoint.WorkflowCheckpoint.config_snapshot
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.checkpoint.WorkflowCheckpoint.intermediate_refs
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.checkpoint.WorkflowCheckpoint.pending_block
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.checkpoint.WorkflowCheckpoint.skip_reasons
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.checkpoint.WorkflowCheckpoint.timestamp
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.checkpoint.WorkflowCheckpoint.workflow_id
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.checkpoint.deserialize_intermediate_refs
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.checkpoint.load_checkpoint
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.checkpoint.logger
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.checkpoint.save_checkpoint
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.checkpoint.serialize_intermediate_refs
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.dag
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.dag.CycleError
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.dag.DAG
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.dag.DAG.adjacency
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.dag.DAG.edge_map
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.dag.DAG.edges
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.dag.DAG.nodes
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.dag.DAG.reverse_adjacency
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.dag.build_dag
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.dag.get_downstream_blocks
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.dag.get_leaf_nodes
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.dag.get_root_nodes
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.dag.topological_sort
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.events
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.events.BLOCK_CANCELLED
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.events.BLOCK_DONE
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.events.BLOCK_ERROR
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.events.BLOCK_PAUSED
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.events.BLOCK_READY
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.events.BLOCK_RUNNING
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.events.BLOCK_SKIPPED
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.events.CANCEL_BLOCK_REQUEST
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.events.CANCEL_WORKFLOW_REQUEST
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.events.CHECKPOINT_SAVED
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.events.EngineEvent
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.events.EngineEvent.block_id
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.events.EngineEvent.data
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.events.EngineEvent.event_type
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.events.EngineEvent.timestamp
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.events.EventBus
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.events.EventBus.emit
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.events.EventBus.subscribe
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.events.EventBus.unsubscribe
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.events.GIT_HEAD_CHANGED
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.events.INTERACTIVE_COMPLETE
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.events.INTERACTIVE_PROMPT
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.events.PROCESS_EXITED
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.events.PROCESS_SPAWNED
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.events.WORKFLOW_CHANGED
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.events.WORKFLOW_COMPLETED
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.events.WORKFLOW_STARTED
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.events.logger
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.lineage_recorder
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.materialisation
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.materialisation.materialise_to_file
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.materialisation.reconstruct_from_file
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.pty_control
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.pty_control.PtyTabSpec
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.pty_control.PtyTabSpec.block_run_id
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.pty_control.PtyTabSpec.cwd
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.pty_control.PtyTabSpec.initial_stdin
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.pty_control.PtyTabSpec.permission_mode
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.pty_control.PtyTabSpec.run_dir_path
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.pty_control.PtyTabSpec.spawn_argv
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.pty_control.PtyTabSpec.title
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.pty_control.get_in_process_handler
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.pty_control.logger
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.pty_control.notify_block_pty_event
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.pty_control.request_pty_tab
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.pty_control.set_in_process_handler
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.resources
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.resources.ResourceManager
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.resources.ResourceManager.acquire
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.resources.ResourceManager.available
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.resources.ResourceManager.can_dispatch
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.resources.ResourceManager.gpu_slots
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.resources.ResourceManager.max_cpu_workers
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.resources.ResourceManager.memory_critical
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.resources.ResourceManager.memory_high_watermark
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.resources.ResourceManager.release
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.resources.ResourceRequest
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.resources.ResourceRequest.cpu_cores
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.resources.ResourceRequest.effective_cpu
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.resources.ResourceRequest.gpu_memory_gb
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.resources.ResourceRequest.max_internal_workers
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.resources.ResourceRequest.requires_gpu
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.resources.ResourceSnapshot
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.resources.ResourceSnapshot.available_cpu_workers
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.resources.ResourceSnapshot.available_gpu_slots
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.resources.ResourceSnapshot.system_memory_percent
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.resources.logger
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.runners
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.runners.base
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.runners.base.BlockRunner
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.runners.base.BlockRunner.cancel
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.runners.base.BlockRunner.check_status
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.runners.base.BlockRunner.run
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.runners.local
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.runners.local.LocalRunner
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.runners.local.LocalRunner.cancel
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.runners.local.LocalRunner.check_status
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.runners.local.LocalRunner.run
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.runners.local.logger
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.runners.platform
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.runners.platform.PlatformOps
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.runners.platform.PlatformOps.assign_to_job
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.runners.platform.PlatformOps.create_job_object
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.runners.platform.PlatformOps.create_process_group
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.runners.platform.PlatformOps.get_exit_info
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.runners.platform.PlatformOps.is_alive
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.runners.platform.PlatformOps.kill_tree
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.runners.platform.PlatformOps.terminate_tree
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.runners.platform.PosixOps
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.runners.platform.PosixOps.assign_to_job
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.runners.platform.PosixOps.create_job_object
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.runners.platform.PosixOps.create_process_group
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.runners.platform.PosixOps.get_exit_info
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.runners.platform.PosixOps.is_alive
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.runners.platform.PosixOps.kill_tree
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.runners.platform.PosixOps.terminate_tree
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.runners.platform.WindowsOps
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.runners.platform.WindowsOps.assign_to_job
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.runners.platform.WindowsOps.create_job_object
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.runners.platform.WindowsOps.create_process_group
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.runners.platform.WindowsOps.get_exit_info
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.runners.platform.WindowsOps.is_alive
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.runners.platform.WindowsOps.kill_tree
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.runners.platform.WindowsOps.terminate_tree
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.runners.platform.get_platform_ops
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.runners.platform.logger
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.runners.process_handle
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.runners.process_handle.ProcessExitInfo
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.runners.process_handle.ProcessExitInfo.exit_code
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.runners.process_handle.ProcessExitInfo.platform_detail
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.runners.process_handle.ProcessExitInfo.signal_number
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.runners.process_handle.ProcessExitInfo.was_killed_by_framework
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.runners.process_handle.ProcessHandle
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.runners.process_handle.ProcessHandle.block_id
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.runners.process_handle.ProcessHandle.exit_info
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.runners.process_handle.ProcessHandle.is_alive
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.runners.process_handle.ProcessHandle.kill
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.runners.process_handle.ProcessHandle.pid
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.runners.process_handle.ProcessHandle.resource_request
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.runners.process_handle.ProcessHandle.start_time
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.runners.process_handle.ProcessHandle.terminate
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.runners.process_handle.ProcessHandle.was_killed_by_framework
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.runners.process_handle.ProcessRegistry
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.runners.process_handle.ProcessRegistry.active_handles
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.runners.process_handle.ProcessRegistry.deregister
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.runners.process_handle.ProcessRegistry.get_handle
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.runners.process_handle.ProcessRegistry.register
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.runners.process_handle.ProcessRegistry.terminate_all
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.runners.process_handle.build_worker_payload
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.runners.process_handle.logger
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.runners.process_handle.register_async_process
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.runners.process_handle.spawn_block_process
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.runners.process_monitor
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.runners.process_monitor.ProcessMonitor
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.runners.process_monitor.ProcessMonitor.start
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.runners.process_monitor.ProcessMonitor.stop
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.runners.process_monitor.logger
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.runners.terminal_state
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.runners.terminal_state.BlockTerminalStateReportedError
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.runners.terminal_state.BlockTerminalStateReportedError.outputs
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.runners.terminal_state.BlockTerminalStateReportedError.state
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.runners.worker
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.runners.worker.logger
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.runners.worker.main
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.runners.worker.reconstruct_inputs
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.runners.worker.serialise_outputs
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.scheduler
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.scheduler.DAGScheduler
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.scheduler.DAGScheduler.block_states
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.scheduler.DAGScheduler.cancel_block
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.scheduler.DAGScheduler.cancel_workflow
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.scheduler.DAGScheduler.execute
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.scheduler.DAGScheduler.execute_from
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.scheduler.DAGScheduler.pause
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.scheduler.DAGScheduler.rerun_block
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.scheduler.DAGScheduler.reset_block
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.scheduler.DAGScheduler.resume
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.scheduler.DAGScheduler.save_checkpoint
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.scheduler.DAGScheduler.set_state
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.scheduler.DAGScheduler.skip_reasons
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.scheduler.RunHandle
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.scheduler.RunHandle.process_handle
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.scheduler.RunHandle.result
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.scheduler.RunHandle.run_id
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.engine.scheduler.logger
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.testing
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.testing.harness
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.testing.harness.BlockTestHarness
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.testing.harness.BlockTestHarness.block_class
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.testing.harness.BlockTestHarness.smoke_test
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.testing.harness.BlockTestHarness.validate_block
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.testing.harness.BlockTestHarness.validate_entry_point_callable
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.testing.harness.BlockTestHarness.validate_package_info
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.testing.harness.BlockTestHarness.work_dir
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.utils
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.utils.axis_iter
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.utils.axis_iter.SliceFn
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.utils.axis_iter.iterate_over_axes
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.utils.broadcast
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.utils.broadcast.BroadcastError
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.utils.broadcast.broadcast_apply
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.utils.broadcast.iter_axis_slices
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.utils.constraints
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.utils.constraints.ConstraintFn
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.utils.constraints.has_axes
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.utils.constraints.has_dtype
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.utils.constraints.has_exact_axes
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.utils.constraints.has_min_shape
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.utils.constraints.has_shape
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.utils.constraints.is_2d
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.utils.constraints.is_3d
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.utils.fs
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.utils.fs.mount_pathlike
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.utils.hashing
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.utils.hashing.collection_hashes
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.utils.hashing.content_hash
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.utils.logging
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.utils.logging.configure_logging
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.utils.wrapping
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.utils.wrapping.wrap_as_dataobject
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.workflow
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.workflow.definition
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.workflow.definition.EdgeDef
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.workflow.definition.EdgeDef.source
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.workflow.definition.EdgeDef.target
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.workflow.definition.NodeDef
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.workflow.definition.NodeDef.block_type
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.workflow.definition.NodeDef.config
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.workflow.definition.NodeDef.execution_mode
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.workflow.definition.NodeDef.id
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.workflow.definition.NodeDef.layout
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.workflow.definition.WorkflowDefinition
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.workflow.definition.WorkflowDefinition.description
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.workflow.definition.WorkflowDefinition.edges
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.workflow.definition.WorkflowDefinition.id
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.workflow.definition.WorkflowDefinition.metadata
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.workflow.definition.WorkflowDefinition.nodes
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.workflow.definition.WorkflowDefinition.version
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.workflow.layout
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.workflow.layout.LayoutInfo
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.workflow.layout.LayoutInfo.node_positions
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.workflow.layout.LayoutInfo.pan_x
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.workflow.layout.LayoutInfo.pan_y
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.workflow.layout.LayoutInfo.zoom
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.workflow.schema
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.workflow.schema.EdgeModel
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.workflow.schema.EdgeModel.from_edge_def
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.workflow.schema.EdgeModel.must_be_port_reference
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.workflow.schema.EdgeModel.source
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.workflow.schema.EdgeModel.target
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.workflow.schema.EdgeModel.to_edge_def
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.workflow.schema.NodeModel
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.workflow.schema.NodeModel.block_type
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.workflow.schema.NodeModel.config
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.workflow.schema.NodeModel.execution_mode
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.workflow.schema.NodeModel.from_node_def
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.workflow.schema.NodeModel.id
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.workflow.schema.NodeModel.id_must_be_nonempty
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.workflow.schema.NodeModel.layout
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.workflow.schema.NodeModel.to_node_def
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.workflow.schema.WorkflowFileModel
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.workflow.schema.WorkflowFileModel.workflow
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.workflow.schema.WorkflowModel
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.workflow.schema.WorkflowModel.description
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.workflow.schema.WorkflowModel.edges
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.workflow.schema.WorkflowModel.from_definition
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.workflow.schema.WorkflowModel.id
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.workflow.schema.WorkflowModel.metadata
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.workflow.schema.WorkflowModel.nodes
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.workflow.schema.WorkflowModel.to_definition
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.workflow.schema.WorkflowModel.version
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.workflow.serializer
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.workflow.serializer.absolutify_paths
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.workflow.serializer.load_yaml
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.workflow.serializer.relativify_paths
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.workflow.serializer.save_yaml
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.workflow.validator
- `closure.missing-symbol-governance` at `griffe`: public symbol has no governing ADR/spec module or contract claim: scieasy.workflow.validator.validate_workflow

## 7. Child Reports

| Tool | Status | Errors | Summary |
|---|---|---:|---|
| `generate_facts` | `pass` | 0 | facts_path=docs/facts/generated.yaml, total_facts=1720, symbol_facts=1689 |
| `fact_drift` | `pass` | 0 | docs_checked=90, substitutions_checked=0 |
| `doc_drift` | `fail` | 19 | governed_docs_checked=5, modules_checked=5, contracts_checked=50, files_checked=39 |
| `closure` | `fail` | 1494 | governed_docs_checked=5, governed_modules=3, governed_contracts=27, symbols_checked=1689 |
| `signature_drift` | `pass` | 0 | expected_signatures_checked=31, symbols_available=1689 |
