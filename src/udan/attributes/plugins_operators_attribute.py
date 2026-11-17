"""Attribute-taking operators and the column machinery.

The operators of the chain kinds that consume attribute values - a replacer that
maps items over an attribute, an extender that nests by one, a grouper and a
filter that read them - and the `cattr` column-definition attribute with its
expression machinery. They live in this package, beside the attribute kind they
are written against, and import it the way every package imports another.
"""

import ast
import operator
from collections.abc import Callable, Iterable
from datetime import datetime
from typing import Any, Literal

from udan.attributes.api_attribute_contexts import AttributesContextAPI
from udan.attributes.api_attribute_runtime import AttributeRuntimeAPI
from udan.attributes.impl_attribute_runtime import AttributesContext
from udan.core.api_attributes import (
    ATTRIBUTE,
    ATTRIBUTE_TYPE_COLUMN,
    FRAMEWORK_PARAMS_ATTR,
    AttributeDescriptor,
    AttributeMetadata,
    AttributeValue,
)
from udan.core.api_exceptions import ExceptionWithAdvice
from udan.core.api_exec_context import ExecContextAPI
from udan.core.api_forests import Item
from udan.core_tools_loading.api_annotated import annotated
from udan.core_tools_loading.api_tools_registry import ToolsRegistryAPI

# Restricted builtins available to cattr expressions (parse once, share everywhere)
_CATTR_BUILTINS = {"str": str, "int": int, "float": float, "len": len, "round": round}
_CATTR_SAFE_GLOBALS = {"__builtins__": _CATTR_BUILTINS}

_DATE_FORMAT = "%Y-%m-%d"

DOMAIN = "attributes_ops"


@annotated(meta={"attribute_type": "simple"})
def refresh_on_date(item: str) -> str:
    """Return cache key that includes item and current date.

    This attribute is used as a cache_attribute for expensive operations
    that should be refreshed daily. The cache key format is 'item:yyyy-mm-dd'.

    Args:
        item: The item to create a cache key for (typically a URL, file path, etc.)

    Returns:
        Cache key string in format 'item:yyyy-mm-dd'

    Example:
        >>> refresh_on_date("https://example.com")
        'https://example.com:2026-01-13'
    """
    today = datetime.now().strftime(_DATE_FORMAT)
    return f"{item}:{today}"


@annotated(meta={"attribute_type": "simple", "args": (("node", None),), "precalculated": True})
def origin(item: Item, node: Any = None) -> list[Any]:
    """Get the origin chain of operators that created/affected this item.

    The origin chain is a list of OperatorDescriptor objects representing all operators
    that affected the position or creation of this item, in chronological order.

    Args:
        item: The item to get the origin for
        node: Internal node object (automatically passed by the system when requested)

    Returns:
        List of OperatorDescriptor objects. Empty list for static elements.
        For items from inserters: [inserter_descriptor]
        For items in groups: [inserter_descriptor, grouper_descriptor, ...]

    Examples:
        >>> # Static item (no origin)
        origin("static")  # Returns []

        >>> # Item from inserter
        origin(file_item)  # Returns [insert_ls_files_operator_descriptor]

        >>> # Item from inserter then grouped
        origin(grouped_item)  # Returns [inserter_descriptor, grouper_descriptor]

    Note:
        The origin information is stored as an attribute during operator application,
        before the forest conversion that would otherwise lose the node's origin_chain.
        This function reads from the pre-calculated attribute storage.
    """
    # The origin is stored as an attribute value during operator application
    # Return empty list for static items or items without origin
    # Note: The actual value is set in core_operator_engine.py
    # This function is only called if the value wasn't pre-calculated
    return []


