"""Operator application engine.

This module contains the OperatorImpl class (implementation of Operator) and the
OperatorsEngine that orchestrates operator application: the walk every operator kind
goes through. The engine owns no operator kind - the kinds live beside the packages
whose services own them, and each service contributes its applicator to the engine's
dispatch at container build (register_applicator) - so this module names none of them:
it resolves an operator descriptor, pre-extracts its OperatorArgs, hands the uniform
applicator its arguments, and marks what came out with its origin.

That is also why the module exists with no kind of its own: the walk (with its
streaming stages, item cap, introspection short-circuit and origin handling), the
dispatch, and the chain step adapter every kind service delegates its groups to are
machinery shared by all of them - one algorithm that cannot decompose per kind. See
docs/architecture.md, the OperatorsEngine section, for the full reasoning.

The engine is a plugin package's own component, not a core one: it is provided by this
package's container contribution, and a host that leaves the package out of
udan_plugin_modules runs with no operator application at all - no operator kind is in
the vocabulary then, so a chain of static structure, attributes and renders still runs.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from inspect import signature
from itertools import islice
from typing import Any, get_type_hints

from pydantic import BaseModel

from udan.core.api_attributes import AttributeDescriptor
from udan.core.api_chain_context import ChainContextAPI
from udan.core.api_constants import (
    ARG_ON_DEPTH,
    ARG_POSITION,
    NODE_ROOT_ITEM,
    NODE_VAR_PREFIX,
    OVERRIDES_OUTPUT,
    TYPE_FOREST,
    TYPE_LIST,
    TYPE_QUERY,
    DepthSelector,
)
from udan.core.api_exceptions import OverrideForestException
from udan.core.api_exec_context import ExecContextAPI
from udan.core.api_forests import Forest, Item, Node
from udan.core.api_operators import (
    Operator,
    OperatorDescriptor,
)
from udan.core.api_types_registry import TypesRegistryAPI
from udan.core.utils_binding import resolve_fn_args
from udan.core.utils_collections import CachedIterable
from udan.core_tools_loading.api_tools import ToolDescriptor, ToolKind, ToolMetadata
from udan.core_tools_loading.api_tools_registry import ToolsRegistryAPI
from udan.core_tools_loading.api_types import Group
from udan.operator.api_operator_engine import Applicator, OperatorArgs, OperatorsEngineAPI


def _is_operator_item(item: Item) -> bool:
    """Whether this forest item is an operator descriptor: applied, not data.

    The classification the walk is built on, and the operators package's to make -
    the core registry classifies only data versus chain item.

    Args:
        item: Forest item to classify

    Returns:
        True for an operator descriptor
    """
    return isinstance(item, OperatorDescriptor)


class OperatorContext(BaseModel):
    depth: int = 0


class OneShotIterableGuard[T]:
    """Debug-mode wrapper that logs when a one-shot input is iterated more than once.

    Applicators may iterate their input several times (a grouper runs any() before
    its main loop); on a bare generator the second pass silently sees nothing and
    items are lost. The engine hands operators a CachedIterable, so this only ever
    fires for call sites that pass a one-shot iterator directly.
    """

    def __init__(self, source: Iterator[T], ctx: ExecContextAPI, op_d: OD) -> None:
        self._source = source
        self._ctx = ctx
        self._op_d = op_d
        self._passes = 0

    def __iter__(self) -> Iterator[T]:
        self._passes += 1
        if self._passes > 1:
            self._ctx.debug(f"{self._op_d.name}: operator input iterated more than once; items may be lost")
        return self._source


def _guard_one_shot(children: Iterable[Node], ctx: ExecContextAPI, op_d: OD) -> Iterable[Node]:
    """Wrap one-shot inputs in a debug guard; re-iterables pass through untouched."""
    if not ctx.is_debug or iter(children) is not children:
        return children
    return OneShotIterableGuard(children, ctx, op_d)


@dataclass
class OperatorImpl(Operator):
    op_d: OperatorDescriptor
    op_fn: Callable
    op_applicator: Applicator
    operator_engine: OperatorsEngineAPI | None = None

    def _mark_with_source_info(self, nodes: Iterable[Node]) -> Iterable[Node]:
        """Mark nodes with source operator information.

        Args:
            nodes: Nodes to mark with source info

        Yields:
            Nodes with source_operator and origin_chain fields set

        Note:
            Only marks nodes with empty origin_chain (newly created nodes).
            Nodes with existing origin are passed through unchanged.
        """
        operator_identity = self.op_d.name

        def add_grouper_to_descendants(node: Node, op_d: OD) -> Node:
            """Recursively add grouper to origin_chain of all descendants.

            Skip adding to Groups that were just created by this grouper
            (i.e., op_d is already at the end of their origin_chain).
            """
            # For Groups: only add op_d if it's not already the last entry in origin_chain
            # This prevents adding the same grouper twice to newly created nested Groups
            if isinstance(node.item, Group) and node.origin_chain and node.origin_chain[-1] == op_d:
                # This Group was just created by this grouper, don't add again
                updated_children = [add_grouper_to_descendants(child, op_d) for child in node.children]
                return node.model_copy(update={"children": updated_children})

            new_origin_chain = list(node.origin_chain) + [op_d]
            updated_children = [add_grouper_to_descendants(child, op_d) for child in node.children]
            return node.model_copy(update={"origin_chain": new_origin_chain, "children": updated_children})

        for node in nodes:
            if isinstance(node, Node):
                # Only mark nodes with empty origin_chain (newly created by this operator)
                # Nodes with existing origin were created by previous operators
                if node.origin_chain:
                    yield node
                    continue

                if isinstance(node.item, Group):
                    # For Group nodes: add grouper to origin
                    # Groups are structural containers created by grouper operators
                    # The grouper affects the position of both the Group and its children
                    new_origin_chain = list(node.origin_chain) + [self.op_d]
                    updated_node = node.model_copy(
                        update={
                            "source_operator": operator_identity,
                            "origin_chain": new_origin_chain,
                        }
                    )
                    # Recursively add grouper to all descendants' origin_chain
                    updated_node = add_grouper_to_descendants(updated_node, self.op_d)
                    yield updated_node
                else:
                    # For regular nodes, append operator descriptor to origin_chain
                    # Create a new origin_chain list with this operator appended
                    new_origin_chain = list(node.origin_chain) + [self.op_d]
                    updated_node = node.model_copy(
                        update={
                            "source_operator": operator_identity,
                            "origin_chain": new_origin_chain,
                        }
                    )
                    yield updated_node
            else:
                yield node

    def apply(self, ctx: ExecContextAPI, attr_ctx: ChainContextAPI, children: Iterable[Node]) -> Iterable[Node]:
        octx = OperatorContext()
        op_d, op_fn, op_ap = self.op_d, self.op_fn, self.op_applicator
        # resolve() returns base ToolMetadata; operators need the OperatorMetadata subclass
        binding = attr_ctx.registry.resolve(op_d)
        op_m = binding.metadata

        # Resolve dependency args (operator-specific logic)
        per_item_attrs: dict[str, AttributeDescriptor] = {}
        pre_resolved_deps: dict[str, Any] = {}
        dep_param_names: set[str] = set()
        if isinstance(op_m, ToolMetadata) and op_m.dependencies:
            dep_param_names = set(op_m.dependencies.keys())
            for param_name, dep_name in op_m.dependencies.items():
                if dep_name is None:
                    # @attribute marker: extract from op_d args for per-item resolution
                    attr_d = _extract_attribute_descriptor_from_args(op_d)
                    if attr_d is not None:
                        per_item_attrs[param_name] = attr_d
                else:
                    # Resolve attribute value from operator's user args
                    attr_value = _resolve_dependency_attribute(attr_ctx, dep_name, dict(op_d.args))
                    pre_resolved_deps[param_name] = attr_value

        args_dict = resolve_fn_args(
            op_fn, dict(op_d.args), dep_param_names=dep_param_names, pre_resolved_deps=pre_resolved_deps
        )
        if self.operator_engine is not None:
            args_dict = self.operator_engine.resolve_typed_variable_arguments(op_fn, args_dict, ctx, attr_ctx)

        # Pre-extract operator metadata for applicators
        op_args = OperatorArgs(
            is_nested=op_m.is_nested,
            on_depth=_get_on_depth(op_d),
            max_depth=op_d.get_max_depth(),
            position=_get_position(op_d),
            per_item_attrs=per_item_attrs,
        )

        result_nodes = op_ap(args_dict, op_fn, ctx, attr_ctx, _guard_one_shot(children, ctx, op_d), octx.depth, op_args)
        # Mark result nodes with source info
        yield from self._mark_with_source_info(result_nodes)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(fn={self.op_d.name})"


OD = OperatorDescriptor


def _get_on_depth(op_d: OD) -> DepthSelector | None:
    """Extract on_depth value from operator special args."""
    for key, value in op_d.tool_args:
        if key == ARG_ON_DEPTH:
            return value
    return None


def _get_position(op_d: OD) -> tuple[int, ...] | None:
    """Extract the hierarchical position path from operator special args.

    The empty path means no position, so it reads back as None however it got into the
    descriptor - the query side drops it, but a hand-built one can carry it.
    """
    for key, value in op_d.tool_args:
        if key == ARG_POSITION:
            return value or None
    return None


def _extract_attribute_descriptor_from_args(op_d: OD) -> AttributeDescriptor | None:
    """Extract AttributeDescriptor from operator args for @attribute marker.

    Checks 'attribute' and 'at_d' arg names.

    Args:
        op_d: Operator descriptor containing args

    Returns:
        AttributeDescriptor if found, None otherwise
    """
    args_dict = dict(op_d.args)
    for key in ("attribute", "at_d"):
        if key in args_dict:
            arg_value = args_dict[key]
            if isinstance(arg_value, AttributeDescriptor):
                return arg_value
            elif isinstance(arg_value, str):
                return AttributeDescriptor.create(arg_value)
    return None


def _resolve_dependency_attribute(
    attr_ctx: ChainContextAPI,
    attr_name: str,
    user_args: dict[str, Any],
) -> Any:
    """Resolve an attribute dependency value from operator user args.

    Maps the operator's user args to attribute args: first arg becomes the item,
    remaining args are forwarded as attribute kwargs.

    Args:
        attr_ctx: Attributes context for value resolution
        attr_name: Name of the attribute to resolve
        user_args: Operator's user-provided arguments

    Returns:
        The resolved attribute value
    """
    first_value = None
    attr_args: dict[str, Any] = {}
    for i, (key, value) in enumerate(user_args.items()):
        if i == 0:
            first_value = value
        elif key != attr_name:
            attr_args[key] = value
    at_d = AttributeDescriptor.create(attr_name, args=attr_args)
    return attr_ctx.get_value(at_d, first_value)


class OperatorsEngineImpl(OperatorsEngineAPI):
    """Handles operator application to tree structures.

    This is the implementation of OperatorsEngineAPI.
    The API documentation is in the OperatorsEngineAPI class in api.py.
    """

    def __init__(self, registry: ToolsRegistryAPI, types_registry: TypesRegistryAPI) -> None:
        """Initialize operator engine.

        The dispatch starts empty: the engine owns no applicator of its own - the
        kind services register theirs at container build (register_applicator), so
        a directly-constructed engine applies nothing until one registers.

        Args:
            registry: ToolsRegistry instance for resolving operators
            types_registry: TypesRegistry instance for type checking
        """
        self._registry = registry
        self._types_registry = types_registry
        self._applicators: dict[ToolKind | str, Applicator] = {}

    def register_applicator(self, kind: ToolKind, applicator: Applicator) -> None:
        """Register the applicator of an operator kind whose chain groups another service owns.

        See OperatorsEngineAPI.register_applicator.

        Args:
            kind: The kind the applicator applies
            applicator: The uniform applicator of that kind's operators
        """
        self._applicators[kind] = applicator

    def unregister_applicator(self, kind: ToolKind) -> None:
        """Take a kind's applicator back off the dispatch; see OperatorsEngineAPI.

        Args:
            kind: The kind whose applicator comes off
        """
        self._applicators.pop(kind, None)

    def _resolve_operator(self, op_d: OperatorDescriptor) -> OperatorImpl:
        """Resolve operator descriptor to Operator object.

        Args:
            op_d: Operator descriptor

        Returns:
            Operator object

        Raises:
            ValueError: If operator not found or validation fails
        """
        binding = self._registry.resolve(op_d)
        op_m = binding.metadata
        op_fn = binding.fn
        op_t = op_m.tool_type

        op_ap = self._applicators.get(op_t)
        if not op_ap:
            raise ValueError(f"Operator with type={op_t} not found")
        return OperatorImpl(op_d, op_fn, op_ap, operator_engine=self)

    def resolve_typed_variable_arguments(
        self,
        fn: Callable,
        args_dict: dict[str, Any],
        ctx: ExecContextAPI,
        attr_context: ChainContextAPI | None = None,
    ) -> dict[str, Any]:
        """Resolve variable arguments based on function parameter type annotations.

        For parameters annotated with types like `list`, if the argument is a string
        that matches a variable name, this method looks up the variable and expands
        it to the required type.

        Args:
            fn: Function whose parameters should be resolved
            args_dict: Current argument values (from resolve_depends)
            ctx: Execution context containing symbols_env

        Returns:
            Updated args_dict with variables expanded to required types
        """
        # Use get_type_hints to resolve string annotations to actual types
        try:
            hints = get_type_hints(fn)
        except NameError, TypeError:
            # If get_type_hints fails, fall back to inspect.signature
            hints = {name: param.annotation for name, param in inspect.signature(fn).parameters.items()}

        sig = signature(fn)
        symbols_env = ctx.symbols_env
        if symbols_env is None:
            return args_dict

        resolved_args = dict(args_dict)

        for param_name, param in sig.parameters.items():
            # Skip parameters that aren't in args_dict
            if param_name not in resolved_args:
                continue

            # Get type annotation (from hints if available, otherwise from param.annotation)
            param_type = hints.get(param_name, param.annotation)
            if param_type is param.empty or param_type is inspect.Parameter.empty:
                continue

            # Handle list type annotation (both actual list type and string 'list')
            if param_type is list or (isinstance(param_type, str) and param_type == "list"):
                arg_value = resolved_args[param_name]

                # Check if this is a variable name (string) that exists in symbols
                if isinstance(arg_value, str):
                    if not symbols_env.has_variable(arg_value):
                        raise ValueError(f"Variable '{arg_value}' is not defined")
                    var_value, var_type = symbols_env.get_variable_with_type(arg_value)

                    # If variable is TYPE_QUERY, expand it using operator engine
                    if var_type == TYPE_QUERY and isinstance(var_value, Forest):
                        assert attr_context is not None
                        expanded, _ = self.apply_operators_with_contexts(
                            self._expandable_forest(var_value), ctx, attr_context
                        )
                        resolved_args[param_name] = expanded.items
                    # If variable is TYPE_FOREST, expand to list
                    elif var_type == TYPE_FOREST and isinstance(var_value, Forest):
                        resolved_args[param_name] = var_value.items
                    # If variable is already a list, use it directly
                    elif var_type == TYPE_LIST and isinstance(var_value, list):
                        resolved_args[param_name] = var_value

        return resolved_args

    def _apply_operators_in_forest(
        self, forest: Forest, ctx: ExecContextAPI, attr_context: ChainContextAPI, item_cap: int | None = None
    ) -> Forest:
        """Expand operators in a forest.

        Args:
            forest: Forest with operators to expand
            ctx: Execution context for this query
            attr_context: Attributes context for attribute operations
            attr_storage: Attribute storage for storing attribute values
            item_cap: Optional bound on how many items the last operator may
                produce. Passed to _apply_operators_in_node for the top-level
                chain only.

        Returns:
            Forest with operators applied
        """
        node = forest.convert_to_node()
        ctx.debug(f"Root node before applying operators: {node}")
        self._log_tool_types(node, ctx)
        origin_at_d = AttributeDescriptor.create("origin", args={"node": None})
        node = self._restore_origin_chains(node, attr_context, origin_at_d)
        node_fixed = self._apply_operators_in_node(node, attr_context, ctx, item_cap=item_cap)

        # Extract origin_chain from nodes and store as attribute before forest conversion
        # This is needed because origin_chain is lost when converting to forest (items only)
        def store_origin_from_node(node: Node) -> None:
            """Recursively extract origin_chain from nodes and store in attributes."""
            # Store origin_chain for all items (including Groups which now have origin)
            if node.origin_chain:
                attr_context.set_value(origin_at_d, node.item, list(node.origin_chain))
            # Recursively process children
            for child in node.children:
                store_origin_from_node(child)

        store_origin_from_node(node_fixed)

        forest_fixed = node_fixed.convert_to_forest()
        # Operator application does not change the level types: the descriptor
        # travels with the node tree (_convert_forest_to_node put it there) and
        # comes back with the conversion above
        return forest_fixed

    def _restore_origin_chains(
        self, node: Node, attr_context: ChainContextAPI, origin_at_d: AttributeDescriptor
    ) -> Node:
        """Re-attach the origin chains the previous chain group stored for its items.

        A chain group's stage travels as a Forest - items only - so the origin chains
        the group's walk marked are carried out of it as the `origin` attribute (the
        store in _apply_operators_in_forest) and come back here, before this group's
        operators run: an operator appends itself to the chain its input already
        carries, the way it does inside a single walk. A node the storage holds
        nothing for keeps its empty chain, the way a fresh item has none.

        Args:
            node: Root node of the stage about to enter the operators phase
            attr_context: Attributes context whose storage holds the chains
            origin_at_d: The descriptor the chains are stored under

        Returns:
            The stage with the stored chains re-attached
        """

        def restore(node: Node) -> Node:
            if not node.origin_chain:
                stored = attr_context.get_stored_value(origin_at_d, node.item)
                if stored:
                    node = node.model_copy(update={"origin_chain": list(stored)})
            if node.children:
                node = node.model_copy(update={"children": [restore(child) for child in node.children]})
            return node

        return restore(node)

    def apply_operators_with_contexts(
        self,
        forest: Forest,
        ctx: ExecContextAPI,
        attr_context: ChainContextAPI,
        item_cap: int | None = None,
    ) -> tuple[Forest, ChainContextAPI]:
        """Apply operators to a forest with the given execution context.

        This method applies operators using the provided execution context.
        The attr_context must be created by the caller.

        Args:
            forest: Forest with operator descriptors to apply
            ctx: Execution context (must be provided, created via request-scoped DI)
            attr_context: Attributes context (must be provided by the caller)
            item_cap: Optional bound on how many items the last operator may
                produce (see _apply_operators_in_node)

        Returns:
            Tuple of (Forest with operators applied, ChainContextAPI)
        """

        # Apply operators
        result = self._apply_operators_in_forest(forest, ctx, attr_context, item_cap=item_cap)
        return result, attr_context

    def apply_chain_step(
        self,
        descriptors: list[ToolDescriptor],
        stage: Forest,
        chain_context: ChainContextAPI,
        ctx: ExecContextAPI,
        item_cap: int | None = None,
    ) -> Forest:
        """Apply a run of operators at their chain position; return the next stage.

        A ten-line adapter over the existing application, not a new mechanic: the run
        is wrapped as ROOT[*descriptors, *stage.items] - the shape a variable splice
        already produces - and handed to the ordinary loop, so streaming, the item cap
        and the introspection short-circuit behave exactly as in a whole-forest call.

        Args:
            descriptors: Operator descriptors of the run, in written order
            stage: The forest the chain groups before this one produced
            chain_context: The per-query context of the walk
            ctx: Execution context for dependency injection and query-time logging
            item_cap: Optional bound on how many items the last operator may produce

        Returns:
            The forest the run produced
        """
        run_forest = Forest(
            items=[*descriptors, *stage.items],
            depths=[0] * len(descriptors) + stage.depths,
            types=stage.types,
        )
        return self._apply_operators_in_forest(run_forest, ctx, chain_context, item_cap=item_cap)

    def _expandable_forest(self, forest: Forest) -> Forest:
        """Drop the chain items this engine does not apply from a forest it expands.

        A variable expanded as a value (an operator argument, a variable reference
        node) yields items: its operators apply, its data passes through, and its
        chain items of other kinds are neither - they belong to the chain that
        references the variable, which the orchestrator's walk applies. Skipping them
        keeps them from leaking into the expansion as items.

        Args:
            forest: Resolved forest of a variable about to be expanded

        Returns:
            Forest without the chain items other services handle
        """
        kept = [(depth, item) for depth, item in forest.as_pairs() if not self._foreign_chain_item(item)]
        if len(kept) == len(forest.items):
            return forest
        return Forest(
            depths=[depth for depth, _ in kept],
            items=[item for _, item in kept],
            types=forest.types,
        )

    def _foreign_chain_item(self, item: Item) -> bool:
        """Whether this chain item is applied by a service other than this engine.

        Args:
            item: Item of a forest about to be expanded

        Returns:
            True for a tool descriptor that is not an operator descriptor
        """
        return self._types_registry.is_chain_item(item) and not _is_operator_item(item)

    def _log_tool_types(self, node: Node, ctx: ExecContextAPI) -> None:
        """Log declared item types for every tool found in the tree.

        Debug aid for the item-type contract: runs right before operators are
        applied, so each tool entering the engine is reported with the
        item_type/output_type declared in its metadata.

        Args:
            node: Root node of the forest about to enter the operators phase
            ctx: Execution context for logging
        """
        if _is_operator_item(node.item):
            op_d: OperatorDescriptor = node.item
            op_m = self._registry.get_metadata(op_d.name)
            if op_m is not None:
                ctx.debug(
                    f"tool {op_d.name} ({op_m.tool_type.name}): "
                    f"item_type={op_m.item_type} output_type={op_m.output_type}"
                )
            else:
                ctx.debug(f"tool {op_d.name}: no metadata ({op_m!r})")
        for child in node.children:
            self._log_tool_types(child, ctx)

    def _overrides_output(self, operator: Operator) -> bool:
        """Does the operator's tool declare that its own output replaces the chain's?

        The declaration is the meta key the whole pipeline reads (`range 5, ?`
        shows the listing, not the range): the walk short-circuits it, so the
        listing question and the per-tool docs answer with their own forest
        whatever name they resolve through - the canonical one or an alias.

        Args:
            operator: The resolved operator

        Returns:
            True when the tool declares the output override
        """
        metadata = self._registry.get_metadata(operator.op_d.name)
        return metadata is not None and bool(metadata.meta.get(OVERRIDES_OUTPUT))

    def _handle_output_override(self, operator: Operator, ctx: ExecContextAPI, attr_context: ChainContextAPI) -> None:
        """Handle an output-overriding operator by raising OverrideForestException.

        Args:
            operator: The overriding operator to execute
            ctx: Execution context for dependency injection
            attr_context: Attributes context for attribute operations

        Raises:
            OverrideForestException: Always raised with the operator's result
        """
        # Execute the operator and raise OverrideForestException with the result
        # An overriding operator should not process children - it outputs its own data
        # Pass empty list to avoid yielding children
        result_nodes = list(operator.apply(ctx, attr_context, []))
        # Create a ROOT node to wrap all result nodes
        result_node = Node(item=NODE_ROOT_ITEM, children=result_nodes) if result_nodes else Node.leaf(None)

        # Convert to forest and raise exception
        result_forest = result_node.convert_to_forest()
        # Override results have no declared item types (listing rows)
        raise OverrideForestException(result_forest)

    def _evaluate_operator_item(
        self, operator: Operator, children: list[Node], ctx: ExecContextAPI, attr_context: ChainContextAPI
    ) -> Node:
        """Evaluate a regular (non-introspection) operator item.

        Args:
            operator: The operator to evaluate (already resolved)
            children: Child nodes to pass to the operator
            ctx: Execution context for dependency injection
            attr_context: Attributes context for attribute operations

        Returns:
            Node with the operator applied
        """
        # Execute the operator with current children as input
        result_nodes = list(operator.apply(ctx, attr_context, children))
        # If operator returned no results, return empty node
        if len(result_nodes) == 0:
            return Node.leaf(None)

        # Apply child operators (if any) to all result nodes
        for child in children:
            if _is_operator_item(child.item):
                child_operator = self._resolve_operator(child.item)
                result_nodes = list(child_operator.apply(ctx, attr_context, result_nodes))

        # Recursively process all result nodes and return them
        result_nodes_processed = [self._apply_operators_in_node(n, attr_context, ctx) for n in result_nodes]
        # Return first node with others as children (or just first if that's the only one)
        if len(result_nodes_processed) == 0:
            return Node.leaf(None)
        elif len(result_nodes_processed) == 1:
            return result_nodes_processed[0]
        else:
            # Multiple nodes - create a forest wrapper or return first with others as children
            # For now, return first with others as children
            # IMPORTANT: Use model_copy to preserve origin_chain and other metadata from the first node
            first_node = result_nodes_processed[0]
            return first_node.model_copy(update={"children": result_nodes_processed[1:]})

    def _evaluate_variable(self, var_name: str, ctx: ExecContextAPI, attr_context: ChainContextAPI) -> Node:
        """Evaluate a variable reference from symbols_env.

        Args:
            var_name: Name of the variable (without NODE_VAR_PREFIX)
            ctx: Execution context for dependency injection
            attr_context: Attributes context for attribute operations

        Returns:
            Node with the expanded variable content
        """
        ctx.debug(f"Expanding variable reference: {var_name}")

        # Get the variable from symbols_env
        symbols_env = ctx.symbols_env
        if symbols_env is None or not symbols_env.has_variable(var_name):
            ctx.warning(f"Variable '{var_name}' not defined")
            return Node.leaf(None)

        var_forest, var_type = symbols_env.get_variable_with_type(var_name)
        ctx.debug(f"Expanding variable '{var_name}' with type '{var_type}'")

        # Apply operators to the variable's forest
        var_result = self._apply_operators_in_forest(self._expandable_forest(var_forest), ctx, attr_context)

        # Convert result to node structure
        var_node = var_result.convert_to_node()

        # Return the variable's content as children of a wrapper node
        # For now, return the first child if single, or create a forest node
        if len(var_node.children) == 0:
            return Node.leaf(None)
        elif len(var_node.children) == 1:
            return var_node.children[0]
        else:
            # Multiple children - wrap in a forest node
            return var_node

    def _apply_operators_in_node(  # noqa: PLR0912, PLR0915, C901
        self, node: Node, attr_context: ChainContextAPI, ctx: ExecContextAPI, item_cap: int | None = None
    ) -> Node:
        """Expand operators in a node tree recursively.

        Args:
            node: Node potentially containing operator children
            attr_context: Attributes context for attribute operations
            ctx: Execution context for dependency injection
            item_cap: Optional bound on how many items the last operator of the
                top-level chain may produce. The caller passes the default limit
                when the auto-limit will apply, so lazy sources (db cursors,
                files) stop producing items once the limit is reached instead of
                being fully materialized and truncated afterwards. Only used for
                the top-level call; recursion into children is never capped.

        Returns:
            Node with operators applied

        Note:
            TODO: Fix and generalize variable expansion. Currently checks if item starts with 'var_'
            and expands variables from symbols_env. This should be generalized for other reference types.
        """

        children = node.children
        item = node.item

        # TODO: Fix and generalize variable expansion.
        # Check if this is a variable reference (starts with NODE_VAR_PREFIX)
        # If yes, expand it by getting the variable from symbols_env and applying its operators
        if isinstance(item, str) and item.startswith(NODE_VAR_PREFIX):
            var_name = item[len(NODE_VAR_PREFIX) :]
            return self._evaluate_variable(var_name, ctx, attr_context)

        # If the item itself is an operator (e.g., from an inserter returning OperatorDescriptors),
        # execute it and use its result as the new structure
        if _is_operator_item(item):
            operator = self._resolve_operator(item)
            ctx.debug(f"applying operator from item: {operator}")

            # An output-overriding tool answers with its own forest
            if self._overrides_output(operator):
                self._handle_output_override(operator, ctx, attr_context)

            return self._evaluate_operator_item(operator, children, ctx, attr_context)

        # Separate operator nodes from regular nodes
        children_operators = [ch for ch in children if _is_operator_item(ch.item)]
        children_fixed: Iterable[Node] = [ch for ch in children if not _is_operator_item(ch.item)]
        # ctx.debug(f"{children_operators=}")
        # ctx.debug(f"{children_fixed=}")

        # Separate output-overriding operators from regular operators
        overriding_operators = []
        regular_operators = []
        for operator_node in children_operators:
            operator = self._resolve_operator(operator_node.item)
            if self._overrides_output(operator):
                overriding_operators.append((operator_node, operator))
            else:
                regular_operators.append((operator_node, operator))

        # If there are overriding operators, only execute the last one
        # Later operators override earlier ones for inserters
        if overriding_operators:
            _, last_op = overriding_operators[-1]
            self._handle_output_override(last_op, ctx, attr_context)

        # Apply regular operators in sequence
        last_operator_index = len(regular_operators) - 1
        for i, (operator_node, operator) in enumerate(regular_operators):
            # Hand the next operator a re-iterable stage instead of a list, so
            # per-item operators stream: a stage pulls from its input only as
            # far as the following stage (or the cap) actually consumes.
            ctx.debug(f"applying operator: {operator}")
            result_nodes = operator.apply(ctx, attr_context, children_fixed)
            if i == last_operator_index and item_cap is not None:
                # The last operator's output becomes the result forest, so a
                # consumer that stops at item_cap still yields a prefix that
                # flattens to at least item_cap items. Bound the pull here so
                # lazy sources are not drained; the caller truncates the
                # flattened forest to the exact limit afterwards.
                children_fixed = CachedIterable(islice(result_nodes, item_cap))
            else:
                children_fixed = CachedIterable(result_nodes)

        # Recursively expand operators in children
        attr_context.depth += 1
        children_fixed = [self._apply_operators_in_node(child_f, attr_context, ctx) for child_f in children_fixed]

        # IMPORTANT: Use model_copy to preserve origin_chain and other metadata from the original node
        return node.model_copy(update={"children": children_fixed})
