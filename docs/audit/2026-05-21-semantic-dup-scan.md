# Semantic duplication scan (`src\scistudio`)

- Functions scanned: 1253
- Model: `BAAI/bge-small-en-v1.5`
- Cosine threshold: `0.92`
- Min LOC: `5`
- Candidate duplicate clusters: **81**
- LOC inside duplicate clusters: **4778** / 34939 (13.7%)
- Largest cluster: **10** functions

## Cluster 1 - 7 funcs, 290 LOC, avg sim=0.973

- `src/scistudio/core/types/array.py:327`  `Array.with_meta`  (39 LOC)
- `src/scistudio/core/types/artifact.py:52`  `Artifact.with_meta`  (38 LOC)
- `src/scistudio/core/types/base.py:286`  `DataObject.with_meta`  (59 LOC)
- `src/scistudio/core/types/composite.py:96`  `CompositeData.with_meta`  (41 LOC)
- `src/scistudio/core/types/dataframe.py:55`  `DataFrame.with_meta`  (38 LOC)
- `src/scistudio/core/types/series.py:57`  `Series.with_meta`  (38 LOC)
- `src/scistudio/core/types/text.py:52`  `Text.with_meta`  (37 LOC)

## Cluster 2 - 3 funcs, 165 LOC, avg sim=0.926

- `src/scistudio/blocks/app/bridge.py:281`  `_materialise_data_object`  (39 LOC)
- `src/scistudio/blocks/app/bridge.py:406`  `_bridge_materialise_to_file`  (21 LOC)
- `src/scistudio/blocks/io/materialisation.py:184`  `materialise_to_file`  (105 LOC)

## Cluster 3 - 5 funcs, 159 LOC, avg sim=0.909

- `src/scistudio/engine/runners/platform.py:82`  `PosixOps.terminate_tree`  (56 LOC)
- `src/scistudio/engine/runners/platform.py:139`  `PosixOps.kill_tree`  (21 LOC)
- `src/scistudio/engine/runners/platform.py:257`  `WindowsOps.terminate_tree`  (44 LOC)
- `src/scistudio/engine/runners/platform.py:302`  `WindowsOps.kill_tree`  (28 LOC)
- `src/scistudio/engine/runners/process_handle.py:82`  `ProcessHandle.terminate`  (10 LOC)

## Cluster 4 - 8 funcs, 139 LOC, avg sim=0.896

- `src/scistudio/qa/audit/frontmatter_lint.py:81`  `_load_adr_addendum_frontmatter`  (23 LOC)
- `src/scistudio/qa/audit/loaders.py:30`  `load_adr_frontmatter`  (10 LOC)
- `src/scistudio/qa/audit/loaders.py:42`  `load_adr_addendum_frontmatter`  (13 LOC)
- `src/scistudio/qa/audit/loaders.py:57`  `load_spec_frontmatter`  (7 LOC)
- `src/scistudio/qa/audit/loaders.py:66`  `load_architecture_frontmatter`  (7 LOC)
- `src/scistudio/qa/audit/_util.py:243`  `load_adr_frontmatter`  (32 LOC)
- `src/scistudio/qa/audit/_util.py:277`  `load_spec_frontmatter`  (25 LOC)
- `src/scistudio/qa/audit/_util.py:304`  `load_architecture_frontmatter`  (22 LOC)

## Cluster 5 - 2 funcs, 138 LOC, avg sim=0.936

- `src/scistudio/engine/scheduler.py:1109`  `DAGScheduler._on_cancel_block`  (67 LOC)
- `src/scistudio/engine/scheduler.py:1177`  `DAGScheduler._on_cancel_workflow`  (71 LOC)

## Cluster 6 - 5 funcs, 135 LOC, avg sim=0.911

- `src/scistudio/qa/audit/signature_contracts.py:312`  `_signature_contract_facts_from_document`  (47 LOC)
- `src/scistudio/qa/audit/signature_contracts.py:361`  `extract_signature_contracts`  (29 LOC)
- `src/scistudio/qa/audit/signature_contracts.py:392`  `extract_adr_signature_contracts`  (29 LOC)
- `src/scistudio/qa/audit/signature_contracts.py:423`  `extract_governed_signature_contracts`  (19 LOC)
- `src/scistudio/qa/audit/signature_drift.py:358`  `extract_expected_signature_facts`  (11 LOC)

