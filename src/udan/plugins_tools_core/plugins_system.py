"""System configuration plugins for Udan.

Provides inserters and operators for accessing Udan configuration, vars, and the
per-tool help: ``introspect_tool`` (the docs the ``?`` listing links to) and
``render_help``. The listing that answers the ``?`` questions itself
(``help``, ``help_list``) lives in ``plugins_help``.
"""

import ast
import importlib
import inspect
import re
import sys
from pathlib import Path
from typing import Annotated, Any

from udan.core.api_config_registry import ConfigRegistryAPI
from udan.core.api_exceptions import ExceptionWithAdvice
from udan.core.api_forests import Item, Node
from udan.core.api_plugins import PluginsAPI
from udan.core.api_symbols_env import SymbolsEnvAPI
from udan.core.config import UdanConfig
from udan.core.impl_ioc import IOC
from udan.core.impl_plugins import Plugins
from udan.core_tools_loading.api_annotated import annotated, unwrap_function
from udan.core_tools_loading.api_tools import ToolKind
from udan.core_tools_loading.api_tools_registry import ToolsRegistryAPI
from udan.core_tools_loading.utils_str import cut_if_needed
from udan.decompof import Declaration

DOMAIN = "system"

# Constants
_VALUE_TRUNCATION_LENGTH = 100  # Max length for value representation in vars

# Google-style docstring sections: the "Args:" header and one of its entries
# ("name:", optionally "name (type):" or a vararg "*name:"), read the way the
# loader reads them
_DOC_ARGS_HEADER_RE = re.compile(r"^\s*Args:\s*$")
_DOC_ARG_ENTRY_RE = re.compile(r"^\s*\*{0,2}([A-Za-z_][A-Za-z0-9_]*)\s*(?:\([^)]*\))?\s*:")

# Restricted globals for keep_if_children predicate expressions
_EXPR_GLOBALS = {"__builtins__": {"any": any, "all": all, "len": len, "str": str, "int": int}}

# The udan project's root (the repo the package is developed in): a tool whose
# file sits outside it belongs to an external package, so its help location
# shows the absolute path
_UDAN_PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _child_matches(expr: str, child_item: Item) -> bool:
    """Evaluate a keep_if_children predicate for one child item (bound to c).

    Unlike peval, evaluation errors fail loud: a broken predicate silently
    keeping everything (or nothing) is exactly the mistake this operator
    must not hide.
    """
    try:
        return bool(eval(expr, _EXPR_GLOBALS, {"c": child_item}))  # noqa: S307
    except Exception as exc:
        raise ExceptionWithAdvice(
            f"keep_if_children: expression {expr!r} failed for child {child_item!r}: {exc}"
        ) from exc


def _subtree_pairs(node: Node, depth: int = 0) -> list[tuple[int, Item]]:
    """Flatten a node together with its subtree into (relative_depth, item) pairs."""
    pairs = [(depth, node.item)]
    for child in node.children:
        pairs.extend(_subtree_pairs(child, depth + 1))
    return pairs


def _section_rows(section: dict) -> list[tuple[int, str]]:
    """Format one config section as (depth, "key: value") rows.

    env_file is ConfigBaseSettings bookkeeping (which .env was read), not a
    knob a user can configure - skip it in the view.
    """
    return [(1, f"{key}: {section[key]}") for key in sorted(section) if key != "env_file"]


@annotated(meta={"tool_type": "inserter", "is_nested": True, "output_type": "str"})
def udan_config(
    config: UdanConfig | None = None,
    config_registry: ConfigRegistryAPI | None = None,
) -> list[tuple[int, str]]:
    """Insert the full udan configuration grouped by owner.

    Depth 0 items are section owners: "core" first, then one entry per
    installed plugin that declares a CONFIG schema, sorted by name.
    Depth 1 items are that section's "<key>: <value>" lines, so textual
    filters (grep, grepv) keep working per line.

    Plugin sections come from the config registry: a plugin module declares
    CONFIG (its own ConfigBaseSettings subclass, validated with unknown-key
    errors) and DOMAIN; the section name is the plugin DOMAIN. Values are
    read from the environment with pydantic-settings precedence
    (init kwargs > env vars > .env > defaults) - the same values the plugin's
    own providers use. Plugins without a CONFIG declaration have no section.

    Args:
        config: Core configuration (injected dependency)
        config_registry: Plugin config registry (injected dependency)

    Returns:
        List of (depth, "key: value") tuples for nested forest insertion

    Examples:
        >>> udan_config
        - core
            - udan_cache_dir: ~/.local/share/udan
            - udan_vars_path: .udan/vars.env
        - history
            - saved_path: .udan/saved.db
            - path: .udan/history.db

        >>> udan_config, grepv cache
        - core
    """
    rows: list[tuple[int, str]] = []
    if config is not None:
        rows.append((0, "core"))
        rows.extend(_section_rows(config.model_dump()))

    if config_registry is not None:
        for name in config_registry.names():
            rows.append((0, name))
            rows.extend(_section_rows(config_registry.get(name).model_dump()))

    return rows