@annotated(meta={"tool_type": "replacer"})
def map_attr(
    items: list[Any],
    attr_name: str,
    attribute_runtime: AttributeRuntimeAPI | None = None,
    ctx: ExecContextAPI | None = None,
):
    """Replace each item with the value of a udan attribute.

    For each depth-0 item, extracts the specified attribute value:
    - For dicts: returns dict.get(attr_name)
    - For objects: returns getattr(item, attr_name, None)
    - For udan attributes: uses attribute_runtime if provided

    This is a simple replacer that only processes depth-0 items.

    Args:
        items: List of items to process (depth-0 only)
        attr_name: Name of the attribute or dict key to extract
        attribute_runtime: Attribute runtime for accessing udan attributes (injected if available)
        ctx: Execution context (passed by the operator engine)

    Yields:
        Attribute values, one per depth-0 input item

    Examples:
        # Extract name field from dicts
        fruits, map_attr name

        # Extract translate_ru attribute (udan attribute)
        fruits, map_attr translate_ru

        # Extract module_name attribute from paths
        ls_files src/udan, map_attr module_name
    """

    def get_attr_value(item: Item) -> Any:
        """Get attribute value for a single item."""
        # Try dict key first
        if isinstance(item, dict):
            value = item.get(attr_name)
            if value is not None:
                return value

        # Try native object attribute
        obj_value = getattr(item, attr_name, None)
        if obj_value is not None:
            return obj_value

        # Try udan attribute via attribute_runtime (requires execution context)
        if attribute_runtime is not None and ctx is not None:
            try:
                at_d = AttributeDescriptor.create(attr_name, args={})
                return attribute_runtime.get_attribute_value(at_d, item, ctx)
            except Exception:
                pass

        return None

    for item in items:
        yield get_attr_value(item)


@annotated(meta={"tool_type": "extender", "item_type": "any", "output_type": "any"})
def extend_by_attribute(  # noqa: C901, PLR0912
    item: Item,
    attr_name: str = "",
    source: str = "",
    source_prefix: str = "",
    at_d: AttributeDescriptor | None = None,
    attribute_runtime: AttributeRuntimeAPI | None = None,
    ctx: ExecContextAPI | None = None,
) -> Iterable[Any]:
    """Extend each item with its attribute value as a child.

    Computes the specified attribute for the item and yields it as a child.
    If the attribute value is None or empty string, no child is yielded.
    If the attribute returns a list, each element is yielded as a separate child.

    When ``source`` is given, first resolves that attribute to get a string,
    then passes it as ``source_value`` to the target attribute.

    When ``at_d`` is given (AttributeDescriptor), uses it directly instead of creating
    one from attr_name. This allows passing attribute arguments like (add_values 1 2).

    Args:
        item: The item to extend.
        attr_name: Name of the attribute to compute (or an AttributeDescriptor for arguments).
        source: Name of a source attribute to resolve and pass as input.
        source_prefix: Forwarded as ``prefix`` to the source attribute for filtering.
        at_d: Optional AttributeDescriptor to use directly (for attribute arguments).
        attribute_runtime: Attribute runtime (injected).
        ctx: Execution context (passed by the operator engine).

    Yields:
        Attribute value(s) as child items.

    Examples:
        ls_files src/, extend_by_attribute extract_text, :org-aggregate
        ls_files src/, extend_by_attribute file_content, :org-aggregate
        # With source and prefix:
        yaml_glob ...hooks[], extend_by_attribute parse_list --source=file_assignments --source_prefix=EXCLUSIONS
        # With attribute arguments:
        range 5, extend_by_attribute (add_values 1 2), :list
    """
    # Handle the case where attr_name is actually an AttributeDescriptor
    # (when passed as the first positional argument like (add_values 1 2))
    actual_at_d = at_d
    if isinstance(attr_name, AttributeDescriptor):
        actual_at_d = attr_name
        attr_name = ""
    elif hasattr(attr_name, "item") and isinstance(attr_name.item, AttributeDescriptor):
        actual_at_d = attr_name.item
        attr_name = ""

    # Use at_d directly if provided (for attribute arguments like add_values 1 2)
    if actual_at_d is not None:
        if attribute_runtime is None or ctx is None:
            return
        try:
            value = attribute_runtime.get_attribute_value(actual_at_d, item, ctx)
        except Exception:
            value = None
    else:
        # Resolve source attribute value if specified
        source_value: str | None = None
        if source:
            if attribute_runtime is None or ctx is None:
                return
            src_args: list[tuple[str, str]] = []
            if source_prefix:
                src_args.append(("prefix", source_prefix))
            src_d = AttributeDescriptor.create(source, args=src_args if src_args else None)
            try:
                source_value = attribute_runtime.get_attribute_value(src_d, item, ctx)
            except Exception:
                return
            if not isinstance(source_value, str) or not source_value:
                return

        # Build args for the target attribute
        args = [("source_value", source_value)] if source_value is not None else None

        # Try udan attribute (requires execution context)
        if attribute_runtime is not None and ctx is not None:
            try:
                at_d_create = AttributeDescriptor.create(attr_name, args=args)
                value = attribute_runtime.get_attribute_value(at_d_create, item, ctx)
            except Exception:
                value = None
        else:
            value = None

        # Fallback: try dict key or object attribute
        if value is None:
            if isinstance(item, dict):
                value = item.get(attr_name)
            else:
                value = getattr(item, attr_name, None)

    if value is None or value == "":
        return

    # Preserve list structure - yield the list as a single child
    # This allows attributes that return lists to maintain their structure
    yield value