## Cluster 7 - 2 funcs, 130 LOC, avg sim=0.936

- `src/scistudio/blocks/registry.py:507`  `BlockRegistry._scan_monorepo_packages`  (78 LOC)
- `src/scistudio/core/types/registry.py:563`  `TypeRegistry._scan_monorepo_types`  (52 LOC)

## Cluster 8 - 2 funcs, 125 LOC, avg sim=0.937

- `src/scistudio/qa/audit/facts.py:117`  `check_generated_facts`  (87 LOC)
- `src/scistudio/qa/audit/full_audit.py:106`  `_facts_report`  (38 LOC)

## Cluster 9 - 6 funcs, 117 LOC, avg sim=0.944

- `src/scistudio/core/types/array.py:388`  `Array._reconstruct_extra_kwargs`  (20 LOC)
- `src/scistudio/core/types/artifact.py:94`  `Artifact._reconstruct_extra_kwargs`  (19 LOC)
- `src/scistudio/core/types/base.py:497`  `DataObject._reconstruct_extra_kwargs`  (29 LOC)
- `src/scistudio/core/types/dataframe.py:97`  `DataFrame._reconstruct_extra_kwargs`  (16 LOC)
- `src/scistudio/core/types/series.py:99`  `Series._reconstruct_extra_kwargs`  (15 LOC)
- `src/scistudio/core/types/text.py:93`  `Text._reconstruct_extra_kwargs`  (18 LOC)

## Cluster 10 - 10 funcs, 108 LOC, avg sim=0.979

- `src/scistudio/qa/audit/griffe_facts.py:14`  `_current_sha`  (12 LOC)
- `src/scistudio/qa/governance/core_change_guard.py:37`  `_source_sha`  (12 LOC)
- `src/scistudio/qa/governance/docs_landing.py:29`  `_source_sha`  (12 LOC)
- `src/scistudio/qa/governance/human_bypass_guard.py:30`  `_source_sha`  (12 LOC)
- `src/scistudio/qa/governance/issue_link.py:53`  `_source_sha`  (12 LOC)
- `src/scistudio/qa/governance/mod_guard.py:39`  `_source_sha`  (5 LOC)
- `src/scistudio/qa/governance/persona_policy.py:25`  `_source_sha`  (12 LOC)
- `src/scistudio/qa/governance/pr_merge_guard.py:19`  `_source_sha`  (12 LOC)
- `src/scistudio/qa/governance/sentrux_gate.py:111`  `_source_sha`  (14 LOC)
- `src/scistudio/qa/governance/weakened_ci_check.py:78`  `_source_sha`  (5 LOC)

## Cluster 11 - 2 funcs, 105 LOC, avg sim=0.927

- `src/scistudio/cli/main.py:312`  `init_block_package`  (38 LOC)
- `src/scistudio/cli/_scaffold.py:60`  `scaffold_block_package`  (67 LOC)

## Cluster 12 - 2 funcs, 98 LOC, avg sim=0.971

- `src/scistudio/blocks/process/builtins/data_router.py:51`  `DataRouter.prepare_prompt`  (46 LOC)
- `src/scistudio/blocks/process/builtins/pair_editor.py:55`  `PairEditor.prepare_prompt`  (52 LOC)

## Cluster 13 - 2 funcs, 96 LOC, avg sim=0.920

- `src/scistudio/blocks/code/runners/julia_runner.py:73`  `JuliaRunner.execute_script`  (47 LOC)
- `src/scistudio/blocks/code/runners/r_runner.py:68`  `RRunner.execute_script`  (49 LOC)

## Cluster 14 - 5 funcs, 95 LOC, avg sim=0.925