def _short_name(cls: type) -> str:
    """Short human-readable name for an IOC component type."""
    return cls.__name__.replace("API", "").replace("Udan", "").replace("Impl", "")


def _provider_classes(plugins: PluginsAPI | None = None) -> list[type]:
    """The provider classes the composed container is built from.

    Core's IOC plus every enabled plugin package's container contribution - the
    Plugin the package declares -
    read off the plugins snapshot the container was composed from - so the
    graph this renders is the graph a running container actually has. A call
    outside the engine (no snapshot injected) scans the default configuration
    itself.

    Args:
        plugins: The enabled packages and their declarations (injected
            dependency); None scans a default UdanConfig.

    Returns:
        The core provider class first, then each enabled package's
        contribution class
    """
    if plugins is None:
        plugins = Plugins(UdanConfig())
    contributions = [package.plugin for package in plugins.packages()]
    return [IOC, *(type(contribution) for contribution in contributions if contribution is not None)]


def _scan_plugin_imports() -> dict[str, set[str]]:
    """Scan all plugin source files for cross-plugin imports via AST.

    Returns a dict mapping every plugin short-name to the set of
    other plugins it imports. Plugins with no cross-plugin imports
    get an empty set.
    """
    dep_graph: dict[str, set[str]] = {}
    src = Path("src")
    plugin_files = (
        list(src.glob("udan/plugins_*.py"))
        + list(src.glob("udan/*/plugins_*.py"))
        + list(src.glob("udan_plugins_*/plugins_*.py"))
    )

    for f in plugin_files:
        short = f.stem.replace("plugins_", "")
        dep_graph[short] = set()
        source = f.read_text()
        tree = ast.parse(source)

        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                parts = node.module.split(".")
                if len(parts) < 2:  # noqa: PLR2004
                    continue
                # udan.plugins_xxx or udan_plugins_xxx.plugins_xxx or udan.<sub>.plugins_xxx
                if parts[0] == "udan":
                    imp_short = next(
                        (part.replace("plugins_", "") for part in reversed(parts) if part.startswith("plugins_")),
                        None,
                    )
                    if imp_short is None or imp_short == short:
                        continue
                    dep_graph[short].add(imp_short)
                elif parts[0].startswith("udan_plugins_"):
                    top = parts[0].replace("udan_plugins_", "")
                    imp_short = parts[1].replace("plugins_", "") if len(parts) > 1 else top
                    if imp_short != short:
                        dep_graph[short].add(imp_short)

    return dep_graph


@annotated(meta={"tool_type": "inserter", "is_nested": True, "output_type": "str"})
def udan_plugins_deps(ignore: Annotated[list[str], "vararg"]) -> list[tuple[int, str]]:
    """Insert plugin-to-plugin dependency graph as nested structure.

    Scans all plugin source files for cross-plugin imports via AST.
    Each plugin is emitted at depth 0, its dependencies at depth 1.
    Pipe through as_dot and as_png to visualize.

    Args:
        ignore: Plugin names to exclude (vararg, positional). Default: none.

    Returns:
        List of (depth, name) tuples for nested forest insertion

    Examples:
        udan_plugins_deps, as_dot --lr, :raw
        udan_plugins_deps, as_dot --lr, as_png
        udan_plugins_deps org, as_dot --lr, as_png
    """
    ignore_set = set(ignore) if ignore else set()
    dep_graph = _scan_plugin_imports()

    result: list[tuple[int, str]] = []
    for plugin in sorted(dep_graph):
        if plugin in ignore_set:
            continue
        result.append((0, plugin))
        for dep in sorted(dep_graph[plugin]):
            if dep not in ignore_set:
                result.append((1, dep))
    return result


