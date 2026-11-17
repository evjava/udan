"""Public API for Udan tool types.

This module defines the public types for tools that can be used
when implementing tools or working with the tool system.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Any

from pydantic import AfterValidator, BaseModel, BeforeValidator, ConfigDict, Field


def validate_parameters_schema(parameters: dict[str, Any]):
    """Validate parameters schema.

    Args:
        parameters: Parameters schema to validate

    Returns:
        Validated parameters schema

    Raises:
        ValueError: If 'properties' not found in schema
    """
    if "properties" not in parameters:
        raise ValueError(f"Expected 'properties' in schema, but not found: {parameters}")
    return parameters


Parameters = Annotated[dict[str, Any], AfterValidator(validate_parameters_schema)]


def _as_tuple(items: tuple | dict[str, Any] | list):
    """Convert items to a tuple.

    Args:
        items: Items to convert - can be tuple, list, or dict

    Returns:
        Tuple representation of items

    Raises:
        ValueError: If items cannot be converted to tuple
    """
    if isinstance(items, tuple):
        return items
    elif isinstance(items, list):
        return tuple(items)
    elif isinstance(items, dict):
        return tuple(items.items())
    else:
        raise ValueError(f"Bad element to make tuple: {items}")


ArgsTuple = Annotated[tuple, BeforeValidator(_as_tuple)]
ArgsInput = tuple | dict[str, Any] | list[tuple[str, Any]] | None


class ToolDescriptor(BaseModel):
    """Descriptor for a tool.

    Represents a tool with its name and arguments.
    """

    model_config = ConfigDict(frozen=True)

    # maybe introduce a `type` field? instead of separate descriptor classes per kind
    name: str
    # todo fix, strdict
    # todo: the chain-step descriptor in forest and in exec-context is different stuff...
    args: ArgsTuple = ()
    # tool args. how to detangle args and tool_args
    # todo validate allowed args somehow?
    tool_args: ArgsTuple = ()

    @classmethod
    def create(cls, name: str, args: ArgsInput = None, *, tool_args: ArgsInput = None):
        """Create a ToolDescriptor.

        Args:
            name: Tool name
            args: Arguments for the tool
            tool_args: Tool arguments

        Returns:
            ToolDescriptor instance
        """
        # Convert inputs to ArgsTuple using the _as_tuple validator
        args_tuple: ArgsTuple = _as_tuple(args) if args is not None else ()
        tool_args_tuple: ArgsTuple = _as_tuple(tool_args) if tool_args is not None else ()
        return cls(name=name, args=args_tuple, tool_args=tool_args_tuple)


class KindArg(BaseModel):
    """One framework-level argument a tool kind accepts.

    The query side intercepts it by name (--on-depth=N) and the descriptor
    carries it as a tool_arg, so it appears in no tool's parameter
    schema. The kind declares it, and help shows it in the
    "<Kind> args:" section of a tool's help.
    """

    model_config = ConfigDict(frozen=True)

    name: str
    # Type shown in the help line ("integer"); empty shows the name alone
    arg_type: str = ""
    description: str = ""


class ToolKind(BaseModel):
    """One tool kind as an object, identified by its name.

    Every kind is instantiated once, in the module that owns its domain, and the
    vocabulary holding them is the `ToolKindsRegistry` component (see
    api_tools_registry), which the services fill at construction.

    The per-kind rules the framework applies are data on the kind: the item contract
    it declares, whether its function must take an `item`, which wildcard of
    `matches_type_filter` it answers to, the metadata class the loader builds and the
    query keyword that introduces it. A kind a plugin adds declares the same fields,
    so the framework runs it with no core change; a kind carrying no rules (a bare
    one, built from a name alone) is generic.

    Equality and hashing are by name: a kind is its name, whatever is attached to it,
    and a kind compares equal to its name - so code that only knows the string form (a
    query, an external tool's meta) interoperates with code holding kinds.
    """

    model_config = ConfigDict(frozen=True)

    name: str
    # Which wildcard of ToolMetadata.matches_type_filter the kind answers to:
    # "attribute" matches the `attribute` filter, "operator" (the default) the
    # `operator` wildcard. Any other group is legal - it just never matches a
    # wildcard, only the exact-kind filter.
    filter_group: str = "operator"
    # Metadata class the loader builds for the kind. None keeps the loader's default,
    # the base ToolMetadata - a kind whose metadata needs more than the base
    # declares it here via `metadata_cls`; that is the mechanism, not a special case.
    # Typed as BaseModel rather than ToolMetadata because that class is defined
    # below this one: a forward reference would leave this model's schema incomplete,
    # and no instance of it could be built in this module.
    metadata_cls: type[BaseModel] | None = None
    # Meta keys the loader promotes into the metadata constructor for a kind that
    # declares metadata_cls. Empty for kinds whose metadata is built from the
    # `@annotated(meta=...)` keys alone.
    metadata_meta_keys: tuple[str, ...] = ()
    # Meta key whose presence in a tool's meta declares it this kind, so the
    # loader recognizes the kind without naming the key itself. None for kinds declared
    # through `tool_type` alone.
    detect_meta_key: str | None = None
    # Meta item-contract keys the kind's metadata promotes from meta to typed fields.
    # Empty for kinds whose contract stays meta-only.
    item_type_keys: tuple[str, ...] = ()
    # Keys of item_type_keys the kind must declare: an extender is defined by what it
    # creates, so one without `output_type` would produce untyped items.
    required_item_type_keys: tuple[str, ...] = ()
    # Whether the kind's function must take an `item` parameter (register-time check).
    requires_item_parameter: bool = False
    # Whether the kind's item contract is about the item it consumes, so it can be
    # derived from the injected `item` annotation. False for inserters: they create
    # items instead of consuming them, so nothing is derived for them.
    derives_item_type: bool = True
    # Query keyword that introduces the kind in a query ("insert" for inserters, ...).
    # None for kinds that cannot be introduced by a query keyword (no keyword of
    # their own today).
    query_keyword: str | None = None
    # Framework-level arguments the kind accepts (--on-depth, --max-depth), shown
    # by help in the "<Kind> args:" section of a tool's help. The
    # applicators reading the tool_args back are the behavior side of this list.
    kind_args: tuple[KindArg, ...] = ()
    # Whether the kind can be used to form a query chain - a resolved Node child
    # applied in written order. True for the chain-forming kinds, the default kind
    # False for the kinds a resolver collects into its own lists instead of the
    # chain. The chain routing (see api_chain_routing) checks
    # at container build that every chain-forming kind has a handler.
    forms_chain: bool = False
    # Parameter names the framework injects into this kind's nested tools, so a
    # descriptor may leave them out of its arguments: the nested replacer receives
    # `items` and `nodes`. Empty for kinds whose tools take only their own.
    injected_args: tuple[str, ...] = ()
    # Whether the kind's tools rewrite the items of a level instead of creating,
    # appending or wrapping levels (mapper, replacer). The type descriptor answers
    # with the in-place rewrite of the deepest level, the applicator with the
    # per-level replacement.
    rewrites_items: bool = False
    # How the kind's tools change the level structure of the chain, read by the
    # type descriptor's folding: "replaces" starts the chain over with the created
    # level (an inserter), "appends" adds a level under the last one (an extender),
    # "wraps" groups the last level into one item (a grouper). Empty for a kind that
    # selects, reorders or rewrites - the level structure is unchanged.
    level_change: str = ""
    # Whether this kind's tools are the ones a chain picks its output producer from
    # when their meta declares the outputs they support; every other kind's
    # declaration is the fallback. True for the kind whose tools define the output
    # of what they produce (the replacer).
    declares_output: bool = False
    # Whether this kind is the one a tool with no declared kind resolves to.
    # Exactly one kind of the vocabulary may declare it, and the declaration belongs
    # to the package owning the kind - the loader reads it, it does not name it.
    is_default: bool = False
    # Whether the kind's `item` parameter stays in the user-facing parameter schema.
    # False for the kinds whose `item` the framework injects and hides; True for the
    # kind whose `item` is the declared input the user reads.
    keeps_item_parameter: bool = False
    # Metadata field naming what a tool of this kind is (e.g. the flavor of
    # value it computes), and the field values that say the function takes no `item`.
    # Both empty for kinds whose signature law is plain `requires_item_parameter`.
    metadata_variant_key: str | None = None
    metadata_item_free_values: tuple[str, ...] = ()
    # Meta key naming the variant of this kind's tools a name resolves to (one
    # name, one variant per variant value), or None for a kind whose names resolve
    # flat. The registry indexes the functions of such a kind per (name, variant
    # value) and resolves through the requested one.
    variant_meta_key: str | None = None

    def __eq__(self, other: object) -> bool:
        """Kinds are equal when they have the same name; a kind equals its name too."""
        if isinstance(other, ToolKind):
            return self.name == other.name
        if isinstance(other, str):
            return self.name == other
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self.name)

    def __str__(self) -> str:
        return self.name


def _coerce_kind(value: ToolKind | str | object) -> ToolKind | object:
    """Accept a kind name where a kind is expected (meta, external tools, hand-built metadata).

    Args:
        value: A kind, or a kind name

    Returns:
        The kind, or a bare kind of that name when the value is a string
    """
    if isinstance(value, str):
        return ToolKind(name=value)
    return value


DEFAULT_KIND = ToolKind(name="default")
"""The kind of last resort: what a tool with no kind resolves to when the
vocabulary names no default. It declares no rules, so the loader and the registry
treat it generically. The vocabulary's default kind - the one a tool with
no declared kind gets - is whichever registered kind declares `is_default`, and
that declaration belongs to the package owning the kind."""


def _normalize_dependencies(
    dependencies: list[str] | dict[str, str | None] | None,
) -> dict[str, str | None] | None:
    """Normalize dependencies to dict[str, str | None].

    Converts various input formats to a consistent internal representation:
    - None → None
    - ["attr1", "attr2"] → {"attr1": "attr1", "attr2": "attr2"}
    - {"param": "attr"} → {"param": "attr"}
    - {"param": <descriptor-like>} → {"param": attr_spec.name}
    - {"param": None} → {"param": None} (the resolve-per-item marker)

    Args:
        dependencies: Depends_on spec in list or dict format

    Returns:
        dict[str, str | None] or None

    Raises:
        ValueError: If dependencies type is invalid
    """
    if dependencies is None:
        return None

    if isinstance(dependencies, list):
        # ["attr1", "attr2"] → {"attr1": "attr1", "attr2": "attr2"}
        return {attr: attr for attr in dependencies}

    if isinstance(dependencies, dict):
        # {"param": "attr"} → {"param": "attr"}
        # {"param": <descriptor-like>} → {"param": attr_spec.name}
        # {"param": None} → {"param": None} (resolve-per-item marker)
        result: dict[str, str | None] = {}
        for param_name, attr_spec in dependencies.items():
            if attr_spec is None:
                # resolve-per-item marker - keep None, resolved during tool application
                result[param_name] = None
            elif isinstance(attr_spec, str):
                result[param_name] = attr_spec
            elif hasattr(attr_spec, "name"):
                result[param_name] = attr_spec.name
            else:
                raise ValueError(f"Invalid dependency spec: {attr_spec!r}. Expected str, None, or a descriptor")
        return result

    raise ValueError(f"Invalid dependencies type: {type(dependencies).__name__}. Expected list, dict, or None")


# Annotated type for the dependencies field with automatic normalization
# We use BeforeValidator to normalize before pydantic type checking
# The output type allows None values for the resolve-per-item marker
# Defined above ToolMetadata so the field annotation resolves while the
# class is built - the module needs no model_rebuild().
Dependencies = Annotated[
    dict[str, str | None] | None,
    BeforeValidator(_normalize_dependencies),
]


class ToolMetadata(BaseModel):
    """Metadata for a tool.

    Represents a tool with its name, description, tags, metadata, parameters schema,
    and output schema, plus the registration data: the function path and the type
    (see ToolKind for the allowed kinds).
    """

    model_config = ConfigDict(extra="forbid")

    name: str
    description: str = ""
    tags: list[str] = []
    meta: dict[str, Any] = Field(default_factory=dict)
    parameters: Parameters
    output_schema: dict[str, Any]

    # maybe introduce a `type` field? instead of separate descriptor classes per kind
    fn_path: str
    # The kind this tool is: an entry of the live kind vocabulary, carrying the
    # rules the framework applies to it (item contract, signature law, query keyword).
    # A kind name is accepted and wrapped into a bare kind of that name - rules come
    # from the vocabulary, which the loader reads when it builds the metadata.
    tool_type: Annotated[ToolKind, BeforeValidator(_coerce_kind)] = DEFAULT_KIND

    # Declared item-type contract, promoted from meta by the loader for the kinds that
    # declare item_type_keys (see ToolKind.item_type_keys). Every kind's
    # metadata carries the fields, so a reader of the contract never needs the kind's
    # metadata class - a kind that promotes none of them leaves them None:
    # - item_type: the item the tool CONSUMES (the default kind, and the
    #   chain kinds that select, reorder or group). A creator of items leaves it None.
    # - output_type: the item the tool CREATES (the kinds that create, append
    #   or rewrite levels). Kinds whose item contract stays in meta never promote
    #   (the output-producing ones keep their contract in meta `item_type`).
    # - output_semantic: the domain meaning of the created item, riding on
    #   output_type. The type names the Python class the item is ("dict", "int",
    #   "CommitInfo"); the semantic names what it means ("fruit") when the class alone
    #   does not say it.
    item_type: str | None = None
    output_type: str | None = None
    output_semantic: str | None = None
    # Whether the tool nests: it returns Iterable[tuple[int, Item]] and the
    # framework builds the levels it describes (a nested replacer).
    is_nested: bool = False
    # Dependency support - the tool depends on other tools' values.
    # Internal storage: dict of parameter name -> the name of the tool whose
    # value the parameter takes, or None for the resolve-per-item marker. Input
    # accepts list[str] or
    # dict[str, str | None]; a descriptor-like value is accepted at the boundary
    # and stored by name (see _normalize_dependencies). The raw user declaration
    # also rides in meta["dependencies"].
    dependencies: Dependencies = None

    def matches_type_filter(self, tool_type: str) -> bool:
        """Does this tool pass a tool_type filter?

        The kind narrowing shared by the completions surfaces: the type system
        applies it inside suggest_tools, the help listing for its
        remaining direct filters. The wildcards are answered through the kind's
        filter_group, so a plugin kind joins the wildcards by declaring a group.

        Args:
            tool_type: The filter value: "operator", "attribute",
                a concrete kind ("inserter", "extender", "filter", ...), or "" for
                no filtering

        Returns:
            True when this tool's kind matches the filter
        """
        if not tool_type:
            return True  # No filter
        # A wildcard is a filter group: the kinds in the group answer it. Anything
        # else is a concrete kind, matched by name.
        return tool_type in (self.tool_type.filter_group, self.tool_type.name)


class ToolBinding(BaseModel):
    """A tool resolved to its metadata and function.

    The one result shape of ToolsRegistryAPI.resolve(): every kind resolves to the
    same pair, so callers never need a per-kind resolve method.
    """

    model_config = ConfigDict(frozen=True)

    metadata: ToolMetadata
    fn: Callable
