#!/usr/bin/env python3
"""Pre-commit hook to forbid global non-protected functions in src/.

The rule: a module-level ``def``/``async def`` in src/ must be protected, i.e.
its name starts with an underscore (same convention as
check-arg-in-protected-methods.py for methods). A loose public function is
module machinery; the public surface of a module is a tool, a class
method or a decorated entry point, not a bare global def.

Example violation:

    src/udan/core/utils_str.py:10: def cut_if_needed(...) - global function is not
    protected; rename it to '_cut_if_needed' or decorate it

Allowed without the underscore prefix:

1. A decorator whose dotted name matches DECORATOR_REGEXPS - such a decorator
   marks the function as intentional public surface:
   - ``annotated``            @annotated / @annotated_dependency tools
   - ``asynccontextmanager``  context-manager factories
2. A dunder name (Python protocol functions, e.g. ``__getattr__``).
3. A path matching PATH_REGEXPS_ALL - a module category whose public global
   functions are its purpose (utils_* modules are shared-helper collections,
   the names they export are what other modules import).
4. An entry in EXCLUSIONS_ADHOC - the violations that already existed when this
   hook was introduced, kept so the hook does not complain about the current
   state of the project.

EXCLUSIONS_ADHOC maps a file path to the names of its still-unprotected global
functions, or to the sentinel "ALL" to allow every public global function in
that file (used for main*.py CLI modules, whose bare entry points like
``main``/``main_io`` are the module's purpose; module categories covered by
PATH_REGEXPS_ALL are exempt outright and never appear here). Enumerated
entries are debt to be resolved, not permissions: shrink them, never grow them
(a newly added public global function still fails). When a listed function is
renamed or removed, its entry turns stale and must be deleted - stale entries
fail the
hook, same as in check-unused-api-methods.py.
"""

import ast
import re
import sys
from pathlib import Path

SRC_DIR = Path("src")

# A decorator matching any of these makes a global function intentional public
# surface, so it is allowed to keep its public name.
DECORATOR_REGEXPS: tuple[re.Pattern[str], ...] = (
    re.compile(r"annotated"),  # @annotated, @annotated_dependency - tools
    re.compile(r"asynccontextmanager"),  # @asynccontextmanager - context managers
)

# A file matching any of these is exempt outright, same as the "ALL" sentinel in
# EXCLUSIONS_ADHOC.
PATH_REGEXPS_ALL: tuple[re.Pattern[str], ...] = (
    re.compile(r"/utils_[^/]+\.py$"),  # utils_* - shared-helper collections
)

# Known unprotected global functions at the time this hook was introduced.
# Keys are repo-relative file paths; a value is either the set of still-allowed
# names or the sentinel "ALL". Debt: shrink, never grow.
EXCLUSIONS_ADHOC: dict[str, set[str] | str] = {
    "src/udan/core_tools_loading/api_annotated.py": {
        "annotated",
        "annotated_dependency",
        "get_annotated_functions",
        "get_annotated_kwargs",
        "get_dependency_providers",
        "get_function_name",
        "get_module_domain",
        "is_annotated",
        "is_plugins_only",
        "unwrap_function",
    },
    # The sqlite access the sql family shares: quote_identifier/connect_sql are
    # what the sql inserters are built on.
    "src/udan/plugins_tools_examples/plugins_sql.py": {"connect_sql", "quote_identifier"},
    "src/udan/core/api_item_types.py": {
        "accepted_item_types",
        "declared_item_type",
        "fits_chain",
        "is_item_type_accepted",
    },
    "src/udan/core_tools_loading/api_tools.py": {"validate_parameters_schema"},
    "src/udan/core_tools_loading/api_tool_kinds.py": {"get_kind_services"},
    "src/udan/core/impl_ioc.py": {"create_udan_container"},
    "src/udan/core_tools_loading/impl_utils_tools_loader.py": {"get_user_description"},
    "src/udan/core_tools_loading/io_fs.py": {
        "calc_file_hash_blake2s",
        "get_module_name_update_time",
        "get_module_update_time",
    },
    "src/udan/core_tools_loading/io_inspect.py": {"extract_injectable_types_from_modules", "get_tool_for_function"},
    "src/udan/core_tools_loading/io_modules.py": {
        # hosting servers scan packages and read DOMAIN by these names
        "get_plugin_domain",
        "scan_module_for_plugins",
    },
    "src/udan/plugins_tools_examples/plugins_json.py": {"resolve_json_path"},
    "src/udan/plugins_tools_examples/plugins_org.py": {"render_org_astchunk"},
    "src/udan/plugins_tools_examples/plugins_org_parser.py": {"parse_date", "parse_org_file"},
    # entry_key_values defines the :entries format the tables family renders.
    "src/udan/renders/plugins_tables.py": {"entry_key_values"},
    # The aggregate predicates the chain sequencing reads: the walk applies aggregates
    # as their own stage, and the parsing side reads render shapes through the same word.
    "src/udan/core/api_attributes.py": {"is_aggregate_attribute"},
    "src/udan/renders/api_renders.py": {"is_aggregate_render"},
    "src/udan/plugins_tools_examples/plugins_test_tracing.py": {"simple_calculate"},
    "src/udan/plugins_tools_examples/plugins_yaml.py": {"resolve_yaml_path"},
    "src/udan/plugins_history/impl_saved_tags.py": {"split_tags", "join_tags"},
    # Query text conventions the query family shares: the named argument token the
    # descriptor factory binds with, and the `# q:` prefix strip the text pipeline does.
    "src/udan/parsing/api_query_parser.py": {"parse_named_argument", "remove_prefix_if_needed"},
    "src/udan/parsing/impl_utils_parsing.py": {"parse_tree"},
    "src/udan/parsing/main.py": "ALL",
    "src/udan/plugins_history/plugins_history.py": {"create_saved_storage", "create_history_storage"},
    # The plugin framework (udan/decompof): the loader's and injector's module-level
    # functions are the framework's public surface; provide, decorate and make_container
    # are the container's declaration and entry point every provider and composition
    # root imports.
    "src/udan/decompof/injector.py": {"unwrap_optional"},
    "src/udan/decompof/loader.py": {
        "declared_plugin",
        "detach_plugin",
        "is_plugin",
        "load_plugin",
        "mount_plugins",
    },
    "src/udan/decompof/container.py": {"make_container"},
    "src/udan/decompof/provide.py": {"provide", "decorate"},
}