- `src/scistudio/core/types/artifact.py:115`  `Artifact._serialise_extra_metadata`  (17 LOC)
- `src/scistudio/core/types/base.py:528`  `DataObject._serialise_extra_metadata`  (26 LOC)
- `src/scistudio/core/types/dataframe.py:115`  `DataFrame._serialise_extra_metadata`  (18 LOC)
- `src/scistudio/core/types/series.py:116`  `Series._serialise_extra_metadata`  (17 LOC)
- `src/scistudio/core/types/text.py:113`  `Text._serialise_extra_metadata`  (17 LOC)

## Cluster 15 - 2 funcs, 93 LOC, avg sim=0.942

- `src/scistudio/blocks/code/runners/julia_runner.py:23`  `JuliaRunner.execute_inline`  (49 LOC)
- `src/scistudio/blocks/code/runners/r_runner.py:23`  `RRunner.execute_inline`  (44 LOC)

## Cluster 16 - 4 funcs, 91 LOC, avg sim=0.926

- `src/scistudio/blocks/io/io_block.py:198`  `IOBlock._detect_format`  (29 LOC)
- `src/scistudio/blocks/io/loaders/load_data.py:460`  `_resolve_format`  (26 LOC)
- `src/scistudio/blocks/io/loaders/load_data.py:559`  `LoadData._detect_format`  (18 LOC)
- `src/scistudio/blocks/io/savers/save_data.py:714`  `SaveData._detect_format`  (18 LOC)

## Cluster 17 - 3 funcs, 84 LOC, avg sim=0.924

- `src/scistudio/core/storage/base.py:25`  `StorageBackend.write`  (10 LOC)
- `src/scistudio/core/storage/filesystem.py:31`  `FilesystemBackend.write`  (38 LOC)
- `src/scistudio/core/storage/zarr_backend.py:25`  `ZarrBackend.write`  (36 LOC)

## Cluster 18 - 3 funcs, 84 LOC, avg sim=0.919

- `src/scistudio/api/routes/workflows.py:106`  `import_workflow`  (32 LOC)
- `src/scistudio/api/routes/workflows.py:141`  `import_workflow_from_path`  (27 LOC)
- `src/scistudio/api/routes/workflows.py:247`  `export_workflow_to_path`  (25 LOC)

## Cluster 19 - 2 funcs, 83 LOC, avg sim=0.924

- `src/scistudio/api/routes/ai_pty.py:346`  `_spawn`  (24 LOC)
- `src/scistudio/ai/agent/terminal.py:452`  `spawn_claude`  (59 LOC)

## Cluster 20 - 3 funcs, 79 LOC, avg sim=0.966

- `src/scistudio/blocks/io/io_block.py:94`  `IOBlock.get_format_capabilities`  (41 LOC)
- `src/scistudio/blocks/io/simple_io.py:73`  `SimpleLoader.get_format_capabilities`  (19 LOC)
- `src/scistudio/blocks/io/simple_io.py:115`  `SimpleSaver.get_format_capabilities`  (19 LOC)

## Cluster 21 - 3 funcs, 78 LOC, avg sim=0.917

- `src/scistudio/engine/runners/platform.py:184`  `PosixOps.get_exit_info`  (47 LOC)
- `src/scistudio/engine/runners/platform.py:337`  `WindowsOps.get_exit_info`  (25 LOC)
- `src/scistudio/engine/runners/process_handle.py:75`  `ProcessHandle.exit_info`  (6 LOC)

## Cluster 22 - 2 funcs, 77 LOC, avg sim=0.959

- `src/scistudio/blocks/ai/providers.py:118`  `AnthropicProvider.generate`  (38 LOC)
- `src/scistudio/blocks/ai/providers.py:194`  `OpenAIProvider.generate`  (39 LOC)

## Cluster 23 - 4 funcs, 74 LOC, avg sim=0.937

- `src/scistudio/blocks/code/interpreters.py:103`  `_resolve_executable`  (17 LOC)
- `src/scistudio/blocks/code/backends/notebook.py:130`  `_resolve_configured_executable`  (17 LOC)
- `src/scistudio/blocks/code/backends/r_quarto.py:119`  `_resolve_executable`  (17 LOC)
- `src/scistudio/blocks/code/backends/shell.py:92`  `_resolve_executable`  (23 LOC)

