# Semantic duplication scan (`src\scistudio`)

- Functions scanned: 1248
- Model: `BAAI/bge-base-en-v1.5`
- Cosine threshold: `0.92`
- Min LOC: `5`
- Candidate duplicate clusters: **59**
- LOC inside duplicate clusters: **3445** / 34636 (9.9%)
- Largest cluster: **9** functions

## Cluster 1 - 7 funcs, 290 LOC, avg sim=0.979

- `src/scistudio/core/types/array.py:327`  `Array.with_meta`  (39 LOC)
- `src/scistudio/core/types/artifact.py:52`  `Artifact.with_meta`  (38 LOC)
- `src/scistudio/core/types/base.py:286`  `DataObject.with_meta`  (59 LOC)
- `src/scistudio/core/types/composite.py:96`  `CompositeData.with_meta`  (41 LOC)
- `src/scistudio/core/types/dataframe.py:55`  `DataFrame.with_meta`  (38 LOC)
- `src/scistudio/core/types/series.py:57`  `Series.with_meta`  (38 LOC)
- `src/scistudio/core/types/text.py:52`  `Text.with_meta`  (37 LOC)

## Cluster 2 - 9 funcs, 150 LOC, avg sim=0.920

- `src/scistudio/qa/governance/core_change_guard.py:133`  `main`  (14 LOC)
- `src/scistudio/qa/governance/docs_landing.py:124`  `main`  (18 LOC)
- `src/scistudio/qa/governance/human_bypass_guard.py:182`  `main`  (14 LOC)
- `src/scistudio/qa/governance/issue_link.py:213`  `main`  (22 LOC)
- `src/scistudio/qa/governance/mod_guard.py:158`  `main`  (22 LOC)
- `src/scistudio/qa/governance/persona_policy.py:129`  `main`  (13 LOC)
- `src/scistudio/qa/governance/pr_merge_guard.py:78`  `main`  (14 LOC)
- `src/scistudio/qa/governance/sentrux_gate.py:396`  `main`  (18 LOC)
- `src/scistudio/qa/governance/weakened_ci_check.py:230`  `main`  (15 LOC)

## Cluster 3 - 4 funcs, 149 LOC, avg sim=0.909

- `src/scistudio/engine/runners/platform.py:82`  `PosixOps.terminate_tree`  (56 LOC)
- `src/scistudio/engine/runners/platform.py:139`  `PosixOps.kill_tree`  (21 LOC)
- `src/scistudio/engine/runners/platform.py:257`  `WindowsOps.terminate_tree`  (44 LOC)
- `src/scistudio/engine/runners/platform.py:302`  `WindowsOps.kill_tree`  (28 LOC)

## Cluster 4 - 5 funcs, 148 LOC, avg sim=0.915

- `src/scistudio/blocks/process/builtins/merge.py:40`  `MergeBlock.run`  (35 LOC)
- `src/scistudio/blocks/process/builtins/merge_collection.py:35`  `MergeCollection.run`  (19 LOC)
- `src/scistudio/blocks/process/builtins/slice_collection.py:37`  `SliceCollection.run`  (21 LOC)
- `src/scistudio/blocks/process/builtins/split.py:43`  `SplitBlock.run`  (52 LOC)
- `src/scistudio/blocks/process/builtins/split_collection.py:38`  `SplitCollection.run`  (21 LOC)

## Cluster 5 - 2 funcs, 144 LOC, avg sim=0.937

- `src/scistudio/blocks/app/bridge.py:281`  `_materialise_data_object`  (39 LOC)
- `src/scistudio/blocks/io/materialisation.py:184`  `materialise_to_file`  (105 LOC)

## Cluster 6 - 2 funcs, 130 LOC, avg sim=0.930

- `src/scistudio/blocks/registry.py:507`  `BlockRegistry._scan_monorepo_packages`  (78 LOC)
- `src/scistudio/core/types/registry.py:563`  `TypeRegistry._scan_monorepo_types`  (52 LOC)

## Cluster 7 - 6 funcs, 117 LOC, avg sim=0.935

