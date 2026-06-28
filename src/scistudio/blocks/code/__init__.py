"""Public surface for authoring and running a Code Block.

Import everything from here: ``from scistudio.blocks.code import ...``. This
package provides the :class:`CodeBlock` itself, its configuration models, the
API for registering interpreter backends, the file-exchange, interpreter,
introspection, provenance, and validation helpers, and the built-in interpreter
backends (Python, notebook, R/Quarto, shell, and MATLAB/Octave).

This whole surface is **provisional**: it is usable but may still change in a
minor release. Leading-underscore names are internal and may change at any time.
"""

from __future__ import annotations

from scistudio.blocks.code._backends_registry import (
    CodeBlockBackend,
    CodeBlockRuntimeContext,
    CodeBlockTimeoutError,
    codeblock_exchange_env,
    ensure_codeblock_backends_loaded,
    list_codeblock_backends,
    register_codeblock_backend,
    resolve_codeblock_backend,
    run_codeblock_process,
    unregister_codeblock_backend,
)
from scistudio.blocks.code.backends.matlab import (
    MatlabCodeBlockBackend,
    MatlabRuntimeResolutionError,
)
from scistudio.blocks.code.backends.notebook import NotebookCodeBlockBackend
from scistudio.blocks.code.backends.python import PythonCodeBlockBackend
from scistudio.blocks.code.backends.r_quarto import RQuartoCodeBlockBackend
from scistudio.blocks.code.backends.shell import ShellCodeBlockBackend
from scistudio.blocks.code.code_block import (
    CodeBlock,
    CodeBlockExecutionError,
    CodeBlockMigrationError,
)
from scistudio.blocks.code.config import (
    CodeBlockConfig,
    CodeBlockConfigError,
    PortFileConfig,
)
from scistudio.blocks.code.exchange import (
    CodeBlockExchangeError,
    CodeBlockExchangeLayout,
    CodeBlockExchangeManifest,
    CodeBlockExchangePort,
    ExchangeDiagnostic,
    ExchangeFileRecord,
    MaterialiseAdapter,
    OutputDiscoveryResult,
    PortManifestRecord,
    ReconstructAdapter,
    allocate_port_folder,
    collect_codeblock_outputs,
    create_codeblock_exchange_layout,
    discover_declared_outputs,
    initialise_exchange_manifest,
    normalise_extension,
    plan_input_filenames,
    prepare_codeblock_exchange,
    safe_exchange_name,
)
from scistudio.blocks.code.interpreters import (
    InterpreterFamily,
    InterpreterResolutionError,
    ResolvedInterpreter,
    UnsupportedScriptExtensionError,
    resolve_script_interpreter,
)
from scistudio.blocks.code.introspect import introspect_script
from scistudio.blocks.code.lazy_list import LazyList
from scistudio.blocks.code.provenance import (
    CodeBlockProvenancePayload,
    EnvironmentSnapshot,
    ScriptProvenance,
    build_codeblock_provenance_payload,
    capture_environment_snapshot,
    capture_script_provenance,
    utc_now_iso,
)
from scistudio.blocks.code.validation import (
    CodeBlockValidationDiagnostic,
    codeblock_config_payload,
    resolve_codeblock_data_type,
    selected_codeblock_capabilities,
    validate_codeblock_config,
)

# Sorted (isort-style) so the exported surface stays in a stable order.
# ``InterpreterFamily`` is a ``Literal`` type alias and cannot carry a runtime
# stability marker, but it is part of the public surface.
__all__ = [
    "CodeBlock",
    "CodeBlockBackend",
    "CodeBlockConfig",
    "CodeBlockConfigError",
    "CodeBlockExchangeError",
    "CodeBlockExchangeLayout",
    "CodeBlockExchangeManifest",
    "CodeBlockExchangePort",
    "CodeBlockExecutionError",
    "CodeBlockMigrationError",
    "CodeBlockProvenancePayload",
    "CodeBlockRuntimeContext",
    "CodeBlockTimeoutError",
    "CodeBlockValidationDiagnostic",
    "EnvironmentSnapshot",
    "ExchangeDiagnostic",
    "ExchangeFileRecord",
    "InterpreterFamily",
    "InterpreterResolutionError",
    "LazyList",
    "MaterialiseAdapter",
    "MatlabCodeBlockBackend",
    "MatlabRuntimeResolutionError",
    "NotebookCodeBlockBackend",
    "OutputDiscoveryResult",
    "PortFileConfig",
    "PortManifestRecord",
    "PythonCodeBlockBackend",
    "RQuartoCodeBlockBackend",
    "ReconstructAdapter",
    "ResolvedInterpreter",
    "ScriptProvenance",
    "ShellCodeBlockBackend",
    "UnsupportedScriptExtensionError",
    "allocate_port_folder",
    "build_codeblock_provenance_payload",
    "capture_environment_snapshot",
    "capture_script_provenance",
    "codeblock_config_payload",
    "codeblock_exchange_env",
    "collect_codeblock_outputs",
    "create_codeblock_exchange_layout",
    "discover_declared_outputs",
    "ensure_codeblock_backends_loaded",
    "initialise_exchange_manifest",
    "introspect_script",
    "list_codeblock_backends",
    "normalise_extension",
    "plan_input_filenames",
    "prepare_codeblock_exchange",
    "register_codeblock_backend",
    "resolve_codeblock_backend",
    "resolve_codeblock_data_type",
    "resolve_script_interpreter",
    "run_codeblock_process",
    "safe_exchange_name",
    "selected_codeblock_capabilities",
    "unregister_codeblock_backend",
    "utc_now_iso",
    "validate_codeblock_config",
]