## Cluster 24 - 3 funcs, 74 LOC, avg sim=0.895

- `src/scistudio/blocks/registry.py:717`  `BlockRegistry.find_loader_capability`  (16 LOC)
- `src/scistudio/blocks/registry.py:734`  `BlockRegistry.find_saver_capability`  (16 LOC)
- `src/scistudio/blocks/io/savers/save_data.py:92`  `_save_capability`  (42 LOC)

## Cluster 25 - 2 funcs, 73 LOC, avg sim=0.921

- `src/scistudio/cli/mcp_bridge.py:185`  `_run_standalone`  (24 LOC)
- `src/scistudio/ai/agent/mcp/runtime.py:159`  `start_inprocess_server`  (49 LOC)

## Cluster 26 - 6 funcs, 72 LOC, avg sim=1.000

- `src/scistudio/agent_provisioning/templates/hook_deny_scistudio_cli.py:28`  `_read_payload`  (12 LOC)
- `src/scistudio/agent_provisioning/templates/hook_enforce_concrete_port_types.py:60`  `_read_payload`  (12 LOC)
- `src/scistudio/agent_provisioning/templates/hook_enforce_list_blocks_before_block_write.py:49`  `_read_payload`  (12 LOC)
- `src/scistudio/agent_provisioning/templates/hook_mark_list_blocks_called.py:23`  `_read_payload`  (12 LOC)
- `src/scistudio/agent_provisioning/templates/hook_protect_workflow_yaml.py:23`  `_read_payload`  (12 LOC)
- `src/scistudio/agent_provisioning/templates/hook_remind_poll_status.py:16`  `_read_payload`  (12 LOC)

## Cluster 27 - 2 funcs, 69 LOC, avg sim=0.934

- `src/scistudio/cli/install.py:133`  `_install_claude`  (38 LOC)
- `src/scistudio/cli/install.py:173`  `_remove_claude`  (31 LOC)

## Cluster 28 - 2 funcs, 65 LOC, avg sim=0.921

- `src/scistudio/api/routes/blocks.py:233`  `get_block_schema`  (33 LOC)
- `src/scistudio/ai/agent/mcp/tools_workflow.py:369`  `get_block_schema`  (32 LOC)

## Cluster 29 - 3 funcs, 64 LOC, avg sim=0.940

- `src/scistudio/qa/governance/gate_record.py:780`  `check_pre_commit`  (18 LOC)
- `src/scistudio/qa/governance/gate_record.py:800`  `check_pre_push`  (19 LOC)
- `src/scistudio/qa/governance/gate_record.py:821`  `check_pr_ready`  (27 LOC)

## Cluster 30 - 3 funcs, 61 LOC, avg sim=0.944

- `src/scistudio/blocks/process/builtins/merge_collection.py:35`  `MergeCollection.run`  (19 LOC)
- `src/scistudio/blocks/process/builtins/slice_collection.py:37`  `SliceCollection.run`  (21 LOC)
- `src/scistudio/blocks/process/builtins/split_collection.py:38`  `SplitCollection.run`  (21 LOC)

## Cluster 31 - 2 funcs, 60 LOC, avg sim=0.921

- `src/scistudio/core/metadata_store.py:266`  `MetadataStore.ancestors`  (35 LOC)
- `src/scistudio/core/metadata_store.py:302`  `MetadataStore.descendants`  (25 LOC)

## Cluster 32 - 5 funcs, 59 LOC, avg sim=0.955

- `src/scistudio/qa/audit/architecture_drift.py:138`  `_finding`  (19 LOC)
- `src/scistudio/qa/audit/frontmatter_lint.py:46`  `_finding`  (8 LOC)
- `src/scistudio/qa/audit/full_audit.py:75`  `_finding`  (8 LOC)
- `src/scistudio/qa/audit/signature_drift.py:72`  `_finding`  (16 LOC)
- `src/scistudio/qa/governance/gate_record.py:425`  `_finding`  (8 LOC)

## Cluster 33 - 2 funcs, 58 LOC, avg sim=0.970

