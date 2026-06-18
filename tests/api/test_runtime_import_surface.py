"""Import-surface preservation tests for the ``scistudio.api.runtime`` package.

Issue #1430 / umbrella #1427: the legacy ``api/runtime.py`` god-file was
split into a sub-package. These tests pin the previously-public surface
so that future restructuring cannot silently break ``from
scistudio.api.runtime import X`` callers (routes, deps, agents, tests).

Two failure modes are guarded:

1. **Symbol removed**: a previously-public name disappears from the
   package. The first test catches this.
2. **Reach-in mutation broken**: tests and ADR-038 wiring sometimes
   monkey-patch private helpers like ``_read_preview_table_from_disk``
   or ``_table_cache``. Those mutations must remain visible to the
   internal code that uses them — see the LRU-cache test in
   ``test_data.py``. The second test pins this contract.
"""

from __future__ import annotations


def test_public_symbols_importable() -> None:
    """Every previously-public name re-exports through the package root.

    The list is curated from the pre-split ``api/runtime.py`` module-level
    definitions plus every external caller's import line under
    ``src/`` and ``tests/`` (grep ``from scistudio.api.runtime import``).
    """
    from scistudio.api import runtime

    expected_symbols = {
        # Classes
        "ApiRuntime",
        "DataRecord",
        "KnownProject",
        "LogBroadcaster",
        "WorkflowRun",
        # Module attrs reached at runtime (Path is monkey-patched in tests)
        "Path",
        "logger",
        # Private helpers external callers depend on.
        # NB: the DataFrame table cache (``_get_preview_table`` & co.) and the
        # raster pipeline (``_downsample_matrix`` / ``_image_data_uri_from_matrix``
        # / ``_load_preview_matrix``) moved down into ``scistudio.previewers``
        # (ADR-048 / #1598) and are deliberately NO LONGER part of the api.runtime
        # surface — see tests/previewers/test_table_cache_surface.py.
        "_infer_type_name_from_ref",
        "_now_iso",
        "_rmtree_force",
        "_safe_parent_dir",
        "_slugify",
    }

    missing = {name for name in expected_symbols if not hasattr(runtime, name)}
    assert not missing, f"Public surface regression: {sorted(missing)} no longer importable"

    # __all__ stays the contract — duplicate-check that every expected
    # name also appears in the export list so accidental hidden symbols
    # don't show up implicitly.
    declared = set(runtime.__all__)
    undeclared = expected_symbols - declared
    assert not undeclared, f"Symbols importable but not in __all__: {sorted(undeclared)}"


def test_apiruntime_is_single_class_with_all_methods() -> None:
    """``ApiRuntime`` keeps its single-class shape after the sub-package split.

    Tests and routes call methods like ``runtime.open_project`` or
    ``runtime.start_workflow`` directly. The class-body static
    assignment pattern in ``runtime/__init__.py`` binds the free
    functions from ``_projects`` / ``_workflows`` / ``_data`` /
    ``_runs`` onto ``ApiRuntime``; this test pins the method list so a
    rename or accidental drop does not silently lose a method.
    """
    from scistudio.api.runtime import ApiRuntime

    expected_methods = {
        # __init__-time helpers
        "_configure_static_registries",
        "_bind_event_logging",
        # Project lifecycle (_projects)
        "_load_known_projects",
        "_save_known_projects",
        "refresh_block_registry",
        "refresh_type_registry",
        "_init_lineage_store",
        "_init_metadata_store",
        "create_project",
        "list_projects",
        "_load_project_from_path",
        "open_project",
        "set_mcp_port",
        "_publish_mcp_port",
        "update_project",
        "delete_project",
        "project_response",
        "require_active_project",
        "list_project_workflows",
        # Workflow I/O + upload (_workflows)
        "workflow_path",
        "save_workflow",
        "load_workflow",
        "_config_schema_for_block",
        "_relativify_node_config",
        "_absolutify_node_config",
        "delete_workflow",
        "upload_file",
        # Data catalog + preview (_data)
        "register_data_ref",
        "register_output_payload",
        "get_data_record",
        "describe_ref",
        "_resolve_record_class",
        # Workflow execution + lineage (_runs)
        "_ancestors_of",
        "checkpoint_dir_for",
        "_build_lineage_recorder",
        "_serialise_workflow_snapshot",
        "_derive_lineage_run_status",
        "_finalize_lineage_run",
        "start_workflow",
        "_log_workflow_task_failure",
        "get_run",
    }

    missing = {name for name in expected_methods if not hasattr(ApiRuntime, name)}
    assert not missing, f"ApiRuntime method-surface regression: {sorted(missing)}"
