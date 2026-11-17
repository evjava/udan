import inspect
import logging
import re
import sys
from collections.abc import Mapping
from pathlib import Path
from types import UnionType
from typing import Any, Union, get_args, get_origin

from udan.core_tools_loading.api_tools import (
    DEFAULT_KIND,
    ToolKind,
    ToolMetadata,
)
from udan.core_tools_loading.api_types import ITEM_TYPE_ANY
from udan.core_tools_loading.io_fs import calc_file_hash_blake2s

logger = logging.getLogger(__name__)


def _resolve_kind(tool: dict, kinds_by_name: Mapping[str, ToolKind] | None = None) -> ToolKind:
    """Which kind a tool schema declares, from its meta and its name prefix.

    Declared `tool_type` wins, then the name prefix matched
    against the kinds' query keywords
    ("insert_diff" -> the kind whose keyword is "insert"). With neither, the kind is
    the vocabulary's default - whichever registered kind declares `is_default`, the
    package owning it decides what that is - and with no vocabulary at all the bare
    default kind, which declares no rules.

    Args:
        tool: The extracted tool schema of the function
        kinds_by_name: The kind vocabulary by name (the container's component); None
            means none is available, so every declared name becomes a bare kind

    Returns:
        The declared kind
    """
    kinds_by_name = kinds_by_name if kinds_by_name is not None else {}
    meta = tool.get("meta") or {}
    tool_type = meta.get("tool_type")
    if tool_type:
        return kinds_by_name.get(tool_type) or ToolKind(name=tool_type)

    name_pref = tool["name"].split("_", 1)[0]
    for kind in kinds_by_name.values():
        if kind.query_keyword == name_pref:
            return kind

    default = next((kind for kind in kinds_by_name.values() if kind.is_default), None)
    return default or DEFAULT_KIND


def _item_type_kwargs(kind: ToolKind, name: str, meta: dict[str, Any]) -> dict[str, str]:
    """Extract the declared item types and semantics from meta, validated against the kind.

    The allowed and required keys are the kind's own (ToolKind.item_type_keys /
    required_item_type_keys), so a plugin kind declares its item contract the same way.

    Args:
        kind: The kind the tool declares
        name: Tool name, used in the error message
        meta: Raw meta of the tool

    Returns:
        Dict with the declared 'item_type'/'output_type'/'output_semantic' kwargs for
        the kinds that promote one; empty for kinds that promote no item contract

    Raises:
        ValueError: If a key is declared that the kind cannot carry,
            e.g. `item_type` on an inserter or `output_type` on a filter, or if a key
            the kind must declare is missing, e.g. an extender without `output_type`
    """
    allowed = frozenset(kind.item_type_keys)
    if not allowed:
        return {}
    declared = {key: meta[key] for key in ("item_type", "output_type", "output_semantic") if meta.get(key) is not None}
    unexpected = sorted(set(declared) - allowed)
    if unexpected:
        raise ValueError(
            f"Tool '{name}' ({kind.name}) declares unsupported item type/semantic key(s): "
            f"{', '.join(unexpected)}. Allowed for '{kind.name}': {', '.join(sorted(allowed))}."
        )
    required = frozenset(kind.required_item_type_keys)
    missing = sorted(required - set(declared))
    if missing:
        raise ValueError(
            f"Tool '{name}' ({kind.name}) does not declare required item type key(s): "
            f"{', '.join(missing)}. Required for '{kind.name}': {', '.join(sorted(required))}."
        )
    return declared


def _annotation_item_type(annotation: object) -> str | None:
    """Item-type name declared by a type annotation, if it names one.

    A class gives its name ("dict"), a union its "|"-joined leaves without None
    ("str|Path"), and Any - the Item alias - the explicit "any". String annotations
    and parameterized generics say nothing derivable: unknown must not reject.

    Args:
        annotation: Type annotation of the tool's 'item' parameter

    Returns:
        Item-type name for meta, or None when nothing can be derived
    """
    if annotation is Any:
        return ITEM_TYPE_ANY
    if get_origin(annotation) in (Union, UnionType):
        names: list[str] = []
        for leaf in get_args(annotation):
            if leaf is type(None):
                continue
            name = _annotation_item_type(leaf)
            if name is None:
                return None
            names.append(name)
        return "|".join(names)
    if inspect.isclass(annotation):
        return annotation.__name__
    return None