- `src/scistudio/core/types/array.py:388`  `Array._reconstruct_extra_kwargs`  (20 LOC)
- `src/scistudio/core/types/artifact.py:94`  `Artifact._reconstruct_extra_kwargs`  (19 LOC)
- `src/scistudio/core/types/base.py:497`  `DataObject._reconstruct_extra_kwargs`  (29 LOC)
- `src/scistudio/core/types/dataframe.py:97`  `DataFrame._reconstruct_extra_kwargs`  (16 LOC)
- `src/scistudio/core/types/series.py:99`  `Series._reconstruct_extra_kwargs`  (15 LOC)
- `src/scistudio/core/types/text.py:93`  `Text._reconstruct_extra_kwargs`  (18 LOC)

## Cluster 8 - 2 funcs, 115 LOC, avg sim=0.921

- `src/scistudio/blocks/io/io_block.py:231`  `IOBlock.run`  (57 LOC)
- `src/scistudio/blocks/process/process_block.py:123`  `ProcessBlock.run`  (58 LOC)

## Cluster 9 - 2 funcs, 98 LOC, avg sim=0.970

- `src/scistudio/blocks/process/builtins/data_router.py:51`  `DataRouter.prepare_prompt`  (46 LOC)
- `src/scistudio/blocks/process/builtins/pair_editor.py:55`  `PairEditor.prepare_prompt`  (52 LOC)

## Cluster 10 - 9 funcs, 96 LOC, avg sim=0.989

- `src/scistudio/qa/governance/core_change_guard.py:37`  `_source_sha`  (12 LOC)
- `src/scistudio/qa/governance/docs_landing.py:29`  `_source_sha`  (12 LOC)
- `src/scistudio/qa/governance/human_bypass_guard.py:30`  `_source_sha`  (12 LOC)
- `src/scistudio/qa/governance/issue_link.py:53`  `_source_sha`  (12 LOC)
- `src/scistudio/qa/governance/mod_guard.py:39`  `_source_sha`  (5 LOC)
- `src/scistudio/qa/governance/persona_policy.py:25`  `_source_sha`  (12 LOC)
- `src/scistudio/qa/governance/pr_merge_guard.py:19`  `_source_sha`  (12 LOC)
- `src/scistudio/qa/governance/sentrux_gate.py:111`  `_source_sha`  (14 LOC)
- `src/scistudio/qa/governance/weakened_ci_check.py:78`  `_source_sha`  (5 LOC)

## Cluster 11 - 2 funcs, 96 LOC, avg sim=0.924

- `src/scistudio/blocks/code/runners/julia_runner.py:73`  `JuliaRunner.execute_script`  (47 LOC)
- `src/scistudio/blocks/code/runners/r_runner.py:68`  `RRunner.execute_script`  (49 LOC)

## Cluster 12 - 2 funcs, 93 LOC, avg sim=0.942

- `src/scistudio/blocks/code/runners/julia_runner.py:23`  `JuliaRunner.execute_inline`  (49 LOC)
- `src/scistudio/blocks/code/runners/r_runner.py:23`  `RRunner.execute_inline`  (44 LOC)

## Cluster 13 - 3 funcs, 79 LOC, avg sim=0.954

- `src/scistudio/blocks/io/io_block.py:94`  `IOBlock.get_format_capabilities`  (41 LOC)
- `src/scistudio/blocks/io/simple_io.py:73`  `SimpleLoader.get_format_capabilities`  (19 LOC)
- `src/scistudio/blocks/io/simple_io.py:115`  `SimpleSaver.get_format_capabilities`  (19 LOC)

## Cluster 14 - 4 funcs, 78 LOC, avg sim=0.934

- `src/scistudio/qa/audit/frontmatter_lint.py:81`  `_load_adr_addendum_frontmatter`  (23 LOC)
- `src/scistudio/qa/audit/loaders.py:30`  `load_adr_frontmatter`  (10 LOC)
- `src/scistudio/qa/audit/loaders.py:42`  `load_adr_addendum_frontmatter`  (13 LOC)
- `src/scistudio/qa/audit/_util.py:243`  `load_adr_frontmatter`  (32 LOC)

## Cluster 15 - 4 funcs, 78 LOC, avg sim=0.923