@annotated(meta={"tool_type": "inserter", "is_nested": True, "output_type": "str"})
def udan_ioc_deps(ignore: Annotated[list[str], "vararg"], plugins: PluginsAPI | None = None) -> list[tuple[int, str]]:
    """Insert IOC dependency graph as nested provider→deps structure.

    Extracts the dependency graph from the IOC container definition (the
    provide declarations of the core provider and every enabled plugin's).
    Each provider is emitted at depth 0, its dependencies at depth 1.
    Pipe through as_dot and as_png to visualize.

    Args:
        ignore: Component names to exclude (vararg, positional). Default: Logger, Context, Config.
        plugins: The enabled packages and their declarations (injected dependency)

    Returns:
        List of (depth, name) tuples for nested forest insertion

    Examples:
        udan_ioc_deps, as_dot --lr, :raw
        udan_ioc_deps, as_dot --lr, as_png
        udan_ioc_deps Logger Config, as_dot --lr, as_raw
    """
    default_ignore = {"Logger", "Context", "Config"}
    ignore_set = set(ignore) if ignore else default_ignore

    result: list[tuple[int, str]] = []
    for provider_class in _provider_classes(plugins):
        for _name, declaration in sorted(provider_class.__dict__.items()):
            if not isinstance(declaration, Declaration) or declaration.is_decorator:
                continue
            p_name = _short_name(declaration.provides)
            if p_name in ignore_set:
                continue
            result.append((0, p_name))
            for dependency in declaration.parameters.values():
                d_name = _short_name(dependency)
                if d_name not in ignore_set:
                    result.append((1, d_name))
    return result


def _format_location_path(file_path: str) -> str:
    """The path a tool's help location shows.

    A file of an external package (udan-ext and any other plugin host) shows
    absolute - resolved through symlinks, so the location stays valid from any
    cwd - while a file of the udan project keeps the short cwd-relative form
    the repo's listing shows.

    Args:
        file_path: The file the function lives in, as inspect.getfile reports it

    Returns:
        The path to show in the location
    """
    fn_path = Path(file_path)
    if _UDAN_PROJECT_ROOT not in fn_path.resolve().parents:
        # External package: show where the file really is, keeping the recorded
        # spelling when that resolution names nothing on disk
        resolved = fn_path.resolve()
        return str(resolved) if resolved.exists() else str(fn_path)
    try:
        return str(fn_path.relative_to(Path.cwd()))
    except ValueError:
        return str(fn_path)


def _get_code_location(fn_path: str) -> str | None:
    """Get file path and line number for a function path.

    Args:
        fn_path: Function path in format "module.submodule:function_name" or "module.submodule.function_name"

    Returns:
        String in format "path/to/file.py:line" or None if not found
    """
    try:
        # Add src to path if needed
        if "src" not in sys.path:
            sys.path.insert(0, "src")

        # Parse the function path - supports both ":" and "." separators
        if ":" in fn_path:
            # Format: "module.submodule:function_name"
            module_path, func_name = fn_path.split(":", 1)
        else:
            # Format: "module.submodule.function_name"
            # Split by "." and take everything except the last as module path
            parts = fn_path.split(".")
            func_name = parts[-1]
            module_path = ".".join(parts[:-1])

        module = importlib.import_module(module_path)

        if hasattr(module, func_name):
            func = getattr(module, func_name)

            # Unwrap the function to get the original definition
            # The @annotated decorator wraps functions, so we need to unwrap
            func = unwrap_function(func)

            file_path = inspect.getfile(func)
            line_number = inspect.getsourcelines(func)[1]

            return f"{_format_location_path(file_path)}:{line_number}"
    except Exception:
        pass

    return None


