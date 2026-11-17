"""Introspection listing plugins for Udan.

``plugins_help`` is the module here: the ``help`` and ``help_list``
tools - the listing family that answers the ``?`` questions by reading the tools
registry, under its own ``help`` domain. ``help`` registers ``?`` as its
alias, so a question in a query is an ordinary application of an ordinary tool: the
sugar that rewrites question-shaped nodes into `?` applications lives in
``plugins_help_sugar``, and the per-tool docs the questions link to
(``introspect_tool``, the tool ``render_help`` reads) stay in ``plugins_system``.
"""

import inspect
from collections.abc import Callable
from typing import cast

from udan.core.api_exceptions import ExceptionWithAdvice
from udan.core.api_exec_context import ExecContextAPI
from udan.core.api_forests import Item
from udan.core.api_type_system import ForestTypeDescriptor, TypeSystemAPI
from udan.core_tools_loading.api_annotated import annotated, unwrap_function
from udan.core_tools_loading.api_tools import ToolDescriptor, ToolMetadata
from udan.core_tools_loading.api_tools_registry import ToolsRegistryAPI
from udan.core_tools_loading.api_types import Group, TypeDescriptor
from udan.plugins_tools_core.plugins_system import _format_location_path, _get_code_location, introspect_tool

DOMAIN = "help"


@annotated(
    meta={
        "tool_type": "inserter",
        "is_nested": False,
        "output_type": "tool_metadata",
        "supported_renders": ["introspect-item"],
    }
)
def help_list(
    pattern: str = "",
    tool_type: str = "",
    registry: ToolsRegistryAPI | None = None,
) -> list[dict]:
    """Return metadata for all tools as dictionaries.

    Each dictionary contains: domain, type, name, description, location (optional),
    plus item_type/output_type when declared. Entries are rendered with the
    `introspect-item` render (default, as in `?`) or raw render (for dict output).

    Args:
        pattern: Filter tools by name pattern
        tool_type: Filter by tool type (render, operator, attribute,
            or a concrete kind like inserter, parser, filter)
        registry: Tools registry (injected dependency)

    Returns:
        List of dictionaries with tool information
    """
    if registry is None:
        return []

    tools = registry.get_tools()
    results = []

    for name in tools:
        metadata = registry.get_metadata(name)

        if metadata is None:
            continue

        if not _is_canonical_name(name, metadata.name):
            continue

        display_domain, full_name = _format_tool_name(name, metadata)

        if not _matches_pattern(pattern, name, full_name, metadata):
            continue

        kind = metadata.tool_type

        if not metadata.matches_type_filter(tool_type):
            continue

        description = _format_help_description(
            metadata.description or "",
            metadata.meta.get("aliases", []),
        )

        location = _get_tool_location(metadata.name, registry)

        result_dict = {
            "domain": display_domain,
            "type": kind,
            "name": full_name,
            "description": description,
        }
        if location is not None:
            result_dict["location"] = location

        result_dict.update(_tool_item_type_fields(metadata))

        results.append(result_dict)

    return results


def _tool_item_type_fields(metadata: ToolMetadata) -> dict[str, str]:
    """Return the declared item-type contract of a tool as listing fields.

    Args:
        metadata: Metadata of the tool

    Returns:
        Dict with the declared 'item_type'/'output_type' entries, only those declared.
        Empty for renders: their `shape` meta key is the render shape
        ("item"/"children"), not an item type, so nothing is promoted for them.
    """
    declared = {
        "item_type": metadata.item_type,
        "output_type": metadata.output_type,
    }
    return {key: value for key, value in declared.items() if value is not None}


def _is_canonical_name(name: str, canonical_name: str) -> bool:
    """Check if name is the canonical name (not an alias)."""
    return name == canonical_name


def _format_tool_name(name: str, metadata: ToolMetadata) -> tuple[str, str]:
    """Format tool name with domain prefix.

    Returns:
        tuple of (display_domain, full_name)
    """
    domain = metadata.meta.get("domain", "")
    display_domain = domain or "builtins"

    if domain and domain != "builtins":
        full_name = f"{domain}.{name}"
    else:
        full_name = name

    return display_domain, full_name


def _matches_pattern(pattern: str, name: str, full_name: str, metadata: ToolMetadata) -> bool:
    """Check if tool matches the given pattern.

    Args:
        pattern: Pattern to match against name and aliases
        name: Base tool name
        full_name: Full name with domain prefix
        metadata: Tool metadata

    Returns:
        True if pattern matches or pattern is empty. The pattern's underscored
        spelling is tried after the typed one, so `ls-files` names `ls_files`
        the way the resolver's dash sugar names a written tool
    """
    if not pattern:
        return True

    aliases = metadata.meta.get("aliases", [])
    candidates = (name, full_name, *aliases)
    return any(spelling in candidate for spelling in (pattern, pattern.replace("-", "_")) for candidate in candidates)


def _get_tool_location(name: str, registry: ToolsRegistryAPI) -> str | None:
    """Get source location for a tool.

    Args:
        name: Name of the tool
        ctx: Execution context

    Returns:
        Location string or None if not available
    """
    fn = registry.get_function(name)
    if fn is not None:
        return _get_function_location(fn)
    return None