- `src/scistudio/core/types/base.py:528`  `DataObject._serialise_extra_metadata`  (26 LOC)
- `src/scistudio/core/types/dataframe.py:115`  `DataFrame._serialise_extra_metadata`  (18 LOC)
- `src/scistudio/core/types/series.py:116`  `Series._serialise_extra_metadata`  (17 LOC)
- `src/scistudio/core/types/text.py:113`  `Text._serialise_extra_metadata`  (17 LOC)

## Cluster 16 - 2 funcs, 77 LOC, avg sim=0.945

- `src/scistudio/blocks/ai/providers.py:118`  `AnthropicProvider.generate`  (38 LOC)
- `src/scistudio/blocks/ai/providers.py:194`  `OpenAIProvider.generate`  (39 LOC)

## Cluster 17 - 4 funcs, 74 LOC, avg sim=0.940

- `src/scistudio/blocks/code/interpreters.py:103`  `_resolve_executable`  (17 LOC)
- `src/scistudio/blocks/code/backends/notebook.py:118`  `_resolve_configured_executable`  (17 LOC)
- `src/scistudio/blocks/code/backends/r_quarto.py:119`  `_resolve_executable`  (17 LOC)
- `src/scistudio/blocks/code/backends/shell.py:92`  `_resolve_executable`  (23 LOC)

## Cluster 18 - 6 funcs, 72 LOC, avg sim=1.000

- `src/scistudio/agent_provisioning/templates/hook_deny_scistudio_cli.py:28`  `_read_payload`  (12 LOC)
- `src/scistudio/agent_provisioning/templates/hook_enforce_concrete_port_types.py:60`  `_read_payload`  (12 LOC)
- `src/scistudio/agent_provisioning/templates/hook_enforce_list_blocks_before_block_write.py:49`  `_read_payload`  (12 LOC)
- `src/scistudio/agent_provisioning/templates/hook_mark_list_blocks_called.py:23`  `_read_payload`  (12 LOC)
- `src/scistudio/agent_provisioning/templates/hook_protect_workflow_yaml.py:23`  `_read_payload`  (12 LOC)
- `src/scistudio/agent_provisioning/templates/hook_remind_poll_status.py:16`  `_read_payload`  (12 LOC)

## Cluster 19 - 6 funcs, 64 LOC, avg sim=0.974

- `src/scistudio/blocks/code/code_block.py:118`  `CodeBlockBackend.run`  (6 LOC)
- `src/scistudio/blocks/code/backends/matlab.py:57`  `MatlabCodeBlockBackend.run`  (11 LOC)
- `src/scistudio/blocks/code/backends/notebook.py:56`  `NotebookCodeBlockBackend.run`  (14 LOC)
- `src/scistudio/blocks/code/backends/python.py:35`  `PythonCodeBlockBackend.run`  (11 LOC)
- `src/scistudio/blocks/code/backends/r_quarto.py:47`  `RQuartoCodeBlockBackend.run`  (11 LOC)
- `src/scistudio/blocks/code/backends/shell.py:50`  `ShellCodeBlockBackend.run`  (11 LOC)

## Cluster 20 - 5 funcs, 59 LOC, avg sim=0.926

- `src/scistudio/qa/audit/architecture_drift.py:138`  `_finding`  (19 LOC)
- `src/scistudio/qa/audit/frontmatter_lint.py:46`  `_finding`  (8 LOC)
- `src/scistudio/qa/audit/full_audit.py:75`  `_finding`  (8 LOC)
- `src/scistudio/qa/audit/signature_drift.py:72`  `_finding`  (16 LOC)
- `src/scistudio/qa/governance/gate_record.py:420`  `_finding`  (8 LOC)

## Cluster 21 - 2 funcs, 58 LOC, avg sim=0.958

- `src/scistudio/blocks/io/loaders/load_data.py:404`  `_legacy_extension_map`  (34 LOC)
- `src/scistudio/blocks/io/savers/save_data.py:441`  `_legacy_save_extension_map`  (24 LOC)

## Cluster 22 - 2 funcs, 57 LOC, avg sim=0.951

