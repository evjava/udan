"""Attribute calculation engine."""

from __future__ import annotations

import inspect
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

from udan.attributes.api_attribute_cache import AttributeCacheAPI
from udan.attributes.api_attribute_contexts import AttributesContextAPI
from udan.attributes.api_attribute_runtime import AttributeRuntimeAPI
from udan.attributes.api_attribute_storage import AttributeStorageAPI
from udan.core.api_attributes import (
    ATTRIBUTE,
    ATTRIBUTE_TYPE_COLUMN,
    SYSTEM,
    Attribute,
    AttributeDescriptor,
    AttributeMetadata,
    AttributeValue,
    is_aggregate_attribute,
)
from udan.core.api_chain_context import ChainContextAPI
from udan.core.api_constants import NODE_ROOT_ITEM
from udan.core.api_exceptions import ExceptionWithAdvice
from udan.core.api_exec_context import ExecContextAPI
from udan.core.api_forests import Forest, Item, Node
from udan.core_tools_loading.api_annotated import unwrap_function
from udan.core_tools_loading.api_tools import ToolDescriptor
from udan.core_tools_loading.api_tools_registry import ToolsRegistryAPI
from udan.core_tools_loading.api_types import Group


def _as_attribute_descriptor(desc: ToolDescriptor) -> AttributeDescriptor:
    """Narrow the walk's generic descriptor to the attribute descriptor the storage keys.

    The walk hands every context method the base descriptor; this runtime's storage
    and the attribute machinery key on the attribute subclass, which is what the
    chain actually resolves for the ATTRIBUTE kind.

    Raises:
        ValueError: If the descriptor is not an attribute descriptor
    """
    if not isinstance(desc, AttributeDescriptor):
        raise ValueError(f"the attributes context stores attribute descriptors, got {type(desc).__name__}")
    return desc


class AttributesContext(AttributesContextAPI):
    """Forest context passed to tools during expansion.

    This is the implementation of AttributesContextAPI.
    The API documentation is in the AttributesContextAPI class in api.py.

    Provides access to attribute runtime, registry, and attribute storage.
    """

    def __init__(
        self,
        attribute_runtime: AttributeRuntimeAPI,
        attribute_storage: AttributeStorageAPI,
        requested_attributes: list[AttributeDescriptor] | None = None,
        ctx: ExecContextAPI | None = None,
    ):
        if ctx is None:
            raise ValueError("AttributesContext requires a query ctx (ExecContextAPI) for query-time logging")
        self.attribute_runtime = attribute_runtime
        self.registry = attribute_runtime.registry
        self.depth: int = 0
        # Store requested attribute descriptors for on-demand calculation
        self.requested_attributes: list[AttributeDescriptor] = requested_attributes or []
        # Use the provided attribute_storage
        self._storage = attribute_storage
        # Query execution context for query-time logging
        self.ctx = ctx

    def set_attr_value(self, at_d: AttributeDescriptor, item: Item, value: AttributeValue) -> None:
        """Store an attribute value for an item."""
        self._storage.set_attr_value(at_d, item, value)

    def get_attr_value(self, at_d: AttributeDescriptor, item: Item) -> Any:
        """Get an attribute value."""
        return self.attribute_runtime.get_attribute_value(at_d, item, self.ctx)

    def get_requested_attributes(self) -> list[AttributeDescriptor]:
        """Get the list of requested attribute descriptors."""
        return self.requested_attributes

    def get_attr_value_from_storage(self, at_d: AttributeDescriptor, item: Item) -> Any:
        """Get attribute value from storage without triggering calculation.

        This method directly accesses the storage to check if a value exists
        without calculating it. Returns None if the value is not in storage.

        Args:
            at_d: Attribute descriptor to look up
            item: Item to look up

        Returns:
            Attribute value from storage, or None if not found
        """
        return self._storage.get_attr_value_from_dict(at_d, item)

    def set_value(self, desc: ToolDescriptor, item: Item, value: AttributeValue) -> None:
        """The walk's generic store call, over attribute storage."""
        self.set_attr_value(_as_attribute_descriptor(desc), item, value)

    def get_requested(self) -> list[ToolDescriptor]:
        """The requested attributes, in the walk's generic shape."""
        return list(self.get_requested_attributes())

    def get_stored_value(self, desc: ToolDescriptor, item: Item) -> Any | None:
        """The walk's generic store read."""
        return self.get_attr_value_from_storage(_as_attribute_descriptor(desc), item)

    def get_value(self, desc: ToolDescriptor, item: Item) -> Any:
        """The walk's generic read, computing on demand."""
        return self.get_attr_value(_as_attribute_descriptor(desc), item)

    def apply_values(self, forest: Forest, requested: list[ToolDescriptor], ctx: ExecContextAPI) -> None:
        """The walk's whole-forest pass: the attributes the walk did not apply."""
        attr_ds = [d for d in requested if isinstance(d, AttributeDescriptor)]
        self.attribute_runtime.calculate_attributes_in_forest(forest, attr_ds, ctx)