def _derive_item_param_type(fn) -> str | None:
    """Derive an item contract from the annotation of the function's 'item' parameter.

    The framework injects the forest item through the 'item' parameter, so the
    parameter's declared type is the tool's item contract when meta does not
    declare one.

    Args:
        fn: Tool function

    Returns:
        Item-type name for meta, or None when the function has no annotated 'item' parameter
    """
    try:
        param = inspect.signature(fn).parameters.get("item")
    except ValueError, TypeError:
        return None
    if param is None or param.annotation is inspect.Parameter.empty:
        return None
    return _annotation_item_type(param.annotation)


def _extract_injected_args(fn) -> list[str]:
    """Extract parameter names that are injected by the framework.

    The following parameters are injected by the framework:
    - 'ctx': UdanContext, injected for inserters, filters, groupers, replacers
    - 'item': Current item, injected for filters, extenders, groupers, sorters, mappers
    - 'items': List of items, injected for non-nested replacers
    - 'nodes': List of nodes, injected for nested replacers

    The 'at_d' parameter is NOT injected - it's a user-facing parameter
    for tools like group_by_attribute/filter_by_attribute where users
    specify which attribute to use.

    Args:
        fn: The function to inspect

    Returns:
        List of parameter names that are injected
    """
    try:
        sig = inspect.signature(fn)
        injected = []
        for param_name, param in sig.parameters.items():
            # Framework-injected parameters
            # at_d is a user-facing parameter for tools
            if param_name in ("ctx", "item", "items", "nodes"):
                injected.append(param_name)
        return injected
    except ValueError, TypeError:
        return []


def _patch_operator_parameters(parameters, keeps_item_parameter: bool = False):
    """Remove 'item', 'items', 'nodes', and 'ctx' parameters from the tool schema.

    The 'item' parameter is implicitly handled by the framework
    for the filter, mapper, sorter, grouper, and extender kinds.
    The 'items' parameter is implicitly handled for the non-nested replacer kind.
    The 'nodes' parameter is implicitly handled for the nested replacer kind.
    The 'ctx' parameter is injected by the framework.
    These should not appear in the user-facing parameter schema.

    The kinds whose `item` is the declared input keep it: that is the kind's own
    `keeps_item_parameter`, read by the caller.
    """
    properties = parameters["properties"]
    required = parameters.get("required", [])
    if not keeps_item_parameter and "item" in properties:
        del properties["item"]
    if "items" in properties:
        del properties["items"]
    if "nodes" in properties:
        del properties["nodes"]
    if "ctx" in properties:
        del properties["ctx"]
    required = [arg_name for arg_name in required if arg_name not in ("item", "items", "nodes", "ctx")]
    return {"properties": properties, "required": required, "type": parameters["type"]}


_ARGS_HEADER_RE = re.compile(r"^\s*Args:\s*$")
_ARG_ENTRY_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*(?:\([^)]*\))?\s*:")

# In-memory cache of refined user-facing descriptions ("system cachable").
# Intentional module-level mutable state: keyed by module identity + function/params,
# so it never goes stale within a process (see get_user_description).
_USER_DOC_CACHE: dict[str, dict[str, str]] = {}


def _indent_of(line: str) -> int:
    return len(line) - len(line.lstrip())


def _collapse_blank_run(lines: list[str], idx: int) -> list[str]:
    """Collapse blank lines around a splice point into a single blank line.

    Args:
        lines: Line list being rebuilt
        idx: Index at which content was removed (blank runs on both sides meet here)

    Returns:
        Rebuilt line list with at most one blank line at the splice point
    """
    before = idx
    while before > 0 and not lines[before - 1].strip():
        before -= 1
    after = idx
    while after < len(lines) and not lines[after].strip():
        after += 1
    separator = [""] if before > 0 and after < len(lines) else []
    return lines[:before] + separator + lines[after:]