_NOT_ATTRIBUTE = object()  # sentinel: a call target that is not a registered attribute


class _CattrResolver(ast.NodeTransformer):
    """Fold a cattr formula's identifiers into constants, leaving the rest to eval.

    Names resolve to values (the item itself via `it`, a registered attribute, or a
    dict field); calls to registered attributes are applied with argument binding
    (positional arguments bind to the non-framework parameters in order, keyword
    arguments bind by name, a single leftover argument overrides `item` itself).
    Everything else -- operators, literals, calls to the whitelisted builtins --
    stays as written, so Python's own parser handles nesting, precedence and
    string literals instead of hand-rolled substitution.
    """

    def __init__(
        self,
        item: Item,
        registry: ToolsRegistryAPI | None,
        attr_ctx: AttributesContextAPI | None,
        safe_globals: dict,
    ):
        self._item = item
        self._registry = registry
        self._attr_ctx = attr_ctx
        self._safe_globals = safe_globals

    def visit_Name(self, node: ast.Name) -> ast.Constant:
        val = self._resolve_name(node.id)
        # None falls back to 0 so a missing field does not break the whole expression
        return ast.copy_location(ast.Constant(value=val if val is not None else 0), node)

    def visit_Call(self, node: ast.Call) -> ast.expr:
        # Fold arguments first, so nested attribute calls resolve before their
        # result is needed as an argument value
        node.args = [self.visit(arg) for arg in node.args]
        node.keywords = [self.visit(kw) for kw in node.keywords]
        if isinstance(node.func, ast.Name):
            applied = self._apply_attribute(node)
            if applied is not _NOT_ATTRIBUTE:
                return ast.copy_location(ast.Constant(value=applied), node)
            # Not a registered attribute: a whitelisted builtin call (str, len,
            # ...), left for eval to resolve against the restricted builtins.
            # Anything else would die with a NameError deep inside eval and be
            # silently swallowed into None, so fail loudly right here instead
            if node.func.id not in _CATTR_BUILTINS:
                raise ExceptionWithAdvice(
                    f"cattr: unknown function '{node.func.id}' in '{ast.unparse(node)}': "
                    f"not a registered attribute and not one of the builtins {sorted(_CATTR_BUILTINS)}. "
                    f"Check the spelling, or register the attribute in a plugin."
                )
            return node
        node.func = self.visit(node.func)
        return node

    def _resolve_name(self, token: str) -> Any:
        """Resolve an identifier to its value for this item."""
        if token == "it":
            # `it` refers to the item itself (e.g. `cattr '(it + 1) % 2'`);
            # it shadows fields and attributes named `it`
            return self._item
        registry = self._registry
        if registry is not None:
            metadata = registry.get_metadata(token)
            if metadata is not None and metadata.tool_type == ATTRIBUTE:
                dep_at_d = AttributeDescriptor.create(token, args={})
                # Try storage first (cheap, no calculation triggered)
                val = self._attr_ctx.get_attr_value_from_storage(dep_at_d, self._item) if self._attr_ctx else None
                if val is None and self._attr_ctx is not None:
                    # Lazy resolution through the attribute runtime: it computes and
                    # materializes the value and detects circular references
                    try:
                        val = self._attr_ctx.get_attr_value(dep_at_d, self._item)
                    except ExceptionWithAdvice:
                        raise
                    except Exception:
                        val = None
                elif val is None:
                    # No attribute context (standalone resolver): call the registered
                    # function directly, without materialization
                    fn = registry.get_function(token)
                    if fn is not None:
                        try:
                            val = fn(item=self._item)
                        except Exception:
                            val = None
                return val
        if isinstance(self._item, dict):
            return self._item.get(token)
        return getattr(self._item, token, None)  # noqa: B009

    def _apply_attribute(self, node: ast.Call) -> Any:
        """Apply a registered attribute to the folded call arguments."""
        registry = self._registry
        if registry is None or not isinstance(node.func, ast.Name):
            return _NOT_ATTRIBUTE
        fn_name = node.func.id
        metadata = registry.get_metadata(fn_name)
        fn = registry.get_function(fn_name)
        if metadata is None or fn is None or metadata.tool_type != ATTRIBUTE:
            return _NOT_ATTRIBUTE

        call_text = ast.unparse(node)
        props = (metadata.parameters or {}).get("properties", {})
        bindables = [p for p in props if p not in FRAMEWORK_PARAMS_ATTR]
        bind_error = ExceptionWithAdvice(
            f"cattr: cannot bind arguments ({call_text!r}) of '{fn_name}' to parameters {bindables} (item is injected)"
        )

        kwargs: dict[str, Any] = {}
        for kw in node.keywords:
            if kw.arg is None or kw.arg not in bindables:
                raise bind_error
            kwargs[kw.arg] = self._value(kw.value)
        positional = [self._value(arg) for arg in node.args]

        remaining = [p for p in bindables if p not in kwargs]
        if len(positional) > len(remaining) + 1 or (len(positional) == len(remaining) + 1 and "item" not in props):
            raise bind_error
        call_item = self._item
        if len(positional) == len(remaining) + 1:
            # A single leftover argument overrides `item` itself, so
            # is_odd(it + 1) applies the is_odd attribute to a transform of the item
            call_item = positional[-1]
            positional = positional[:-1]
        call_kwargs = kwargs | dict(zip(remaining, positional, strict=True))
        if "item" in props:
            # Value-shaped fns (attribute_type "value") take no item: their value
            # parameters receive the composed inputs instead
            call_kwargs["item"] = call_item
        try:
            return fn(**call_kwargs)
        except Exception as e:
            raise ExceptionWithAdvice(f"cattr: call '{call_text}' failed: {e}") from e

    def _value(self, node: ast.expr) -> Any:
        """Value of a folded argument node: a constant directly, anything else via eval."""
        if isinstance(node, ast.Constant):
            return node.value
        tree = ast.fix_missing_locations(ast.Expression(body=node))
        return eval(compile(tree, "<cattr>", "eval"), self._safe_globals)  # noqa: S307