@dataclass
class SimpleAttribute(Attribute):
    """Simple attribute that calculates values directly from item properties.

    This is the standard attribute type that calls a function with the item
    to compute the attribute value.
    """

    at_d: AttributeDescriptor
    at_fn: Callable[..., AttributeValue]
    metadata: AttributeMetadata  # Metadata for this attribute

    def __post_init__(self) -> None:
        """Introspect once whether the fn takes `item` (value-shaped fns take none)."""
        self._takes_item = "item" in inspect.signature(unwrap_function(self.at_fn)).parameters

    def _call_fn(self, item: Item, **kwargs: object) -> AttributeValue:
        """Call the attribute fn for the item.

        Value-shaped fns (attribute_type "value", no `item` parameter) are called
        without `item`: their arguments carry the inputs (e.g. a composed value).
        """
        if self._takes_item:
            return self.at_fn(item=item, **kwargs)
        return self.at_fn(**kwargs)

    def calculate(self, context: AttributesContextAPI, children: Iterable[Node]) -> None:
        """Calculate attribute values for items.

        Caching is not part of this attribute: whether its values are served from
        the attribute cache is decided by the runtime, which reads the same
        metadata when it calculates.

        Args:
            context: Forest context with attribute storage (access context.ctx for UdanContext)
            children: Nodes to calculate attributes for
        """
        # Check if this attribute depends on another attribute
        if self.metadata.dependencies:
            self._calculate_with_dependency(context, children)
            return

        # Check if attribute needs node access
        has_node_arg = False
        for arg_name, _ in self.at_d.args:
            if arg_name == "node":
                has_node_arg = True
                break

        # No dependency: calculate as before
        for child in children:
            item = child.item
            # Skip Group items - they are metadata containers, not actual data
            # Attributes should not be calculated on Group objects
            if isinstance(item, Group):
                continue

            # Check if value is already pre-calculated in storage (e.g., origin from tool application)
            # This allows certain attributes to be set during tool application rather than calculation
            # Only use pre-calculated values for attributes marked as precalculated
            if self.metadata.precalculated:
                precalculated_value = context.get_attr_value_from_storage(self.at_d, item)
                if precalculated_value is not None:
                    # Use the pre-calculated value, skip calling the attribute function
                    context.set_attr_value(self.at_d, item, precalculated_value)
                    continue

            # Prepare arguments for attribute function
            args = dict(self.at_d.args)
            if has_node_arg:
                args["node"] = child

            # Resolve attribute references in args: if a string arg matches
            # a registered attribute name, resolve it to that attribute's value
            args = self._resolve_attr_refs_in_args(context, args, item)

            at_val = self._call_fn(item, **args)
            context.set_attr_value(self.at_d, item, at_val)

    def _resolve_attr_refs_in_args(
        self, context: AttributesContextAPI, args: dict[str, Any], item: Item
    ) -> dict[str, Any]:
        """Resolve attribute references in function arguments.

        If a string arg value matches a registered attribute name, resolve it
        to that attribute's computed value for the item. An AttributeDescriptor
        arg value (from parameterized syntax like `double(div_3)`) is treated
        as an attribute reference directly.
        """
        resolved = dict(args)
        for arg_name, arg_val in args.items():
            if arg_name == "node":
                continue
            if isinstance(arg_val, AttributeDescriptor):
                dep_at_d = arg_val
            elif isinstance(arg_val, str):
                at_m = context.registry.get_metadata(arg_val)
                if at_m is None or at_m.tool_type != ATTRIBUTE or not isinstance(at_m, AttributeMetadata):
                    continue
                dep_at_d = AttributeDescriptor.create(arg_val, args={})
            else:
                continue
            dep_value = context.get_attr_value_from_storage(dep_at_d, item)
            if dep_value is None and context.attribute_runtime is not None:
                item_node = Node.create(item=item, children=[])
                context.attribute_runtime.calculate_attribute_descriptor_for_child(context, dep_at_d, item_node)
                dep_value = context.get_attr_value_from_storage(dep_at_d, item)
            resolved[arg_name] = dep_value
        return resolved

    def _get_dependency_dict(self) -> dict[str, str | None]:
        """Get dependencies as dict of parameter name to attribute name.

        Returns:
            Dict mapping parameter names to attribute names (or None for @attribute marker)
        """
        return self.metadata.dependencies or {}

    def _calculate_with_dependency(self, context: AttributesContextAPI, children: Iterable[Node]) -> None:
        """Calculate attribute values after resolving dependencies.

        For attributes with dependencies, resolves the dependency attribute(s)
        first, then passes their value(s) as parameter(s) to the attribute function.

        For attributes with pre-calculated values in storage (e.g., origin from tool application),
        skips calculation and uses the stored value.
        """
        deps_dict = self._get_dependency_dict()
        # Descriptors for the named dependencies, built once before the items loop.
        # None entries are the @attribute marker - those values are resolved during
        # tool application, not here.
        dep_at_ds = {param: AttributeDescriptor.create(name) for param, name in deps_dict.items() if name is not None}

        for child in children:
            item = child.item
            # Skip Group items - they are metadata containers, not actual data
            # Attributes should not be calculated on Group objects
            if isinstance(item, Group):
                continue

            # Check if value is already pre-calculated in storage (e.g., origin from tool application)
            # This allows certain attributes to be set during tool application rather than calculation
            # Only use pre-calculated values for attributes marked as precalculated
            if self.metadata.precalculated:
                precalculated_value = context.get_attr_value_from_storage(self.at_d, item)
                if precalculated_value is not None:
                    # Use the pre-calculated value, skip calling the attribute function
                    context.set_attr_value(self.at_d, item, precalculated_value)
                    continue

            # Resolve all dependencies
            dep_values = {}
            for param_name, dep_at_d in dep_at_ds.items():
                # Resolve dependency attribute
                dep_value = context.get_attr_value_from_storage(dep_at_d, item)
                if dep_value is None:
                    # Dependency not calculated yet, calculate it now
                    if context.attribute_runtime is None:
                        raise RuntimeError("attribute_runtime is required for attributes with dependencies")
                    # IMPORTANT: Pass child directly - calculate_attribute_descriptor_for_child handles wrapping
                    context.attribute_runtime.calculate_attribute_descriptor_for_child(context, dep_at_d, child)
                    dep_value = context.get_attr_value_from_storage(dep_at_d, item)

                # Store dependency value using parameter name as key
                dep_values[param_name] = dep_value

            # Build kwargs: include descriptor args plus dependency values
            kwargs = dict(self.at_d.args)
            # Pass each dependency value using the parameter name from dependencies dict
            kwargs.update(dep_values)

            # Calculate this attribute
            at_val = self._call_fn(item, **kwargs)
            context.set_attr_value(self.at_d, item, at_val)

    def __repr__(self) -> str:
        return f"Attr({self.at_d})"