@annotated(meta={"tool_type": "replacer", "is_nested": True, "overrides_output": True})
def introspect_tool(tool_name: str, registry: ToolsRegistryAPI | None = None) -> list[tuple[int, str]]:
    """Return metadata for a specific tool as a pretty formatted forest.

    Shows the tool's description, then its parameters and the framework
    arguments of its kind:
    - Level 0 (depth 0): "{name} ({type})"
    - Level 1 (depth 1): the description, whose "Args:" section documents the
      parameters - a parameter it documents gets no further line
    - Level 1 (depth 1): "{name}: {type}! :: {description}" for a parameter the
      description does not document (with ! if required)
    - Level 1 (depth 1): the description's continuation block "{Kind} args:" with
      one indented "name: type :: description" line per framework argument the
      kind accepts ("on_depth", "max_depth") - only when the kind declares any

    Args:
        registry: Tools registry (injected dependency)
        tool_name: Name of the tool to introspect

    Returns:
        List of (depth, string) tuples for creating a nested forest
    """
    if registry is None:
        raise ExceptionWithAdvice("Registry required for introspect_tool")

    # Find the tool
    metadata = registry.get_metadata(tool_name)
    if not metadata:
        raise ExceptionWithAdvice(f"Tool '{tool_name}' not found")

    # Build nested structure
    results = []

    # Level 0: Tool info
    kind = metadata.tool_type

    # Get domain and format name with domain prefix
    domain = metadata.meta.get("domain", "")
    if domain and domain != "builtins":
        formatted_name = f"{domain}.{tool_name}"
    else:
        formatted_name = tool_name

    # Get code location if available
    location = ""
    if hasattr(metadata, "fn_path") and metadata.fn_path:
        loc = _get_code_location(metadata.fn_path)
        if loc:
            location = f" [{loc}]"

    tool_line = f"{formatted_name} ({kind}){location}"
    results.append((0, tool_line))

    # Add description
    if metadata.description:
        results.append((1, metadata.description))

    # Level 1: Parameters - only those the description does not document itself,
    # otherwise the line repeats the description's Args entry
    documented_args = _docstring_arg_names(metadata.description)
    parameters = metadata.parameters or {}
    properties = parameters.get("properties", {})
    required = set(parameters.get("required", []))

    for param_name, param_info in properties.items():
        if param_name in documented_args:
            continue

        param_type = param_info.get("type", "any")
        # Add ! to type if required
        if param_name in required:
            param_type += "!"

        # Get description
        description = param_info.get("description", "")

        # Format: "name: type! :: description"
        param_line = f"{param_name}: {param_type}"
        if description:
            param_line += f" :: {description}"

        results.append((1, param_line))

    _append_kind_args_block(results, metadata.tool_type)

    return results


def _indent_of(line: str) -> int:
    """Indentation width of a docstring line.

    Args:
        line: The line to measure

    Returns:
        Number of leading whitespace characters
    """
    return len(line) - len(line.lstrip())


def _docstring_arg_names(description: str) -> set[str]:
    """Argument names the Google-style 'Args:' section of a description documents.

    Reads the section the way the loader does (impl_utils_tools_loader):
    it ends at the next non-empty line at or below the header's indent, and an
    entry is a "name:" line at the section's base indent, the deeper-indented
    lines being its continuations.

    Args:
        description: The tool's description (its docstring)

    Returns:
        Set of documented argument names, empty when there is no Args section
    """
    lines = description.split("\n")
    header_idx = next((i for i, line in enumerate(lines) if _DOC_ARGS_HEADER_RE.match(line)), None)
    if header_idx is None:
        return set()

    header_indent = _indent_of(lines[header_idx])
    end_idx = next(
        (i for i in range(header_idx + 1, len(lines)) if lines[i].strip() and _indent_of(lines[i]) <= header_indent),
        len(lines),
    )
    section = [line for line in lines[header_idx + 1 : end_idx] if line.strip()]
    base_indent = next((_indent_of(line) for line in section), header_indent + 4)

    return {
        match.group(1)
        for line in section
        if _indent_of(line) == base_indent and (match := _DOC_ARG_ENTRY_RE.match(line)) is not None
    }


def _kind_args_block(kind: ToolKind) -> str:
    """The framework-arguments block of a kind as plain lines.

    Args:
        kind: The kind of the tool being introspected

    Returns:
        The "{Kind} args:" header followed by one indented
        "name: type :: description" line per framework argument. Empty when the
        kind declares none, so those helps stay unchanged.
    """
    if not kind.kind_args:
        return ""

    arg_lines = []
    for kind_arg in kind.kind_args:
        line = f"{kind_arg.name}: {kind_arg.arg_type}" if kind_arg.arg_type else kind_arg.name
        if kind_arg.description:
            line += f" :: {kind_arg.description}"
        arg_lines.append(f"    {line}")

    return "\n".join([f"{kind.name.capitalize()} args:", *arg_lines])