def decorator_name(decorator: ast.expr) -> str:
    """Dotted name of a decorator expression, e.g. 'annotated' or 'app.get'."""
    target = decorator.func if isinstance(decorator, ast.Call) else decorator
    return ast.unparse(target)


def is_decorated_as_public(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Check if a decorator marks the function as intentional public surface."""
    return any(rx.search(decorator_name(d)) for d in node.decorator_list for rx in DECORATOR_REGEXPS)


def unprotected_globals(file_path: str) -> list[tuple[int, str]]:
    """Find public module-level functions not marked public by a decorator.

    Exclusions are deliberately not applied here, so stale-exclusion detection
    sees the same raw set the violation check filters.

    Returns:
        List of (line_number, function_name) tuples
    """
    path = Path(file_path)

    try:
        source = path.read_text(encoding="utf-8")
    except OSError, UnicodeDecodeError:
        return []

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    violations = []

    for node in tree.body:
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        # Protected names and dunder protocol functions are allowed as-is
        if node.name.startswith("_"):
            continue
        if is_decorated_as_public(node):
            continue
        violations.append((node.lineno, node.name))

    return violations


def is_allowed_path(file_path: str) -> bool:
    """Check if the file's module category allows public globals outright."""
    return any(rx.search(file_path) for rx in PATH_REGEXPS_ALL)


def exclusion_names(allowed: set[str] | str) -> set[str] | None:
    """Names an EXCLUSIONS_ADHOC entry allows; None means the blanket "ALL"."""
    return None if allowed == "ALL" else allowed


def find_stale_exclusions() -> list[tuple[str, str]]:
    """Find exclusions whose unprotected global function no longer exists.

    Returns:
        List of (file_path, function_name) pairs to remove from EXCLUSIONS_ADHOC
    """
    stale = []

    for file_path, allowed in EXCLUSIONS_ADHOC.items():
        names = exclusion_names(allowed)
        if names is None:  # "ALL" - blanket allowance, cannot go stale
            continue
        actual = {name for _, name in unprotected_globals(file_path)}
        for name in sorted(names - actual):
            stale.append((file_path, name))

    return stale


def main() -> int:
    """Main entry point for the pre-commit hook."""
    if len(sys.argv) < 2:
        print("Usage: check-no-global-non-protected-functions.py <file1.py> [file2.py] ...")
        return 1

    exit_code = 0

    for file_path in sys.argv[1:]:
        if is_allowed_path(file_path):
            continue
        allowed = exclusion_names(EXCLUSIONS_ADHOC.get(file_path, set()))
        if allowed is None:  # "ALL" - every public global function allowed
            continue

        for line_no, name in unprotected_globals(file_path):
            if name in allowed:
                continue
            exit_code = 1
            print(
                f"{file_path}:{line_no}: global function '{name}' is not protected - "
                f"rename it to '_{name}' or decorate it (see DECORATOR_REGEXPS)"
            )

    for file_path, name in find_stale_exclusions():
        exit_code = 1
        print(f"Stale exclusion: {file_path}: '{name}' is gone - remove it from EXCLUSIONS_ADHOC")

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