@dataclass
class CompositeAttribute(Attribute):
    """Attribute that extracts a field from another attribute's value.

    For example, 'pfc.proteins' would extract the 'proteins' field from
    the 'pfc' attribute value.
    """

    at_d: AttributeDescriptor
    base_at_d: AttributeDescriptor
    field_path: str

    def calculate(self, context: AttributesContextAPI, children: Iterable[Node]) -> None:
        """Calculate composite attribute by extracting field from base attribute.

        Args:
            context: Forest context with attribute storage (access context.ctx for UdanContext)
            children: Nodes to calculate attributes for
        """
        # First, ensure the base attribute is calculated
        # Create a temporary node with all children
        temp_node = Node(item=NODE_ROOT_ITEM, children=list(children))

        # Calculate the base attribute if not already calculated
        if context.attribute_runtime is None:
            raise RuntimeError("attribute_runtime is required for composite attributes")
        context.attribute_runtime.calculate_attribute_descriptor_in_node(context, self.base_at_d, temp_node)

        # Now extract the field from the base attribute value
        for child in children:
            item = child.item
            # Get the base attribute value
            base_value = context.get_attr_value_from_storage(self.base_at_d, item)
            if base_value is None:
                # Base attribute not found or is None
                context.set_attr_value(self.at_d, item, None)
                continue

            # Extract the field from the base value
            # Support nested field access like "field.nested"
            try:
                value = base_value
                for field in self.field_path.split("."):
                    if isinstance(value, dict):
                        value = value.get(field)
                    else:
                        # Handle object attribute access
                        value = getattr(value, field, None)
                context.set_attr_value(self.at_d, item, value)
            except KeyError, AttributeError, TypeError:
                context.set_attr_value(self.at_d, item, None)

    def __repr__(self) -> str:
        return f"CompAttr({self.at_d} <- {self.base_at_d}.{self.field_path})"