def _strip_hidden_args_from_doc(description: str, user_param_names: set[str]) -> str:
    """Remove 'Args:' entries for parameters that are not user-insertable.

    Parses the Google-style 'Args:' section of a docstring and drops every entry
    whose name is absent from user_param_names, together with its continuation
    lines. If no entries remain, the 'Args:' header itself is removed and
    leftover blank lines are collapsed. A docstring without an 'Args:' section
    is returned unchanged.

    Args:
        description: Raw docstring of a tool function
        user_param_names: Names of parameters visible to users (final user-facing schema)

    Returns:
        Refined description safe to show to query users
    """
    lines = description.split("\n")
    header_idx = next((i for i, line in enumerate(lines) if _ARGS_HEADER_RE.match(line)), None)
    if header_idx is None:
        return description

    header_indent = _indent_of(lines[header_idx])

    # Section ends at the next non-empty line with indent <= header indent (e.g. 'Returns:')
    end_idx = len(lines)
    for i in range(header_idx + 1, len(lines)):
        line = lines[i]
        if not line.strip():
            continue
        if _indent_of(line) <= header_indent:
            end_idx = i
            break

    section = lines[header_idx + 1 : end_idx]

    # Trailing blank lines separate the section from the next one - keep them out of entries
    trailing_blanks: list[str] = []
    while section and not section[-1].strip():
        trailing_blanks.insert(0, section.pop())

    base_indent = next((_indent_of(line) for line in section if line.strip()), header_indent + 4)

    # Group section lines into entries: an entry starts at a 'name:' line on the base
    # indent, deeper-indented lines are its continuations
    groups: list[tuple[str | None, list[str]]] = []
    for line in section:
        entry_match = _ARG_ENTRY_RE.match(line)
        if (entry_match and _indent_of(line) == base_indent) or not groups:
            groups.append((entry_match.group(1) if entry_match else None, [line]))
        else:
            groups[-1][1].append(line)

    kept_lines: list[str] = []
    has_kept_entry = False
    for name, group_lines in groups:
        if name is None:
            kept_lines.extend(group_lines)
        elif name in user_param_names:
            has_kept_entry = True
            kept_lines.extend(group_lines)

    if not has_kept_entry:
        # No user-insertable entries left - drop the 'Args:' header with the whole section
        return "\n".join(_collapse_blank_run(lines[:header_idx] + lines[end_idx:], header_idx))

    while kept_lines and not kept_lines[-1].strip():
        kept_lines.pop()
    new_lines = lines[: header_idx + 1] + kept_lines + trailing_blanks + lines[end_idx:]
    return "\n".join(new_lines)


def get_user_description(fn, description: str, user_param_names: set[str]) -> str:
    """Return the user-facing description with hidden 'Args:' entries stripped.

    The refinement is cached in-memory to avoid recomputation. The cache key is
    the identity of the module in which the function is defined (name plus file
    content hash, so a changed module recomputes), refined by the function's
    qualified name and the user-insertable parameter names (so same-process
    reloads with different injectable-type sets do not share entries).

    Args:
        fn: Function the description belongs to
        description: Raw docstring of the function
        user_param_names: Names of parameters visible to users (final user-facing schema)

    Returns:
        Refined description safe to show to query users
    """
    module = sys.modules.get(fn.__module__)
    module_file = module.__dict__.get("__file__") if module is not None else None
    if not module_file:
        # No stable module identity (e.g. dynamically created or builtin module) - compute without caching
        return _strip_hidden_args_from_doc(description, user_param_names)

    outer_key = f"{fn.__module__}:{calc_file_hash_blake2s(Path(module_file))}"
    inner_key = f"{fn.__qualname__}:{','.join(sorted(user_param_names))}"
    module_cache = _USER_DOC_CACHE.setdefault(outer_key, {})
    if inner_key not in module_cache:
        module_cache[inner_key] = _strip_hidden_args_from_doc(description, user_param_names)
    return module_cache[inner_key]


def _kind_declared_by_meta(meta: dict[str, Any], kinds_by_name: Mapping[str, ToolKind]) -> ToolKind | None:
    """Which kind a tool's meta declares through the kind's own key, if the vocabulary knows one.

    A kind may name the meta key that marks a tool as its own (its
    `detect_meta_key`), so which kind a meta declares is asked of the vocabulary, not
    read off a key the loader names itself. None when no kind's key is present: the
    tool then keeps the kind resolved from its declared `tool_type`.

    Args:
        meta: Raw meta of the tool
        kinds_by_name: The kind vocabulary by name (the container's component)

    Returns:
        The kind whose key meta carries, or None when none does
    """
    for kind in kinds_by_name.values():
        if kind.detect_meta_key is not None and meta.get(kind.detect_meta_key):
            return kind
    return None