- `src/scistudio/qa/audit/architecture_drift.py:97`  `_parameters`  (14 LOC)
- `src/scistudio/qa/audit/signature_contracts.py:35`  `_parameters`  (43 LOC)

## Cluster 23 - 2 funcs, 56 LOC, avg sim=0.955

- `src/scistudio/utils/constraints.py:142`  `has_shape`  (29 LOC)
- `src/scistudio/utils/constraints.py:173`  `has_min_shape`  (27 LOC)

## Cluster 24 - 3 funcs, 54 LOC, avg sim=0.923

- `src/scistudio/blocks/io/loaders/load_data.py:552`  `LoadData._detect_format`  (18 LOC)
- `src/scistudio/blocks/io/savers/save_data.py:480`  `_resolve_save_format`  (18 LOC)
- `src/scistudio/blocks/io/savers/save_data.py:706`  `SaveData._detect_format`  (18 LOC)

## Cluster 25 - 2 funcs, 53 LOC, avg sim=0.920

- `src/scistudio/core/lineage/store.py:486`  `LineageStore.list_block_io`  (13 LOC)
- `src/scistudio/core/lineage/store.py:500`  `LineageStore.list_block_io_with_objects`  (40 LOC)

## Cluster 26 - 5 funcs, 52 LOC, avg sim=0.956

- `src/scistudio/blocks/code/interpreters.py:133`  `_environment_delta`  (10 LOC)
- `src/scistudio/blocks/code/backends/matlab.py:188`  `environment_delta`  (12 LOC)
- `src/scistudio/blocks/code/backends/notebook.py:191`  `_environment_delta`  (10 LOC)
- `src/scistudio/blocks/code/backends/r_quarto.py:193`  `_environment_delta`  (10 LOC)
- `src/scistudio/blocks/code/backends/shell.py:155`  `_configured_environment`  (10 LOC)

## Cluster 27 - 2 funcs, 50 LOC, avg sim=0.923

- `src/scistudio/engine/checkpoint.py:43`  `serialize_intermediate_refs`  (17 LOC)
- `src/scistudio/engine/checkpoint.py:103`  `deserialize_intermediate_refs`  (33 LOC)

## Cluster 28 - 3 funcs, 48 LOC, avg sim=0.939

- `src/scistudio/blocks/code/interpreters.py:145`  `_probe_version`  (16 LOC)
- `src/scistudio/blocks/code/backends/r_quarto.py:205`  `_probe_version`  (16 LOC)
- `src/scistudio/blocks/code/backends/shell.py:167`  `_probe_shell_version`  (16 LOC)

## Cluster 29 - 2 funcs, 46 LOC, avg sim=0.999

- `src/scistudio/blocks/process/builtins/merge.py:77`  `_persist_arrow_result`  (23 LOC)
- `src/scistudio/blocks/process/builtins/split.py:97`  `_persist_arrow_result`  (23 LOC)

## Cluster 30 - 3 funcs, 44 LOC, avg sim=0.925

- `src/scistudio/blocks/code/backends/notebook.py:36`  `NotebookCodeBlockBackend.resolve`  (19 LOC)
- `src/scistudio/blocks/code/backends/python.py:26`  `PythonCodeBlockBackend.resolve`  (8 LOC)
- `src/scistudio/blocks/code/backends/shell.py:32`  `ShellCodeBlockBackend.resolve`  (17 LOC)

## Cluster 31 - 2 funcs, 42 LOC, avg sim=0.934

- `src/scistudio/blocks/code/code_block.py:473`  `_migration_diagnostics`  (16 LOC)
- `src/scistudio/blocks/code/config.py:198`  `legacy_migration_diagnostics`  (26 LOC)

## Cluster 32 - 2 funcs, 40 LOC, avg sim=0.922

- `src/scistudio/blocks/code/runners/base.py:27`  `CodeRunner.execute_script`  (9 LOC)
- `src/scistudio/blocks/code/runners/python_runner.py:54`  `PythonRunner.execute_script`  (31 LOC)

## Cluster 33 - 2 funcs, 38 LOC, avg sim=0.927

- `src/scistudio/blocks/base/block.py:109`  `Block.get_effective_input_ports`  (22 LOC)
- `src/scistudio/blocks/base/block.py:132`  `Block.get_effective_output_ports`  (16 LOC)