- `src/scistudio/blocks/io/loaders/load_data.py:411`  `_legacy_extension_map`  (34 LOC)
- `src/scistudio/blocks/io/savers/save_data.py:449`  `_legacy_save_extension_map`  (24 LOC)

## Cluster 34 - 2 funcs, 57 LOC, avg sim=0.959

- `src/scistudio/qa/audit/architecture_drift.py:97`  `_parameters`  (14 LOC)
- `src/scistudio/qa/audit/signature_contracts.py:35`  `_parameters`  (43 LOC)

## Cluster 35 - 2 funcs, 56 LOC, avg sim=0.960

- `src/scistudio/utils/constraints.py:142`  `has_shape`  (29 LOC)
- `src/scistudio/utils/constraints.py:173`  `has_min_shape`  (27 LOC)

## Cluster 36 - 5 funcs, 52 LOC, avg sim=0.965

- `src/scistudio/blocks/code/interpreters.py:133`  `_environment_delta`  (10 LOC)
- `src/scistudio/blocks/code/backends/matlab.py:188`  `environment_delta`  (12 LOC)
- `src/scistudio/blocks/code/backends/notebook.py:203`  `_environment_delta`  (10 LOC)
- `src/scistudio/blocks/code/backends/r_quarto.py:193`  `_environment_delta`  (10 LOC)
- `src/scistudio/blocks/code/backends/shell.py:155`  `_configured_environment`  (10 LOC)

## Cluster 37 - 2 funcs, 50 LOC, avg sim=0.946

- `src/scistudio/engine/checkpoint.py:43`  `serialize_intermediate_refs`  (17 LOC)
- `src/scistudio/engine/checkpoint.py:103`  `deserialize_intermediate_refs`  (33 LOC)

## Cluster 38 - 3 funcs, 48 LOC, avg sim=0.939

- `src/scistudio/blocks/code/interpreters.py:145`  `_probe_version`  (16 LOC)
- `src/scistudio/blocks/code/backends/r_quarto.py:205`  `_probe_version`  (16 LOC)
- `src/scistudio/blocks/code/backends/shell.py:167`  `_probe_shell_version`  (16 LOC)

## Cluster 39 - 2 funcs, 48 LOC, avg sim=0.948

- `src/scistudio/qa/audit/facts.py:80`  `generate_facts`  (28 LOC)
- `src/scistudio/qa/audit/griffe_facts.py:139`  `generate_registry`  (20 LOC)

## Cluster 40 - 2 funcs, 46 LOC, avg sim=0.998

- `src/scistudio/blocks/process/builtins/merge.py:77`  `_persist_arrow_result`  (23 LOC)
- `src/scistudio/blocks/process/builtins/split.py:97`  `_persist_arrow_result`  (23 LOC)

## Cluster 41 - 3 funcs, 45 LOC, avg sim=0.922

- `src/scistudio/engine/scheduler.py:1428`  `DAGScheduler.cancel_block`  (9 LOC)
- `src/scistudio/api/routes/workflows.py:313`  `cancel_workflow`  (16 LOC)
- `src/scistudio/api/routes/workflows.py:332`  `cancel_block`  (20 LOC)

## Cluster 42 - 2 funcs, 45 LOC, avg sim=0.932

- `src/scistudio/blocks/io/loaders/load_data.py:735`  `_check_pickle_allowed`  (23 LOC)
- `src/scistudio/blocks/io/savers/save_data.py:522`  `_check_pickle_gate`  (22 LOC)

## Cluster 43 - 2 funcs, 42 LOC, avg sim=0.955

- `src/scistudio/blocks/code/code_block.py:473`  `_migration_diagnostics`  (16 LOC)
- `src/scistudio/blocks/code/config.py:198`  `legacy_migration_diagnostics`  (26 LOC)

## Cluster 44 - 2 funcs, 41 LOC, avg sim=0.920

- `src/scistudio/qa/governance/gate_record.py:360`  `_sentrux_applies`  (24 LOC)
- `src/scistudio/qa/governance/sentrux_gate.py:214`  `sentrux_applies_to_changes`  (17 LOC)