class AttributeRuntimeImpl(AttributeRuntimeAPI):
    """Handles attribute calculation on tree structures."""

    def __init__(
        self,
        registry: ToolsRegistryAPI,
        attribute_storage: AttributeStorageAPI,
        cache: AttributeCacheAPI,
    ) -> None:
        """Initialize attribute runtime.

        Args:
            registry: ToolsRegistryAPI instance for resolving attributes
            attribute_storage: AttributeStorageAPI for storing attribute values
            cache: AttributeCacheAPI for caching computed attribute values
        """
        self.registry = registry
        self.attribute_storage = attribute_storage
        self._cache = cache
        # Cycle guard for lazy attribute evaluation: (attribute name, id(item)) pairs
        # currently being resolved. Re-entering the same pair means a circular
        # reference (formula columns referencing each other, or mutual dependencies).
        # Internal state - plugins never touch it; the guard lives in the lazy
        # evaluation entry points below.
        self._eval_in_progress: set[tuple[str, int]] = set()

    def _resolve_attribute(self, at_d: AttributeDescriptor) -> Attribute:
        """Resolve attribute descriptor to Attribute object.

        Args:
            at_d: Attribute descriptor

        Returns:
            Attribute object

        Raises:
            TypeError: If not an AttributeDescriptor
            ValueError: If attribute not found
        """
        if not isinstance(at_d, AttributeDescriptor):
            raise TypeError(f"Not a AttributeDescriptor: {at_d}")
        name = at_d.name

        # Check if this is a composite attribute (contains a dot)
        if "." in name:
            # Split into base attribute and field path
            base_attr_name, field_path = name.split(".", 1)

            # Resolve base attribute descriptor
            base_at_d = AttributeDescriptor.create(base_attr_name, {})

            # Resolve base attribute to check it exists
            base_at_m = self.registry.get_metadata(base_attr_name)
            if not base_at_m or not isinstance(base_at_m, AttributeMetadata):
                raise ValueError(f"Base attribute '{base_attr_name}' not found for composite attribute '{name}'")

            # Create composite attribute
            return CompositeAttribute(
                at_d=at_d,
                base_at_d=base_at_d,
                field_path=field_path,
            )

        # Normal attribute resolution
        at_m = self.registry.get_metadata(name)
        assert isinstance(at_m, AttributeMetadata)
        if at_m.attribute_type == ATTRIBUTE_TYPE_COLUMN:
            # A column-definition attribute is a column factory: it has no value of
            # its own, its chain items resolve to the column they define
            raise ExceptionWithAdvice(
                f"'{name}' defines columns and has no value of its own - use it in a chain with a formula argument"
            )

        at_fn = self.registry.get_function(name)
        if not at_fn:
            raise ValueError(
                f"Attribute metadata found for '{name}', but no function registered. "
                f"This usually means the tool was registered without a function."
            )

        return SimpleAttribute(at_d=at_d, at_fn=at_fn, metadata=at_m)

    def create_attributes_context(
        self,
        attribute_storage: AttributeStorageAPI,
        requested_attributes: list[Any] | None = None,
        ctx: ExecContextAPI | None = None,
    ) -> AttributesContextAPI:
        """Create an AttributesContext for tool application.

        Args:
            attribute_storage: Attribute storage for the context
            requested_attributes: Optional list of attributes to compute
            ctx: Query execution context for query-time logging

        Returns:
            AttributesContext instance configured with this runtime
        """
        if ctx is None:
            raise ValueError("create_attributes_context requires a query ctx (ExecContextAPI)")
        return AttributesContext(
            attribute_runtime=self,
            attribute_storage=attribute_storage,
            requested_attributes=requested_attributes,
            ctx=ctx,
        )

    def calculate_attribute_descriptor_in_node(
        self, context: AttributesContext, at_d: AttributeDescriptor, node: Node
    ) -> None:
        """Calculate attribute for a node and its descendants by descriptor.

        This is a convenience method that resolves the attribute descriptor
        and then calculates it, eliminating the need for callers to do both steps.

        Args:
            context: Forest context with attribute storage (access context.ctx for UdanContext)
            at_d: Attribute descriptor to calculate
            node: Node to calculate attribute for
        """

        # Skip calculation for system attributes (set by pre-render phase)
        # Check metadata directly from registry instead of tracking via storage
        metadata = self.registry.get_metadata(at_d.name)
        if metadata and metadata.meta.get(SYSTEM, False):
            return

        attr = self._resolve_attribute(at_d)
        self._calculate_attribute_in_node(context, at_d, attr, node)

    def _enter_eval(self, attr_name: str, item: Item) -> None:
        """Mark an attribute evaluation as in progress, raising on re-entry.

        Lazy evaluation re-entering the same (attribute, item) pair is a circular
        reference: named cattr columns evaluating each other's formulas, or
        attributes with mutual dependencies. Fails loudly instead of recursing.
        """
        key = (attr_name, id(item))
        if key in self._eval_in_progress:
            raise ExceptionWithAdvice(f"circular reference while evaluating attribute '{attr_name}'")
        self._eval_in_progress.add(key)

    def _exit_eval(self, attr_name: str, item: Item) -> None:
        """Clear the in-progress mark after an attribute evaluation finished."""
        self._eval_in_progress.discard((attr_name, id(item)))

    def calculate_attribute_descriptor_for_child(
        self, context: AttributesContext, at_d: AttributeDescriptor, child: Node
    ) -> None:
        """Calculate attribute for a single child node by descriptor.

        This is a convenience method for calculating attributes for a single node
        (not recursively). It wraps the child in a parent node since Attribute.calculate
        expects to iterate over children.

        Args:
            context: Forest context with attribute storage (access context.ctx for UdanContext)
            at_d: Attribute descriptor to calculate
            child: Child node to calculate attribute for
        """
        self._enter_eval(at_d.name, child.item)
        try:
            attr = self._resolve_attribute(at_d)
            self._calculate_attribute(context, at_d, attr, [child])
        finally:
            self._exit_eval(at_d.name, child.item)

    def _calculate_attribute_in_node(
        self, context: AttributesContext, at_d: AttributeDescriptor, attr: Attribute, node: Node
    ) -> None:
        """Calculate attribute for a node and its descendants.

        Args:
            context: Forest context with attribute storage (access context.ctx for UdanContext)
            at_d: Attribute descriptor to calculate
            attr: Attribute to calculate
            node: Node to calculate attribute for
        """
        children = node.children
        self._calculate_attribute(context, at_d, attr, children)
        for child in children:
            self._calculate_attribute_in_node(context, at_d, attr, child)

    def _calculate_attribute(
        self, context: AttributesContext, at_d: AttributeDescriptor, attr: Attribute, children: list[Node]
    ) -> None:
        """Calculate an attribute for children, serving cacheable attributes from the cache.

        Caching is a runtime concern: an attribute is only a computation - its
        descriptor, function and metadata - so whether its values are served from
        the attribute cache is decided here, next to the cache itself.

        Args:
            context: Forest context with attribute storage (access context.ctx for UdanContext)
            at_d: Attribute descriptor to calculate
            attr: Attribute to calculate
            children: Nodes to calculate attributes for
        """
        at_m = self.registry.get_metadata(at_d.name)
        if isinstance(at_m, AttributeMetadata) and at_m.cache_attribute:
            self._calculate_cached(context, at_d, attr, at_m.cache_attribute, children)
            return
        attr.calculate(context, children)

    def _calculate_cached(
        self,
        context: AttributesContext,
        at_d: AttributeDescriptor,
        attr: Attribute,
        stamp_attribute: str,
        children: list[Node],
    ) -> None:
        """Calculate attribute values, taking them from the cache when present.

        The stamp attribute named by `stamp_attribute` keys the cache entry. On a
        hit the cached value is stored for the item; on a miss the attribute
        calculates the value and the result is put into the cache.

        Args:
            context: Forest context with attribute storage (access context.ctx for UdanContext)
            at_d: Attribute descriptor to calculate
            attr: Attribute to calculate
            stamp_attribute: Name of the attribute whose value keys the cache entry
            children: Nodes to calculate attributes for
        """
        # Stamp attribute descriptor and use it as cache key
        stamp_at_d = AttributeDescriptor.create(stamp_attribute, args={})
        # Serialize descriptor to string for cache lookup
        attr_cache_key = at_d.cache_key()
        attr_identity = at_d.name

        for child in children:
            item = child.item

            # Calculate stamp attribute value (should be cheap)
            # First check if it's already calculated
            stamp_value = context.get_attr_value_from_storage(stamp_at_d, item)
            if stamp_value is None:
                # Not calculated yet, calculate it now
                context.attribute_runtime.calculate_attribute_descriptor_for_child(context, stamp_at_d, child)
                stamp_value = context.get_attr_value_from_storage(stamp_at_d, item)

            # Convert cache key to string (handle None, dicts, etc.)
            if stamp_value is None:
                cache_key = "None"
            elif isinstance(stamp_value, dict):
                # For dicts, use a stable string representation
                cache_key = str(sorted(stamp_value.items()))
            else:
                cache_key = str(stamp_value)

            # Cache hit: use cached value
            cached_value = self._cache.get_value(attr_identity, attr_cache_key, cache_key, context.ctx)
            if cached_value is not None:
                context.set_attr_value(at_d, item, cached_value)
                continue

            # Cache miss: calculate and store
            attr.calculate(context, [child])
            self._cache.set_value(
                attr_identity, attr_cache_key, cache_key, context.get_attr_value_from_storage(at_d, item), context.ctx
            )

    def calculate_attributes_in_forest(
        self, forest: Forest, attr_descriptors: list[AttributeDescriptor], ctx: ExecContextAPI
    ) -> None:
        """Calculate attributes for entire forest.

        Args:
            forest: Forest to calculate attributes for
            attr_descriptors: List of attribute descriptors to calculate
            ctx: Execution context for query-time logging
        """
        node = forest.convert_to_node()
        # Use the global attribute_storage (APP-scoped singleton)
        assert self.attribute_storage is not None, "attribute_storage must not be None"
        context = AttributesContext(attribute_runtime=self, attribute_storage=self.attribute_storage, ctx=ctx)

        # Attributes are now stored in attribute_storage only, not in forest.attributes
        for at_d in attr_descriptors:
            # Skip dynamically-computed attributes that are already in storage
            # (e.g., from cattr) and are not registered tools
            is_in_storage = self.attribute_storage.has_attribute_descriptor(at_d)
            if is_in_storage and self.registry.get_metadata(at_d.name) is None:
                continue
            # Skip aggregate attributes — they are computed in bulk below
            if is_aggregate_attribute(self.registry, at_d.name):
                continue
            self.calculate_attribute_descriptor_in_node(context, at_d, node)
        # Show calculated attribute keys (consider adding verbose levels to show full attribute values)
        attr_keys = self.attribute_storage.attributes.keys()
        if attr_keys:
            ctx.debug(f"calculated attributes: {attr_keys}")

        # Compute aggregate attributes (after all per-item attributes)
        aggregate_at_ds = [at_d for at_d in attr_descriptors if is_aggregate_attribute(self.registry, at_d.name)]
        if aggregate_at_ds:
            self._compute_aggregate_attributes(context, node, aggregate_at_ds, ctx)

    def calculate_aggregate_attributes(
        self,
        context: AttributesContext,
        nodes: list[Node],
        target_item: Item,
        at_ds: list[AttributeDescriptor],
        ctx: ExecContextAPI,
    ) -> None:
        """Compute aggregate attributes over one stage: the stage-level aggregate entry.

        The same bottom-up walk the forest-level bulk computation runs, over the nodes
        a chain position hands in: leaves per inner node, the global value on the
        stage's root item. Called by the orchestrator's walk for an aggregate written
        before a later chain item, so the value answers what exists at that position.

        Args:
            context: Forest context with attribute storage
            nodes: The stage's top-level nodes
            target_item: Item the global aggregate value is stored on
            at_ds: Aggregate attribute descriptors to compute
            ctx: Execution context for query-time logging
        """
        if not at_ds:
            return
        all_leaves = self._collect_aggregate_leaves(context, nodes, at_ds, ctx)
        self._compute_aggregate_for_items(at_ds, all_leaves, target_item, context, ctx)

    def apply_chain_step(
        self,
        descriptors: list[ToolDescriptor],
        stage: Forest,
        chain_context: ChainContextAPI,
        ctx: ExecContextAPI,
        item_cap: int | None = None,
    ) -> Forest:
        """Compute attribute values over the stage at their chain position; pass it through.

        Computing, not transforming: the stage the descriptors were resolved over is
        returned unchanged, the values land in attribute storage. Dispatch by
        attribute_type - the level of routing where that knowledge lives: an aggregate
        runs the stage-level bulk walk, a column definition is skipped (it has no value
        of its own; renders and aggregates read it lazily), anything else computes
        per item over the stage node.

        Args:
            descriptors: Attribute descriptors of the chain group, in written order
            stage: The forest the chain groups before this one produced
            chain_context: The per-query context of the walk
            ctx: Execution context for query-time logging
            item_cap: Ignored: attribute computation is not a lazy pull

        Returns:
            The stage, unchanged
        """
        assert isinstance(chain_context, AttributesContext), "attribute chain steps run with the runtime's context"
        attr_context = chain_context
        node = stage.convert_to_node()
        for descriptor in descriptors:
            # The routing sends this service only attribute descriptors; the narrowing
            # keeps the per-descriptor calls on their declared type
            if not isinstance(descriptor, AttributeDescriptor):
                continue
            if is_aggregate_attribute(self.registry, descriptor.name):
                self.calculate_aggregate_attributes(attr_context, node.children, node.item, [descriptor], ctx)
            elif not self._is_column_definition(descriptor):
                self.calculate_attribute_descriptor_in_node(attr_context, descriptor, node)
        return stage

    def _is_column_definition(self, at_d: AttributeDescriptor) -> bool:
        """Check if an attribute descriptor defines columns instead of producing values.

        Args:
            at_d: Attribute descriptor

        Returns:
            True when the attribute is registered with the column attribute_type
        """
        metadata = self.registry.get_metadata(at_d.name)
        return isinstance(metadata, AttributeMetadata) and metadata.attribute_type == ATTRIBUTE_TYPE_COLUMN

    def _compute_aggregate_attributes(
        self,
        context: AttributesContext,
        node: Node,
        aggregate_at_ds: list[AttributeDescriptor],
        ctx: ExecContextAPI,
    ) -> None:
        """Compute aggregate attributes for the entire forest and per-node.

        Walks the tree once, bottom-up: collect leaf items for each node,
        then compute aggregates deepest-first, so every node above the leaves
        carries the aggregate of its subtree.
        """
        if not aggregate_at_ds:
            return
        all_leaves = self._collect_aggregate_leaves(context, node.children, aggregate_at_ds, ctx)
        self._compute_aggregate_for_items(aggregate_at_ds, all_leaves, node.item, context, ctx)

    def _collect_aggregate_leaves(
        self,
        context: AttributesContext,
        nodes: list[Node],
        aggregate_at_ds: list[AttributeDescriptor],
        ctx: ExecContextAPI,
    ) -> list[Item]:
        """Collect the leaf items of these nodes, storing each inner node's subtree aggregate.

        Args:
            context: Forest context with attribute storage
            nodes: Top-level nodes to collect the leaves of
            aggregate_at_ds: Aggregate attribute descriptors computed per inner node
            ctx: Execution context for query-time logging

        Returns:
            The leaf items, in order
        """
        leaves: list[Item] = []
        for child in nodes:
            if child.children:
                child_leaves = self._collect_aggregate_leaves(context, child.children, aggregate_at_ds, ctx)
                # Store aggregate for this inner node (group, extended node, ...)
                self._compute_aggregate_for_items(aggregate_at_ds, child_leaves, child.item, context, ctx)
                leaves.extend(child_leaves)
            else:
                leaves.append(child.item)
        return leaves

    def _compute_aggregate_for_items(
        self,
        aggregate_at_ds: list[AttributeDescriptor],
        items: list[Item],
        target_item: Item,
        context: AttributesContext,
        ctx: ExecContextAPI,
    ) -> None:
        """Compute aggregate attributes for a given list of items, store on target_item."""
        assert self.attribute_storage is not None, "attribute_storage must not be None"
        for at_d in aggregate_at_ds:
            at_fn = self.registry.get_function(at_d.name)
            if at_fn is None:
                continue

            sig = inspect.signature(at_fn)

            kwargs: dict[str, Any] = {}
            if "items" in sig.parameters:
                kwargs["items"] = items
            # Pass named args from descriptor
            for key, val in dict(at_d.args).items():
                if key in sig.parameters:
                    kwargs[key] = val
            # Aggregates declaring attr_ctx in their user-facing schema receive this
            # context: they fall back to stored attribute values / lazy named cattr
            # columns when a named column is not an item field. Passing it explicitly
            # also keeps the injector from trying to resolve it (it is query-scoped).
            metadata = self.registry.get_metadata(at_d.name)
            if metadata is not None and "attr_ctx" in (metadata.parameters or {}).get("properties", {}):
                kwargs["attr_ctx"] = context

            result = at_fn(**kwargs)
            self.attribute_storage.set_attr_value(at_d, target_item, result)
            ctx.debug(f"Aggregate attribute {at_d.name}: {result}")

    def get_attribute_value(self, attr_d: AttributeDescriptor, item: Item, ctx: ExecContextAPI) -> Any:
        """Get attribute value for a specific item.

        Args:
            attr_d: Attribute descriptor
            item: Item to get attribute value for
            ctx: Execution context for query-time logging

        Returns:
            Attribute value

        Raises:
            ExceptionWithAdvice: If lazy evaluation re-enters the same
                (attribute, item) pair - a circular reference
        """
        ctx.debug(f"going to calculate attribute: {attr_d}, {item}")
        self._enter_eval(attr_d.name, item)
        try:
            return self._get_attribute_value_inner(attr_d, item, ctx)
        finally:
            self._exit_eval(attr_d.name, item)

    def _get_attribute_value_inner(self, attr_d: AttributeDescriptor, item: Item, ctx: ExecContextAPI) -> Any:
        assert self.attribute_storage is not None, "attribute_storage must not be None"
        # Check if attribute is already calculated in attribute_storage
        value = self.attribute_storage.get_attr_value_from_dict(attr_d, item)
        if value is not None:
            ctx.debug(f"Found pre-calculated attribute value: {value}")
            return value

        # Create context with the storage
        context = AttributesContext(attribute_runtime=self, attribute_storage=self.attribute_storage, ctx=ctx)

        # Create a parent node with the item as its child
        # attr.calculate() iterates over children, so item must be a child
        item_node = Node.create(item=item, children=[])
        parent_node = Node.create(item="parent", children=[item_node])

        # Calculate attribute for the parent node (will process item_node as a child)
        self.calculate_attribute_descriptor_in_node(context, attr_d, parent_node)

        # Return the calculated value from storage
        # Use get_attr_value_from_dict to handle both hashable and unhashable items.
        # A None result means the stored value is None (a valid value) - direct
        # dict indexing must not be used as fallback: unhashable items are kept
        # in a separate storage and would raise KeyError/TypeError here.
        return self.attribute_storage.get_attr_value_from_dict(attr_d, item)