def _get_function_location(fn: Callable) -> str | None:
    """Get the source location of a function.

    Follows __wrapped__ chain to find the actual implementation, not wrappers.
    Skips decorator lines to point to the actual def/class line.

    Args:
        fn: Function to get location for

    Returns:
        Location string in format "fname:line_num", or None if not available
    """
    try:
        # Follow __wrapped__ chain to find the actual implementation
        # This skips wrapper functions to get the real source location
        actual_fn = unwrap_function(fn)

        fn_file = inspect.getfile(cast("Callable", actual_fn))
        fn_source, fn_line = inspect.getsourcelines(cast("Callable", actual_fn))

        # Skip decorator lines to find the actual def/class line
        for offset, line in enumerate(fn_source):
            stripped = line.strip()
            if stripped.startswith(("def ", "class ")):
                fn_line += offset
                break

        return f"{_format_location_path(fn_file)}:{fn_line}"
    except TypeError, OSError:
        # Function is built-in or from a compiled module
        return None


def _format_help_description(description: str, aliases: list[str]) -> str:
    """Format a tool description for introspection output.

    Args:
        description: The raw description
        aliases: List of aliases for the tool

    Returns:
        Formatted description with aliases appended if present
    """
    if aliases:
        # Extract first sentence/paragraph for description
        first_line = description.split("\n", maxsplit=1)[0].strip()
        # Remove trailing period if present
        if first_line.endswith("."):
            first_line = first_line[:-1]
        alias_str = ", ".join(aliases)
        return f"{first_line} (aliases: {alias_str})"
    else:
        # Use first sentence/paragraph for brevity
        formatted = description.split("\n", maxsplit=1)[0].strip()
        # Remove trailing period if present
        if formatted.endswith("."):
            formatted = formatted[:-1]
        return formatted


@annotated(
    meta={
        "tool_type": "replacer",
        "is_nested": True,
        "supported_renders": ["introspect-item"],
        "output_type": "tool_group",
        # The question atom is an alias of this tool: a `?` in a query resolves
        # through it (the question sugar in plugins_help_sugar emits `?`
        # nodes and answers the resolver's misses with them; the resolver
        # resolves the alias to the same function, so the descriptor keeps the
        # atom as its name)
        "aliases": ["?"],
        # This tool is chain-blind: which tools fit depends on the item types
        # built so far at its chain position, so it asks the resolver to hand
        # them over as the item_types argument (the walk reads the declaration
        # for any tool that makes it)
        "wants_item_types": True,
        # The chain this tool sits in is replaced by its own listing, so the
        # registry reports the chain as output-overriding and the walk applies nothing
        # else from it (`range 5, ?` shows the listing, not the range)
        "overrides_output": True,
    }
)
def help(
    pattern: str = "",
    tool_type: str = "",
    group: str = "domain",
    item_types: str = "",
    registry: ToolsRegistryAPI | None = None,
    type_system: TypeSystemAPI | None = None,
    ctx: ExecContextAPI | None = None,
) -> list[tuple[int, Item]]:
    """Return operator descriptors for help_list grouped by domain or type.

    This replacer replaces the chain with a nested structure that groups
    tools by their domain (default) or type: the engine runs only it,
    the chain's data source never executes. Group headers are Group items;
    tool entries are dictionaries that can be rendered with the
    `introspect-item` render (default) or raw render (for dict output).

    Args:
        pattern: Filter tools by name pattern (the type system applies it,
            see TypeSystem.suggest_tools)
        tool_type: Filter by tool type (render, operator, attribute,
            or a concrete kind like inserter, parser, filter - also applied by the
            type system; narrowing to "render" is what keeps the `:?` variant
            render-only)
        group: Group by "domain" (default) or "type"
        item_types: Comma-separated item types of the chain built so far (the bare
            `?` completions set it, see TypeSystem.annotate_introspection):
            tools that cannot sit at that position are not listed - inserters
            only fit an empty chain, everything else must declare an input type the
            chain provides
        registry: Tools registry (injected dependency)
        type_system: Source of the completions verdict - which tools fit the
            chain and pass the pattern/kind narrowing (injected dependency)
        ctx: Execution context for query-time logging (injected dependency)

    Returns:
        List of (depth, item) tuples for creating a nested forest grouped by domain or type
    """
    if registry is None:
        return []

    # A pattern that names a tool exactly asks for that tool's
    # docs, not the listing: `fs.relative_path?` shows relative_path help even
    # though relative_path_update also contains the pattern as a substring
    exact_key = _find_exactly_named_tool(pattern, registry) if pattern else None
    exact_metadata = registry.get_metadata(exact_key) if exact_key is not None else None
    if exact_metadata is not None and exact_metadata.matches_type_filter(tool_type):
        return introspect_tool(tool_name=exact_key, registry=registry)

    if type_system is None:
        raise ExceptionWithAdvice(
            "help needs the type system for the completions verdict "
            "(injected dependency missing) - run it through the query engine"
        )

    level_types = [level_type.strip() for level_type in item_types.split(",") if level_type.strip()]
    # The chain types ride the descriptor as a string (annotate_introspection);
    # rebuild the descriptor so the completions question is asked on the same
    # ftd seam as suggest_renders
    ftd = ForestTypeDescriptor(depths=[TypeDescriptor(name=level_type) for level_type in level_types])
    sections = type_system.suggest(ftd, pattern, tool_type)
    suggested = {name: metadata for entries in sections.values() for name, metadata in entries.items()}
    if not suggested and pattern:
        # Completions never answer nothing: a pattern matching nobody falls back
        # to the kind's unfiltered listing, so help still shows what exists
        sections = type_system.suggest(ftd, "", tool_type)
        suggested = {name: metadata for entries in sections.values() for name, metadata in entries.items()}
    if ctx is not None:
        total = sum(1 for name, metadata in registry.get_metadatas().items() if name == metadata.name)
        ctx.debug(f"suggesting tools for {level_types or ['no source']}: {len(suggested)} of {total} fit")

    groups: dict[str, list[dict]] = {}

    for name, metadata in suggested.items():
        # Get domain from metadata
        domain = metadata.meta.get("domain", "")
        # For display, use "builtins" for builtins domain, otherwise use the actual domain
        display_domain = domain or "builtins"

        # Format name with domain prefix (skip for builtin/default domain)
        if domain and domain != "builtins":
            full_name = f"{domain}.{name}"
        else:
            full_name = name

        kind = metadata.tool_type

        # Format description with aliases
        description = metadata.description or ""
        aliases = metadata.meta.get("aliases", [])
        formatted_description = _format_help_description(description, aliases)

        # Get code location if available
        location = None
        if hasattr(metadata, "fn_path") and metadata.fn_path:
            location = _get_code_location(metadata.fn_path)

        # Determine group key
        group_key = _get_help_group_key(kind.name, display_domain, group)

        # Add to group
        if group_key not in groups:
            groups[group_key] = []
        groups[group_key].append(
            _build_tool_item_dict(
                group_key,
                group,
                display_domain,
                kind.name,
                full_name,
                formatted_description,
                location,
            )
        )

    # Build nested structure with group headers
    results = []
    for group_key in sorted(groups.keys()):
        # Add group header
        results.append((0, _build_group_header(group_key, group)))
        # Add items in this group
        for item_dict in groups[group_key]:
            results.append((1, item_dict))

    return results