## Cluster 45 - 2 funcs, 40 LOC, avg sim=1.000

- `src/scistudio/blocks/code/backends/notebook.py:215`  `_resolve_existing_working_directory`  (20 LOC)
- `src/scistudio/blocks/code/backends/python.py:55`  `_resolve_existing_working_directory`  (20 LOC)

## Cluster 46 - 4 funcs, 39 LOC, avg sim=0.975

- `src/scistudio/blocks/code/code_block.py:118`  `CodeBlockBackend.run`  (6 LOC)
- `src/scistudio/blocks/code/backends/matlab.py:57`  `MatlabCodeBlockBackend.run`  (11 LOC)
- `src/scistudio/blocks/code/backends/r_quarto.py:47`  `RQuartoCodeBlockBackend.run`  (11 LOC)
- `src/scistudio/blocks/code/backends/shell.py:50`  `ShellCodeBlockBackend.run`  (11 LOC)

## Cluster 47 - 2 funcs, 37 LOC, avg sim=0.956

- `src/scistudio/qa/governance/mod_guard.py:158`  `main`  (22 LOC)
- `src/scistudio/qa/governance/weakened_ci_check.py:230`  `main`  (15 LOC)

## Cluster 48 - 3 funcs, 35 LOC, avg sim=0.921

- `src/scistudio/api/routes/workflows.py:32`  `_mark_self_write`  (17 LOC)
- `src/scistudio/api/routes/workflow_watcher.py:621`  `WorkflowWatcher.mark_self_write`  (6 LOC)
- `src/scistudio/api/routes/workflow_watcher.py:685`  `mark_self_write`  (12 LOC)

## Cluster 49 - 2 funcs, 34 LOC, avg sim=0.997

- `src/scistudio/qa/governance/mod_guard.py:66`  `_local_bypass_findings`  (17 LOC)
- `src/scistudio/qa/governance/weakened_ci_check.py:157`  `_local_bypass_findings`  (17 LOC)

## Cluster 50 - 2 funcs, 34 LOC, avg sim=0.933

- `src/scistudio/engine/runners/base.py:45`  `BlockRunner.check_status`  (14 LOC)
- `src/scistudio/engine/runners/local.py:336`  `LocalRunner.check_status`  (20 LOC)

## Cluster 51 - 2 funcs, 34 LOC, avg sim=0.931

- `src/scistudio/blocks/base/block.py:132`  `Block.get_effective_output_ports`  (16 LOC)
- `src/scistudio/blocks/io/loaders/load_data.py:578`  `LoadData.get_effective_output_ports`  (18 LOC)

## Cluster 52 - 4 funcs, 33 LOC, avg sim=0.931

- `src/scistudio/core/storage/arrow_backend.py:64`  `ArrowBackend.iter_chunks`  (5 LOC)
- `src/scistudio/core/storage/filesystem.py:88`  `FilesystemBackend.iter_chunks`  (9 LOC)
- `src/scistudio/core/storage/zarr_backend.py:70`  `ZarrBackend.iter_chunks`  (7 LOC)
- `src/scistudio/core/types/base.py:443`  `DataObject.iter_chunks`  (12 LOC)

## Cluster 53 - 3 funcs, 33 LOC, avg sim=0.926

- `src/scistudio/core/storage/arrow_backend.py:70`  `ArrowBackend.get_metadata`  (10 LOC)
- `src/scistudio/core/storage/filesystem.py:98`  `FilesystemBackend.get_metadata`  (10 LOC)
- `src/scistudio/core/storage/zarr_backend.py:83`  `ZarrBackend.get_metadata`  (13 LOC)

## Cluster 54 - 2 funcs, 33 LOC, avg sim=0.963

- `src/scistudio/agent_provisioning/claude_agents_md.py:18`  `_load_template`  (19 LOC)
- `src/scistudio/agent_provisioning/hooks.py:51`  `_load_template`  (14 LOC)

## Cluster 55 - 2 funcs, 33 LOC, avg sim=0.992

- `src/scistudio/blocks/base/block.py:240`  `Block.process_item`  (8 LOC)
- `src/scistudio/blocks/process/process_block.py:93`  `ProcessBlock.process_item`  (25 LOC)