def _convert_tool_to_metadata(
    fn, tool: dict, domain: str | None, kinds_by_name: Mapping[str, ToolKind] | None = None
) -> ToolMetadata | None:
    """Convert tool schema to tool metadata.

    Args:
        fn: The tool function
        tool: The extracted tool schema of the function
        domain: Plugin domain to qualify the name with, None for none
        kinds_by_name: The kind vocabulary by name (the container's component), used to
            resolve the declared kind; None means none is available, so every declared
            name becomes a bare kind

    Returns:
        The tool metadata, or None when the tool cannot be built in
        this installation (its kind declares no metadata class: the package declaring
        the kind is not installed); the caller drops it

    Note: kind-specific signature validation (e.g. the required 'item' parameter) is
    performed by the registry at register time, via ToolsRegistry.validate_signature.
    """
    kinds_by_name = kinds_by_name if kinds_by_name is not None else {}
    meta = tool.get("meta") or {}
    if domain:
        meta["domain"] = domain

    kind = _resolve_kind(tool, kinds_by_name)
    declared = _kind_declared_by_meta(meta, kinds_by_name)

    # The type of the injected 'item' parameter declares the item contract when meta
    # does not. One key for every kind - `item_type` - so no per-kind choice of key
    # here: a declared concrete type wins, an undeclared one and "any" say nothing.
    # A kind that does not consume items derives nothing, and the kinds
    # without a promoted field keep the contract in meta.
    if kind.derives_item_type and meta.get("item_type") in (None, ITEM_TYPE_ANY):
        derived = _derive_item_param_type(fn)
        if derived is not None:
            meta["item_type"] = derived

    # Declare variables that will be set in the branches
    tool_cls: type[ToolMetadata]
    kind_kwargs: dict[str, Any]
    tool_type: ToolKind

    # The metadata class is the kind's own declaration (metadata_cls), falling back to
    # the base class, whose fields every metadata carries. A kind whose metadata needs
    # a marker of its own declares it, the way it declares its item contract keys; the
    # keys it promotes from meta into that class are its `metadata_meta_keys`. A kind
    # detected through its own meta key (`detect_meta_key`) but carrying no metadata
    # class cannot be built here: the package declaring the kind is not installed.
    declared_cls = (declared or kind).metadata_cls
    if not (isinstance(declared_cls, type) and issubclass(declared_cls, ToolMetadata)):
        if declared is not None:
            logger.warning(
                f"Tool '{tool['name']}' declares '{declared.detect_meta_key}' but its kind "
                f"('{declared.name}') carries no metadata class: the package declaring the kind is "
                f"not installed, so the tool cannot be built. Skipping it."
            )
            return None
        tool_cls = ToolMetadata
    else:
        tool_cls = declared_cls
    kind_kwargs = dict(
        is_nested=meta.get("is_nested", False),
        dependencies=meta.get("dependencies"),
        **_item_type_kwargs(kind, tool["name"], meta),
        **{key: meta[key] for key in (declared or kind).metadata_meta_keys if meta.get(key) is not None},
    )
    tool_type = declared or kind

    # Whether 'item' stays in the schema is the kind's own law
    parameters = _patch_operator_parameters(
        tool.get("parameters", {}), keeps_item_parameter=tool_type.keeps_item_parameter
    )

    # Build common kwargs with explicit types
    common_kwargs: dict[str, Any] = {
        "name": tool["name"],
        "description": get_user_description(fn, tool.get("description") or "", set(parameters["properties"])),
        "tags": tool.get("tags", []),
        "meta": meta,
        "parameters": parameters,
        "output_schema": tool.get("output_schema", {}),
        "tool_type": tool_type,
        "fn_path": f"{fn.__module__}.{fn.__name__}",
    }

    return tool_cls(**common_kwargs, **kind_kwargs)  # type: ignore[arg-type]


# Public API exports
extract_injected_args = _extract_injected_args
patch_operator_parameters = _patch_operator_parameters
convert_tool_to_metadata = _convert_tool_to_metadata
strip_hidden_args_from_doc = _strip_hidden_args_from_doc