def _append_kind_args_block(results: list[tuple[int, str]], kind: ToolKind) -> None:
    """Append a kind's framework-arguments block to the help lines built so far.

    The render bullets the first line of every entry, so the block cannot be an
    entry of its own - it rides the last entry as continuation lines, which
    leaves "{Kind} args:" at the left margin like the description's sections.

    Args:
        results: The (depth, line) list built so far, mutated in place
        kind: The kind of the tool being introspected
    """
    block = _kind_args_block(kind)
    if not block:
        return

    if not results:
        results.append((1, block))
        return

    depth, last_line = results[-1]
    results[-1] = (depth, f"{last_line.rstrip(chr(10))}\n\n{block}")


@annotated(
    meta={
        "tool_type": "replacer",
        "domain": "system",
        "is_nested": True,
    }
)
def render_help(
    nodes: list[Any],
    render_name: str,
    registry: ToolsRegistryAPI | None = None,
) -> list[tuple[int, str]]:
    """Show help for a render including documentation and available columns from data.

    This operator displays:
    1. Documentation for the specified render (via introspect_tool)
    2. Available columns from the data source (extracted from dict items)

    Args:
        nodes: List of Node objects from the data source
        render_name: Name of the render to show help for
        registry: Tools registry (injected dependency)

    Returns:
        List of (depth, string) tuples with render help and available columns
    """
    if registry is None:
        raise ExceptionWithAdvice("Registry required for render_help")

    # Get render documentation
    render_docs = introspect_tool(tool_name=render_name, registry=registry)

    # Start with render docs
    results = list(render_docs)

    # Extract columns from data
    # Look for dict items in nodes and collect all unique keys
    columns: set[str] = set()
    for node in nodes:
        if hasattr(node, "item") and isinstance(node.item, dict):
            columns.update(node.item.keys())

    if columns:
        # Sort columns for consistent display
        sorted_columns = sorted(columns)
        results.append((0, ""))
        results.append((0, f"Available columns ({len(sorted_columns)}):"))
        for column in sorted_columns:
            results.append((1, column))

    return results


@annotated(meta={"tool_type": "inserter", "output_type": "str"})
def vars(symbols_env: SymbolsEnvAPI | None = None) -> list[str]:
    """Insert list of all defined variables.

    Shows all variables currently stored in the UdanContext symbol table,
    including those defined via := assignment and those loaded from .env file.

    Args:
        symbols_env: Symbol environment (injected dependency)

    Returns:
        List of variable names and their values in "name: value" format

    Example:
        >>> a := (fruits)
        >>> vars
        - a: [apple, banana, cherry]
    """
    if symbols_env is None:
        return []

    variable_names = symbols_env.list_variables()
    result = []
    for var_name in sorted(variable_names):
        var_value, _var_type = symbols_env.get_variable_with_type(var_name)
        # Format as "name: value"
        value_str = str(var_value)
        # Truncate long values
        value_str = cut_if_needed(value_str, _VALUE_TRUNCATION_LENGTH)
        result.append(f"{var_name}: {value_str}")
    return result


@annotated(meta={"tool_type": "replacer", "is_nested": True, "aliases": ["kchildren"]})
def keep_if_children(nodes: list[Node], expr: str) -> list[tuple[int, Item]]:
    """Keep nodes having at least one child satisfying expr, with their subtrees.

    Structural filter over children. It is declared a nested replacer (not a
    filter) because replacers are the only operators that receive `nodes`
    with subtrees; the decision it makes is still keep-or-drop, so kept nodes
    are re-emitted unchanged, subtree included.

    Nodes without children have no child to match and are dropped.

    Args:
        nodes: Sibling nodes with their subtrees (injected dependency)
        expr: Python expression evaluated per child; `c` is the child item

    Returns:
        List of (depth, item) tuples: kept nodes followed by their subtree items

    Examples:
        >>> range 5, multiply 3, keep_if_children "c % 6 == 0", :list
        [0, [0], 2, [6], 4, [12]]
    """
    kept: list[tuple[int, Item]] = []
    for node in nodes:
        if any(_child_matches(expr, child.item) for child in node.children):
            kept.extend(_subtree_pairs(node))
    return kept