def _eval_cattr_expr(
    expr: str,
    item: Item,
    registry: ToolsRegistryAPI | None,
    attr_ctx: AttributesContextAPI | None,
) -> Any:
    """Parse and evaluate a cattr expression for one item.

    Identifiers fold to attribute values / dict fields / the item itself; the eval
    then runs plain Python over the folded tree under restricted builtins.
    """
    tree = ast.parse(expr, mode="eval")
    folded = _CattrResolver(item, registry, attr_ctx, _CATTR_SAFE_GLOBALS).visit(tree.body)
    code = compile(ast.fix_missing_locations(ast.Expression(body=folded)), "<cattr>", "eval")
    return eval(code, _CATTR_SAFE_GLOBALS)  # noqa: S307


def _named_column_fn(
    attr_name: str,
    expr: str,
    registry: ToolsRegistryAPI | None,
    attribute_runtime: AttributeRuntimeAPI | None,
    ctx: ExecContextAPI | None,
) -> Callable[[Item], Any]:
    """Build the lazy evaluator stored for a named cattr column.

    Recomputes the formula for items not yet materialized in attribute storage.
    Attribute tokens inside the formula resolve through a query attribute context
    over the shared storage (storage first, then the attribute runtime), so nested
    columns are evaluated - and checked for circular references - by the runtime,
    not here. The context is built at definition time: the column is defined at
    query resolution, before the query's own attribute context exists.
    """
    attr_ctx = (
        AttributesContext(
            attribute_runtime=attribute_runtime,
            attribute_storage=attribute_runtime.attribute_storage,
            ctx=ctx,
        )
        if attribute_runtime is not None and attribute_runtime.attribute_storage is not None and ctx is not None
        else None
    )

    def _evaluate(item: Item) -> Any:
        try:
            return _eval_cattr_expr(expr, item, registry, attr_ctx)
        except ExceptionWithAdvice:
            raise
        except Exception:
            # Malformed formula or a type error: same tolerance as the inline cattr
            return None

    return _evaluate