## Cluster 34 - 2 funcs, 37 LOC, avg sim=0.936

- `src/scistudio/qa/governance/gate_record.py:766`  `check_pre_commit`  (18 LOC)
- `src/scistudio/qa/governance/gate_record.py:786`  `check_pre_push`  (19 LOC)

## Cluster 35 - 2 funcs, 36 LOC, avg sim=0.966

- `src/scistudio/api/routes/workflows.py:313`  `cancel_workflow`  (16 LOC)
- `src/scistudio/api/routes/workflows.py:332`  `cancel_block`  (20 LOC)

## Cluster 36 - 2 funcs, 34 LOC, avg sim=0.990

- `src/scistudio/qa/governance/mod_guard.py:66`  `_local_bypass_findings`  (17 LOC)
- `src/scistudio/qa/governance/weakened_ci_check.py:157`  `_local_bypass_findings`  (17 LOC)

## Cluster 37 - 2 funcs, 33 LOC, avg sim=0.965

- `src/scistudio/agent_provisioning/claude_agents_md.py:18`  `_load_template`  (19 LOC)
- `src/scistudio/agent_provisioning/hooks.py:51`  `_load_template`  (14 LOC)

## Cluster 38 - 2 funcs, 33 LOC, avg sim=0.925

- `src/scistudio/core/storage/composite_store.py:22`  `CompositeStore._get_backend_for`  (14 LOC)
- `src/scistudio/core/types/base.py:38`  `_get_backend`  (19 LOC)

## Cluster 39 - 2 funcs, 33 LOC, avg sim=0.990

- `src/scistudio/blocks/base/block.py:240`  `Block.process_item`  (8 LOC)
- `src/scistudio/blocks/process/process_block.py:93`  `ProcessBlock.process_item`  (25 LOC)

## Cluster 40 - 2 funcs, 29 LOC, avg sim=0.969

- `src/scistudio/blocks/app/bridge.py:370`  `_resolve_core_type_param`  (8 LOC)
- `src/scistudio/blocks/io/materialisation.py:98`  `_resolve_core_type_param`  (21 LOC)

## Cluster 41 - 3 funcs, 27 LOC, avg sim=0.990

- `src/scistudio/qa/governance/core_change_guard.py:55`  `_labels`  (9 LOC)
- `src/scistudio/qa/governance/human_bypass_guard.py:44`  `_labels`  (9 LOC)
- `src/scistudio/qa/governance/pr_merge_guard.py:33`  `_labels`  (9 LOC)

## Cluster 42 - 2 funcs, 27 LOC, avg sim=0.931

- `src/scistudio/engine/runners/platform.py:161`  `PosixOps.is_alive`  (22 LOC)
- `src/scistudio/engine/runners/platform.py:331`  `WindowsOps.is_alive`  (5 LOC)

## Cluster 43 - 2 funcs, 25 LOC, avg sim=0.928

- `src/scistudio/blocks/io/io_block.py:148`  `IOBlock.load`  (18 LOC)
- `src/scistudio/blocks/io/savers/save_data.py:737`  `SaveData.load`  (7 LOC)

## Cluster 44 - 4 funcs, 24 LOC, avg sim=0.938

- `src/scistudio/qa/governance/gate_record.py:1140`  `_render_text`  (6 LOC)
- `src/scistudio/qa/governance/mod_guard.py:150`  `_render_text`  (6 LOC)
- `src/scistudio/qa/governance/sentrux_gate.py:388`  `_render_text`  (6 LOC)
- `src/scistudio/qa/governance/weakened_ci_check.py:222`  `_render_text`  (6 LOC)

## Cluster 45 - 2 funcs, 24 LOC, avg sim=0.954

- `src/scistudio/qa/schemas/frontmatter.py:199`  `SpecFrontmatter._owners_non_empty`  (12 LOC)
- `src/scistudio/qa/schemas/maintainers.py:27`  `MaintainerRule._owners_non_empty`  (12 LOC)

## Cluster 46 - 2 funcs, 24 LOC, avg sim=0.936