def _find_exactly_named_tool(pattern: str, registry: ToolsRegistryAPI) -> str | None:
    """Find the tool that the pattern names exactly, if there is exactly one.

    A pattern names a tool exactly when it equals its registry key, its
    domain-qualified name ("domain.name"), or one of its aliases - as typed, or
    spelled with the underscore the resolver's dash sugar writes (`ls-files`
    names `ls_files`). Substring hits do not count: "relative_path" does not
    name "relative_path_update".

    Args:
        pattern: The introspection pattern to match
        registry: Tools registry

    Returns:
        Registry key of the single exactly-named tool, None if none or several match
    """
    matches = []
    for name in registry.get_tools():
        metadata = registry.get_metadata(name)
        if metadata is None:
            continue
        # Only canonical names - an alias key would match twice (as key and as alias)
        if name != metadata.name:
            continue
        domain = metadata.meta.get("domain", "")
        full_name = f"{domain}.{name}" if domain and domain != "builtins" else name
        named = (name, full_name, *metadata.meta.get("aliases", []))
        if any(spelling in named for spelling in (pattern, pattern.replace("-", "_"))):
            matches.append(name)
    return matches[0] if len(matches) == 1 else None


def _get_help_group_key(kind: str, display_domain: str, group: str) -> str:
    """Determine the group key for a tool.

    Args:
        kind: The tool's type
        display_domain: The domain name for display
        group: The grouping parameter ("domain" or "type")

    Returns:
        The group key to use
    """
    if group == "type":
        return kind
    return display_domain


def _build_group_header(group_key: str, group: str) -> Group:
    """Build a group header item for introspection output.

    Args:
        group_key: The key for this group
        group: The grouping parameter ("domain" or "type"), used as the
            grouping descriptor identity so renders can show "domain=xxx"

    Returns:
        Group item representing a group header
    """
    return Group(key=group_key, key_descriptor=ToolDescriptor.create(group))


def _build_tool_item_dict(
    group_key: str,
    group: str,
    display_domain: str,
    kind: str,
    full_name: str,
    description: str,
    location: str | None = None,
) -> dict:
    """Build a tool item dictionary for introspection output.

    Args:
        group_key: The group key for this item
        group: The grouping parameter
        display_domain: The domain name for display
        kind: The tool type
        full_name: The full tool name
        description: The formatted description
        location: Optional code location (file:line)

    Returns:
        Dictionary representing a tool item
    """
    item_dict = {
        "domain": group_key if group == "domain" else display_domain,
        "type": group_key if group == "type" else kind,
        "name": full_name,
        "description": description,
    }
    if location:
        item_dict["location"] = location

    return item_dict