def _column_metadata(attr_name: str, expr: str) -> AttributeMetadata:
    """Registry metadata of a cattr column: the formula rides as 'cattr_expr'.

    The formula is the serialized representation of the column, so it resolves
    through the normal registry path in later cattr formulas, attribute-aware
    operators and dependencies, and re-evaluates lazily (via the stored
    evaluator) for items that were not materialized yet.
    """
    return AttributeMetadata(
        name=attr_name,
        description=f"Named cattr column: {expr}",
        parameters={"type": "object", "properties": {"item": {}}, "required": []},
        output_schema={
            "anyOf": [
                {"type": "string"},
                {"type": "number"},
                {"type": "boolean"},
                {"type": "null"},
                {"type": "object"},
                {"type": "array"},
            ]
        },
        fn_path="cattr",
        tool_type=ATTRIBUTE,
        attribute_type="simple",
        # Values may already sit in storage from an earlier query; the lazy
        # evaluator only serves items that were not materialized yet
        precalculated=True,
        meta={"cattr_expr": expr},
    )


@annotated(meta={"attribute_type": ATTRIBUTE_TYPE_COLUMN})
def cattr(
    expr: str = "",  # the binding of a chain item without a formula is rejected below
    name: str | None = None,
    registry: ToolsRegistryAPI | None = None,
    attribute_runtime: AttributeRuntimeAPI | None = None,
    ctx: ExecContextAPI | None = None,
) -> str:
    """Define a computed column (attribute) from an expression.

    A cattr chain item is a column definition, not a value: the query resolution
    registers the column (the formula is kept in the column's metadata) and the
    column is calculated per item through the normal attribute path. A formula
    references dict fields, registered attributes (callable: 'double(div_3)', with
    a transform argument: 'is_odd(it + 1)'), other columns of this query, and
    the item itself via the `it` token.

    The column is a registry member, so later formulas resolve it by name - in
    this query (e.g. a second cattr) and in later queries (operators,
    dependencies). Without --name the column is named by the formula string.
    Column names are query-local: redefining a name claimed by an earlier query
    replaces it, while two different formulas for one name within this query (or
    shadowing an existing tool) are errors.

    Args:
        expr: Expression string (e.g., 'calories * fruit_cost').
        name: Optional column name (defaults to expression string).
        registry: Tools registry (injected).
        attribute_runtime: Attribute runtime (injected).
        ctx: Execution context (injected).

    Returns:
        The column name.

    Examples:
        fruits, cattr 'calories * fruit_cost', :raw
        fruits, cattr 'calories * fruit_cost' --name=total, :fmt '{item[name]}: {total:.2f}'
        range 6, cattr '(it + 1) % 2 == 1' --name=next_is_odd
        range 6, cattr 'is_odd(it + 1)' --name=n1, cattr 'n1 == True' --name=n2
    """
    if registry is None or attribute_runtime is None or ctx is None:
        raise ExceptionWithAdvice(
            "cattr: column definition needs the query machinery (registry, attribute runtime, exec context); "
            "use it in a query chain as `cattr 'formula' [--name=X]`"
        )
    if not expr:
        raise ExceptionWithAdvice("cattr: missing formula: use `cattr 'expression' [--name=X]`")

    attr_name = name if name else expr
    # Naming rules (names are query-local): same name + same formula is an idempotent
    # no-op (query re-runs); two different formulas for one name within the same
    # query, and shadowing a non-column tool, are errors; a name claimed by
    # an EARLIER query is free to redefine - the previous definition (metadata,
    # evaluator, stored values) is replaced
    first_claim_in_query = ctx.claim_named_column(attr_name)
    existing = registry.get_metadata(attr_name)
    if existing is not None:
        if not (isinstance(existing, AttributeMetadata) and existing.meta.get("cattr_expr") == expr):
            existing_is_column = isinstance(existing, AttributeMetadata) and "cattr_expr" in existing.meta
            if not first_claim_in_query or not existing_is_column:
                detail = f", formula '{existing.meta.get('cattr_expr')}'" if existing.meta.get("cattr_expr") else ""
                raise ExceptionWithAdvice(
                    f"cattr: cannot use --name='{attr_name}': already taken by "
                    f"'{existing.name}' ({existing.tool_type}{detail}). Choose a different name."
                )
            # Redefinition of a column claimed by an earlier query: drop the values
            # of the old formula so they cannot be served for the new definition
            storage = attribute_runtime.attribute_storage
            assert storage is not None, "attribute_storage must be set to drop stale column values"
            storage.delete_attr_values(AttributeDescriptor.create(attr_name, args={}))

    # Registration happens once per chain item at resolution; values are computed
    # later, per item, through the normal attribute path (the registered evaluator)
    registry.register_metadata(
        _column_metadata(attr_name, expr), None, _named_column_fn(attr_name, expr, registry, attribute_runtime, ctx)
    )
    return attr_name


@annotated(meta={"tool_type": "grouper", "item_type": "any", "dependencies": {"value": None}})
def group_by_attribute(
    item: Item,
    at_d: AttributeDescriptor | None = None,
    value: AttributeValue = None,
) -> Any:
    return value


_FILTER_OPERATORS_MAP: dict[str, Callable[[Any, Any], bool]] = {
    "==": operator.eq,
    "=": operator.eq,
    "!=": operator.ne,
    "<>": operator.ne,
    "<": operator.lt,
    ">": operator.gt,
    "<=": operator.le,
    ">=": operator.ge,
}


@annotated(meta={"tool_type": "filter", "item_type": "any", "dependencies": {"attr_value": None}})
def filter_by_attribute(
    item: Item,
    at_d: AttributeDescriptor | None = None,
    operator: Literal["=", "==", "!=", "<>", "<", ">", "<=", ">="] = "=",
    value: AttributeValue = None,
    attr_value: AttributeValue = None,
) -> bool:
    compare_func = _FILTER_OPERATORS_MAP.get(operator)
    if compare_func is None:
        return False
    try:
        return compare_func(attr_value, value)
    except TypeError:
        return False