- `src/scistudio/blocks/code/backends/r_quarto.py:180`  `_exchange_environment`  (11 LOC)
- `src/scistudio/blocks/code/backends/shell.py:140`  `_environment_delta`  (13 LOC)

## Cluster 47 - 2 funcs, 23 LOC, avg sim=0.947

- `src/scistudio/blocks/app/bridge.py:341`  `_get_registry`  (9 LOC)
- `src/scistudio/blocks/io/materialisation.py:59`  `_get_registry`  (14 LOC)

## Cluster 48 - 2 funcs, 21 LOC, avg sim=0.941

- `src/scistudio/agent_provisioning/templates/hook_deny_scistudio_cli.py:42`  `main`  (10 LOC)
- `src/scistudio/agent_provisioning/templates/hook_protect_workflow_yaml.py:37`  `main`  (11 LOC)

## Cluster 49 - 2 funcs, 19 LOC, avg sim=0.921

- `src/scistudio/blocks/code/config.py:143`  `CodeBlockConfig.resolve_working_directory`  (10 LOC)
- `src/scistudio/blocks/code/interpreters.py:122`  `_resolve_working_directory`  (9 LOC)

## Cluster 50 - 2 funcs, 19 LOC, avg sim=0.923

- `src/scistudio/blocks/code/exchange.py:94`  `ExchangeFileRecord.to_dict`  (11 LOC)
- `src/scistudio/blocks/code/exchange.py:117`  `ExchangeDiagnostic.to_dict`  (8 LOC)

## Cluster 51 - 2 funcs, 18 LOC, avg sim=0.958

- `src/scistudio/core/metadata_store.py:146`  `MetadataStore.put_wire`  (9 LOC)
- `src/scistudio/core/metadata_store.py:156`  `MetadataStore.put_wire_if_missing`  (9 LOC)

## Cluster 52 - 2 funcs, 18 LOC, avg sim=0.920

- `src/scistudio/api/routes/workflow_watcher.py:621`  `WorkflowWatcher.mark_self_write`  (6 LOC)
- `src/scistudio/api/routes/workflow_watcher.py:685`  `mark_self_write`  (12 LOC)

## Cluster 53 - 2 funcs, 16 LOC, avg sim=0.927

- `src/scistudio/api/routes/workflows.py:291`  `pause_workflow`  (8 LOC)
- `src/scistudio/api/routes/workflows.py:302`  `resume_workflow`  (8 LOC)

## Cluster 54 - 2 funcs, 15 LOC, avg sim=0.925

- `src/scistudio/core/metadata_store.py:81`  `_set_active_lineage_store`  (8 LOC)
- `src/scistudio/core/metadata_store.py:91`  `_active_lineage_store`  (7 LOC)

## Cluster 55 - 2 funcs, 15 LOC, avg sim=0.937

- `src/scistudio/qa/governance/gate_record.py:483`  `_invalid_override_labels`  (9 LOC)
- `src/scistudio/qa/governance/human_bypass_guard.py:83`  `_invalid_override_labels`  (6 LOC)

## Cluster 56 - 2 funcs, 14 LOC, avg sim=0.943

- `src/scistudio/blocks/registry.py:874`  `BlockRegistry._resolve_capability_class`  (5 LOC)
- `src/scistudio/blocks/registry.py:880`  `BlockRegistry._resolve_first_capability_class`  (9 LOC)

## Cluster 57 - 2 funcs, 14 LOC, avg sim=1.000

- `src/scistudio/qa/audit/architecture_drift.py:84`  `_normalize`  (7 LOC)
- `src/scistudio/qa/audit/signature_drift.py:38`  `_normalize`  (7 LOC)

## Cluster 58 - 2 funcs, 12 LOC, avg sim=0.998

- `src/scistudio/qa/audit/full_audit.py:85`  `_display_path`  (5 LOC)
- `src/scistudio/qa/audit/governed.py:81`  `display_path`  (7 LOC)

## Cluster 59 - 2 funcs, 10 LOC, avg sim=0.924

- `src/scistudio/core/types/artifact.py:44`  `Artifact.get_in_memory_data`  (5 LOC)
- `src/scistudio/core/types/text.py:44`  `Text.get_in_memory_data`  (5 LOC)