## Cluster 56 - 2 funcs, 32 LOC, avg sim=0.927

- `src/scistudio/qa/governance/core_change_guard.py:133`  `main`  (14 LOC)
- `src/scistudio/qa/governance/docs_landing.py:124`  `main`  (18 LOC)

## Cluster 57 - 2 funcs, 31 LOC, avg sim=0.943

- `src/scistudio/api/routes/git.py:552`  `merge`  (16 LOC)
- `src/scistudio/api/routes/git.py:604`  `merge_complete`  (15 LOC)

## Cluster 58 - 2 funcs, 30 LOC, avg sim=0.938

- `src/scistudio/engine/checkpoint.py:244`  `save_checkpoint`  (21 LOC)
- `src/scistudio/engine/checkpoint.py:328`  `CheckpointManager.save`  (9 LOC)

## Cluster 59 - 2 funcs, 29 LOC, avg sim=0.951

- `src/scistudio/blocks/registry.py:1287`  `_exact_ext_in_mapping`  (15 LOC)
- `src/scistudio/blocks/registry.py:1304`  `_ext_in_mapping`  (14 LOC)

## Cluster 60 - 2 funcs, 29 LOC, avg sim=0.984

- `src/scistudio/blocks/app/bridge.py:370`  `_resolve_core_type_param`  (8 LOC)
- `src/scistudio/blocks/io/materialisation.py:98`  `_resolve_core_type_param`  (21 LOC)

## Cluster 61 - 3 funcs, 27 LOC, avg sim=0.988

- `src/scistudio/qa/governance/core_change_guard.py:55`  `_labels`  (9 LOC)
- `src/scistudio/qa/governance/human_bypass_guard.py:44`  `_labels`  (9 LOC)
- `src/scistudio/qa/governance/pr_merge_guard.py:33`  `_labels`  (9 LOC)

## Cluster 62 - 2 funcs, 27 LOC, avg sim=0.924

- `src/scistudio/qa/governance/human_bypass_guard.py:182`  `main`  (14 LOC)
- `src/scistudio/qa/governance/persona_policy.py:129`  `main`  (13 LOC)

## Cluster 63 - 2 funcs, 25 LOC, avg sim=0.924

- `src/scistudio/blocks/io/io_block.py:148`  `IOBlock.load`  (18 LOC)
- `src/scistudio/blocks/io/savers/save_data.py:745`  `SaveData.load`  (7 LOC)

## Cluster 64 - 2 funcs, 25 LOC, avg sim=0.922

- `src/scistudio/blocks/code/backends/python.py:26`  `PythonCodeBlockBackend.resolve`  (8 LOC)
- `src/scistudio/blocks/code/backends/shell.py:32`  `ShellCodeBlockBackend.resolve`  (17 LOC)

## Cluster 65 - 2 funcs, 24 LOC, avg sim=0.962

- `src/scistudio/qa/schemas/frontmatter.py:199`  `SpecFrontmatter._owners_non_empty`  (12 LOC)
- `src/scistudio/qa/schemas/maintainers.py:27`  `MaintainerRule._owners_non_empty`  (12 LOC)

## Cluster 66 - 2 funcs, 24 LOC, avg sim=0.926

- `src/scistudio/blocks/code/exchange.py:94`  `ExchangeFileRecord.to_dict`  (11 LOC)
- `src/scistudio/blocks/code/exchange.py:142`  `PortManifestRecord.to_dict`  (13 LOC)

## Cluster 67 - 2 funcs, 24 LOC, avg sim=0.934

- `src/scistudio/blocks/code/backends/r_quarto.py:180`  `_exchange_environment`  (11 LOC)
- `src/scistudio/blocks/code/backends/shell.py:140`  `_environment_delta`  (13 LOC)

## Cluster 68 - 2 funcs, 23 LOC, avg sim=0.968

- `src/scistudio/blocks/app/bridge.py:341`  `_get_registry`  (9 LOC)
- `src/scistudio/blocks/io/materialisation.py:59`  `_get_registry`  (14 LOC)

