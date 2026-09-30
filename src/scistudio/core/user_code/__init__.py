"""Import user code (types, blocks, panels, plots) through Python's import system.

SciStudio keeps one ordered list of user directories, the *user import path*, at
the end of ``sys.path`` in every process that runs user code, and imports every
user file by its module name. Each file is therefore one module per process and
each user data type one class, which is what lets type checks use
``isinstance`` and lets pickle find a class by name.

The public surface:

- the user import path: :func:`build_user_import_path`,
  :func:`install_user_import_path`, :func:`ensure_user_import_path`,
  :func:`installed_user_import_path`, and the environment helpers that carry
  the path to a child process (:data:`USER_IMPORT_PATH_ENV_VAR`);
- the name check every user file passes before it is imported:
  :func:`check_user_import_path` and :class:`NameRefusal`;
- the loader: :func:`load_user_module` and :class:`UserModuleLoad`;
- the forget step that makes the next import run the code on disk:
  :func:`forget_user_modules`.
"""

# Development references: ADR-056, NEW-010.

from scistudio.core.user_code.import_path import (
    USER_IMPORT_PATH_ENV_VAR,
    build_user_import_path,
    ensure_user_import_path,
    install_user_import_path,
    install_user_import_path_from_env,
    installed_user_import_path,
    parse_user_import_path,
    serialise_user_import_path,
    user_import_path_env,
    user_import_path_from_env,
)
from scistudio.core.user_code.loader import (
    UserModuleLoad,
    defined_classes,
    load_user_module,
    module_owner_dir,
    module_source_file,
)
from scistudio.core.user_code.names import NameRefusal, check_user_import_path, importable_entries
from scistudio.core.user_code.reset import evict_bytecode, forget_user_modules

__all__ = [
    "USER_IMPORT_PATH_ENV_VAR",
    "NameRefusal",
    "UserModuleLoad",
    "build_user_import_path",
    "check_user_import_path",
    "defined_classes",
    "ensure_user_import_path",
    "evict_bytecode",
    "forget_user_modules",
    "importable_entries",
    "install_user_import_path",
    "install_user_import_path_from_env",
    "installed_user_import_path",
    "load_user_module",
    "module_owner_dir",
    "module_source_file",
    "parse_user_import_path",
    "serialise_user_import_path",
    "user_import_path_env",
    "user_import_path_from_env",
]