## Cluster 69 - 2 funcs, 22 LOC, avg sim=0.933

- `src/scistudio/engine/runners/base.py:60`  `BlockRunner.cancel`  (9 LOC)
- `src/scistudio/engine/runners/local.py:357`  `LocalRunner.cancel`  (13 LOC)

## Cluster 70 - 2 funcs, 22 LOC, avg sim=0.922

- `src/scistudio/blocks/code/config.py:48`  `PortFileConfig._normalize_extension`  (7 LOC)
- `src/scistudio/blocks/io/capabilities.py:50`  `normalize_extension`  (15 LOC)

## Cluster 71 - 2 funcs, 21 LOC, avg sim=0.920

- `src/scistudio/agent_provisioning/templates/hook_deny_scistudio_cli.py:42`  `main`  (10 LOC)
- `src/scistudio/agent_provisioning/templates/hook_protect_workflow_yaml.py:37`  `main`  (11 LOC)

## Cluster 72 - 2 funcs, 19 LOC, avg sim=0.926

- `src/scistudio/blocks/code/config.py:143`  `CodeBlockConfig.resolve_working_directory`  (10 LOC)
- `src/scistudio/blocks/code/interpreters.py:122`  `_resolve_working_directory`  (9 LOC)

## Cluster 73 - 2 funcs, 19 LOC, avg sim=0.929

- `src/scistudio/api/routes/ai_pty.py:641`  `_ensure_ipc_token`  (14 LOC)
- `src/scistudio/api/routes/ai_pty.py:657`  `_check_ipc_token`  (5 LOC)

## Cluster 74 - 3 funcs, 18 LOC, avg sim=0.938

- `src/scistudio/qa/governance/gate_record.py:1154`  `_render_text`  (6 LOC)
- `src/scistudio/qa/governance/mod_guard.py:150`  `_render_text`  (6 LOC)
- `src/scistudio/qa/governance/sentrux_gate.py:388`  `_render_text`  (6 LOC)

## Cluster 75 - 2 funcs, 18 LOC, avg sim=0.963

- `src/scistudio/core/metadata_store.py:146`  `MetadataStore.put_wire`  (9 LOC)
- `src/scistudio/core/metadata_store.py:156`  `MetadataStore.put_wire_if_missing`  (9 LOC)

## Cluster 76 - 2 funcs, 16 LOC, avg sim=0.933

- `src/scistudio/api/routes/workflows.py:291`  `pause_workflow`  (8 LOC)
- `src/scistudio/api/routes/workflows.py:302`  `resume_workflow`  (8 LOC)

## Cluster 77 - 2 funcs, 14 LOC, avg sim=0.966

- `src/scistudio/blocks/registry.py:896`  `BlockRegistry._resolve_capability_class`  (5 LOC)
- `src/scistudio/blocks/registry.py:902`  `BlockRegistry._resolve_first_capability_class`  (9 LOC)

## Cluster 78 - 2 funcs, 14 LOC, avg sim=1.000

- `src/scistudio/qa/audit/architecture_drift.py:84`  `_normalize`  (7 LOC)
- `src/scistudio/qa/audit/signature_drift.py:38`  `_normalize`  (7 LOC)

## Cluster 79 - 2 funcs, 12 LOC, avg sim=0.999

- `src/scistudio/qa/audit/full_audit.py:85`  `_display_path`  (5 LOC)
- `src/scistudio/qa/audit/governed.py:81`  `display_path`  (7 LOC)

## Cluster 80 - 2 funcs, 10 LOC, avg sim=0.933

- `src/scistudio/qa/governance/gate_record.py:411`  `_effective_include`  (5 LOC)
- `src/scistudio/qa/governance/gate_record.py:418`  `_effective_exclude`  (5 LOC)

## Cluster 81 - 2 funcs, 10 LOC, avg sim=0.938

- `src/scistudio/core/types/artifact.py:44`  `Artifact.get_in_memory_data`  (5 LOC)
- `src/scistudio/core/types/text.py:44`  `Text.get_in_memory_data`  (5 LOC)
