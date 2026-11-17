"""Query processing engine.

This module contains the core logic for walking query trees and resolving
tools (operators and attributes) from parsed nodes.
"""

import inspect
import re
from collections.abc import Callable, Mapping
from functools import partial
from typing import Any

from Levenshtein import distance as levenshtein_distance

from udan.core.api_attributes import (
    ATTRIBUTE,
    FRAMEWORK_PARAMS_ATTR,
    AttributeDescriptor,
    AttributeMetadata,
)
from udan.core.api_constants import (
    ARG_ON_DEPTH,
    ARG_POSITION,
    DEBUG,
    DEBUG_TIME,
    NODE_ASSIGN_PREFIX,
    NODE_ROOT_ITEM,
    NODE_STRING_PREFIX,
    NODE_VAR_PREFIX,
    NOLIMIT_TOKEN,
    TYPE_FOREST,
    TYPE_INT,
    TYPE_LIST,
    TYPE_QUERY,
    TYPE_STR,
    WANTS_ITEM_TYPES,
)
from udan.core.api_descriptor_factory import DescriptorFactoryAPI
from udan.core.api_exceptions import ExceptionWithAdvice
from udan.core.api_exec_context import ExecContextAPI
from udan.core.api_forests import Forest, Item, Node
from udan.core.api_item_types import ITEM_TYPE_ANY, accepted_item_types
from udan.core.api_operators import (
    OperatorDescriptor,
)
from udan.core.api_query_processor import (
    QueryMiss,
    QueryProcessorAPI,
)
from udan.core.api_symbols_env import SymbolsEnvAPI
from udan.core.api_type_system import ForestTypeDescriptor, TypeSystemAPI
from udan.core.api_variable_handler import VariableHandlerAPI
from udan.core.utils_binding import (
    convert_string_value,
)
from udan.core_tools_loading.api_annotated import unwrap_function
from udan.core_tools_loading.api_tools import ToolMetadata
from udan.core_tools_loading.api_tools_registry import ToolsRegistryAPI
from udan.core_tools_loading.api_types import TypeDescriptor
from udan.renders.api_renders import RENDER, RenderDescriptor, is_aggregate_render

_MAX_SIMILAR_SUGGESTIONS = 10
# Maximum Levenshtein distance between an unknown name and a suggested one.
# Kept small so that a typo yields a few close candidates instead of an
# arbitrary slice of the whole registry.
_MAX_SIMILAR_SUGGESTION_DISTANCE = 2

# A bare number token: digits with an optional decimal part.
_NUMBER_PATTERN = re.compile(r"\d+(?:\.\d+)?")


def _number_literal(item: object) -> int | float | None:
    """Numeric value of a bare number query item, None when the item is not one.

    A bare number ("3", "3.5") is literal data in any chain position, like a
    quoted string; every other bare word is a tool name. Signed and
    exponent forms ("-3", "1e3") are not literals: they stay bare words and
    report the bare-literal error.

    Args:
        item: The query node item

    Returns:
        The number as int or float, or None when the item is not a number
    """
    if not isinstance(item, str) or not _NUMBER_PATTERN.fullmatch(item):
        return None
    return float(item) if "." in item else int(item)


def _annotate_chain_item_types(node: Node, ftd: ForestTypeDescriptor, metadatas: Mapping[str, ToolMetadata]) -> Node:
    """Append the chain's item types to a descriptor whose tool asks for them.

    A tool can be chain-blind: what it lists or suggests depends on the types
    built so far at its chain position, which only the resolver knows. Such a
    tool declares ``WANTS_ITEM_TYPES`` in its meta (the same declaration shape
    as ``OVERRIDES_OUTPUT`` - the core reads the key, the vocabulary stays with
    the declaring tool), and the resolver hands the types over as the
    ``item_types`` arg. An empty chain annotates nothing: there is nothing to
    hand over.

    Args:
        node: Resolved chain item node
        ftd: Forest type descriptor of this expression's chain built so far
        metadatas: Registered tool metadatas, by name or alias

    Returns:
        Node whose descriptor carries the item_types arg, unchanged otherwise
    """
    item = node.item
    if not isinstance(item, OperatorDescriptor):
        return node
    metadata = metadatas.get(item.name)
    if metadata is None or not metadata.meta.get(WANTS_ITEM_TYPES):
        return node
    levels = [depth.name for depth in ftd.depths]
    if not levels:
        return node
    op_d = OperatorDescriptor.create(item.name, [*item.args, ("item_types", ",".join(levels))])
    return Node.create(item=op_d, children=node.children)


def _infer_variable_type(forest: Forest) -> str:
    """Infer the symbol type of a resolved forest: query, forest, list, str or int.

    The type decides how a `$var` reference expands: a query re-runs its operators, a
    forest expands to its items, the rest are values. A forest holding operator
    descriptors is a query - descriptors are the chain items, and their presence means
    the variable still has operators to apply.

    Args:
        forest: Resolved (unexpanded) forest of an assignment expression

    Returns:
        The TYPE_* name of the forest's content
    """
    items = forest.items
    # A query: it still has chain items to apply
    if any(isinstance(item, OperatorDescriptor) for item in items):
        return TYPE_QUERY
    if forest.depths and max(forest.depths) > 0:
        return TYPE_FOREST
    if len(items) == 0:
        return TYPE_LIST
    if len(items) == 1:
        item = items[0]
        if isinstance(item, str):
            return TYPE_STR
        if isinstance(item, int):
            return TYPE_INT
    return TYPE_LIST


class QueryProcessor(QueryProcessorAPI):
    """Handles query processing and conversion to forest.

    This is the implementation of QueryProcessorAPI.
    The API documentation is in the QueryProcessorAPI class in api.py.
    """

    def __init__(
        self,
        registry: ToolsRegistryAPI,
        type_system: TypeSystemAPI,
        udan_tools_preferences_input: dict[str, str],
        symbols_env: SymbolsEnvAPI,
        variable_handler: VariableHandlerAPI,
        descriptor_factory: DescriptorFactoryAPI,
    ) -> None:
        """Initialize query processor.

        Args:
            registry: ToolsRegistryAPI instance for accessing metadata
            type_system: TypeSystemAPI instance for folding forest type descriptors
            udan_tools_preferences_input: User input preferences for tools
            symbols_env: SymbolsEnvAPI instance for variable management
            variable_handler: VariableHandlerAPI for handling variable assignments and references
            descriptor_factory: DescriptorFactoryAPI for creating operator and attribute descriptors
        """
        self._registry = registry
        self._type_system = type_system
        self._udan_tools_preferences_input = udan_tools_preferences_input
        self._symbols_env = symbols_env

        self._variable_handler: VariableHandlerAPI = variable_handler
        self._descriptor_factory: DescriptorFactoryAPI = descriptor_factory

    # ========================================================================
    # UTILITY METHODS (moved from module-level functions)
    # ========================================================================

    def _format_tool(self, tool_key: str) -> str:
        """Format a single tool with domain-qualified name.

        Args:
            tool_key: Tool key to format

        Returns:
            Formatted tool name
        """
        metadata = self._registry.get_metadata(tool_key)
        if metadata:
            domain = metadata.meta.get("domain", "")
            if domain and domain != "builtins":
                return f"{domain}.{tool_key}"
        return tool_key

    def _format_tools_list(self, tools_keys: list[str]) -> str:
        """Format a list of tools with domain-qualified names.

        Args:
            tools_keys: List of tool keys to format

        Returns:
            Formatted string with one tool per line
        """
        formatted_list = []
        for tool_key in tools_keys:
            formatted_name = self._format_tool(tool_key)
            formatted_list.append(f"  - {formatted_name}")
        return "\n".join(formatted_list)

    def _is_string_literal_node(self, node: Node) -> bool:
        """Check if a node is a string literal (starts with NODE_STRING_PREFIX)."""
        return isinstance(node.item, str) and node.item.startswith(NODE_STRING_PREFIX)

    def _is_render_spec_node(self, node: Node) -> bool:
        """Check if a node is a render specification (starts with ':')."""
        return isinstance(node.item, str) and node.item.startswith(":") and not node.item.startswith(":=")

    def _is_inserter_node(self, node: Node) -> bool:
        """Check if a node resolves to an inserter tool.

        Only checks the top-level item (not children of application nodes).
        """
        item = node.item
        if not isinstance(item, str):
            return False

        # Application nodes (with children) may be inserters with args
        # Bare nodes (without children) are checked directly
        metadata = self._registry.get_metadata(item)
        # the inserter kind is a plugin kind, so the check matches the kind by name
        if metadata and metadata.tool_type == "inserter":
            return True
        return False

    def _validate_chain(self, chain_children: list[Node]) -> None:
        """Validate that a chain has at most one data source.

        A chain must be: [inserter_or_literal, operator, operator, ...]
        At most one child can be an inserter, a string literal, or a bare number.
        Renders are allowed anywhere (they don't produce data).

        Args:
            chain_children: Children of a CHAIN node

        Raises:
            ExceptionWithAdvice: If the chain is invalid
        """
        data_source_count = 0
        first_data_source_label: str | None = None
        second_data_source_label: str | None = None

        for child in chain_children:
            # Skip renders -- they don't count as data sources
            if self._is_render_spec_node(child):
                continue

            # Skip assignments -- they store data, don't produce it
            if isinstance(child.item, str) and child.item.startswith(":="):
                continue

            # Skip ROOT nodes (subqueries) -- they are opaque containers
            # that produce a single combined result, regardless of their contents
            if isinstance(child.item, str) and child.item == NODE_ROOT_ITEM:
                continue

            is_data_source = False
            label = repr(child.item)

            if self._is_string_literal_node(child) or _number_literal(child.item) is not None:
                is_data_source = True
            elif self._is_inserter_node(child):
                is_data_source = True

            if is_data_source:
                data_source_count += 1
                if first_data_source_label is None:
                    first_data_source_label = label
                elif second_data_source_label is None:
                    second_data_source_label = label

        if data_source_count > 1:
            raise ExceptionWithAdvice(
                f"Invalid chain: multiple data sources (inserter or literal) in a single chain.\n"
                f"Found: {first_data_source_label}, {second_data_source_label}\n"
                f"Use semicolon (;) to separate independent chains.\n"
                f"Example: 'inserter1 arg; inserter2 arg' instead of 'inserter1 arg, inserter2 arg'"
            )

    def _desugar_subqueries(self, node: Node, parent_item: str | None = None) -> Node:
        """Desugar parenthesized subqueries into anonymous variable assignments.

        Transforms expressions like:
            difference (range 3) (range 1 4)

        Into:
            :=_anon0 (range 3)
            :=_anon1 (range 1 4)
            difference _anon0 _anon1

        This allows set operations to accept inline subqueries as arguments instead of
        requiring pre-assigned variables.

        Note: Only desugars ROOT nodes when they are children of set operations
        (difference, union, intersect, symmetric_difference) to avoid breaking
        parameterized attribute syntax like (attr_name arg).

        Args:
            node: Query node to transform
            parent_item: Parent node's item (to determine if we should desugar)

        Returns:
            Transformed node with subqueries converted to anonymous variable assignments.
            If assignments were created, returns a ROOT node with assignments as
            siblings of the transformed node.
        """
        if not node.children:
            return node

        # Set operations that should trigger subquery desugaring
        set_operations = {"difference", "union", "intersect", "symmetric_difference"}
        # Check if current node or parent is a set operation
        current_is_set_op = isinstance(node.item, str) and node.item in set_operations
        should_desugar = current_is_set_op or (parent_item in set_operations)

        # Collect assignments and build new children list
        all_assignments = []
        new_children = []

        for child in node.children:
            # Check if this is an assignment node - don't desugar into it
            # (we don't want to treat (range 5) in "a := (range 5)" as a subquery)
            is_assignment = isinstance(child.item, str) and child.item.startswith(":=")

            if not is_assignment and child.item == NODE_ROOT_ITEM and len(child.children) == 1 and should_desugar:
                # This is a parenthesized subquery in a set operation - create anonymous variable assignment
                var_name = self._variable_handler.get_anon_var_name()
                # Recursively desugar the subquery expression (pass current node's item as parent)
                desugared_child = self._desugar_subqueries(child.children[0], node.item)
                assignment = Node.create(f"{NODE_ASSIGN_PREFIX}{var_name}", [desugared_child])
                all_assignments.append(assignment)
                # Replace subquery with variable reference (using NODE_VAR_PREFIX)
                new_children.append(Node.leaf(f"{NODE_VAR_PREFIX}{var_name}"))
            # For assignments: don't recursively desugar, keep as-is
            elif is_assignment:
                new_children.append(child)
            else:
                # Recursively desugar non-assignment nodes
                # For CHAIN nodes, propagate the parent_item so set operations
                # inside chains are still detected
                effective_parent = parent_item if node.item == "CHAIN" else node.item
                desugared = self._desugar_subqueries(child, effective_parent)
                # If the child produced assignments (returned ROOT with assignments),
                # extract and hoist them.  Only hoist from ROOT nodes that actually
                # contain assignment nodes — a plain ROOT (e.g. a parenthesized group
                # like (range 5; range 3)) must be kept as-is so the chain validator
                # and executor can handle it correctly.
                if isinstance(desugared.item, str) and desugared.item == NODE_ROOT_ITEM:
                    has_assignments = any(
                        isinstance(gc.item, str) and gc.item.startswith(NODE_ASSIGN_PREFIX) for gc in desugared.children
                    )
                    if has_assignments:
                        # Separate assignments from the transformed child
                        for gc in desugared.children:
                            if isinstance(gc.item, str) and gc.item.startswith(NODE_ASSIGN_PREFIX):
                                all_assignments.append(gc)
                            else:
                                new_children.append(gc)
                    else:
                        # No assignments: keep the ROOT as-is (parenthesized group)
                        new_children.append(desugared)
                else:
                    new_children.append(desugared)

        # Create new node with variable references instead of subqueries
        new_node = Node(item=node.item, children=new_children)

        # Return ROOT containing assignments followed by the transformed node
        if all_assignments:
            # If the original node was already ROOT, flatten to avoid nested ROOTs
            if node.item == NODE_ROOT_ITEM:
                return Node(item=NODE_ROOT_ITEM, children=all_assignments + [new_node])
            else:
                # Wrap in ROOT with assignments at top level
                return Node(item=NODE_ROOT_ITEM, children=all_assignments + [new_node])
        else:
            return new_node

    # ========================================================================
    # PUBLIC METHODS
    # ========================================================================

    def _flatten_root_nodes(self, node: Node) -> Node:
        """Recursively flatten nested ROOT nodes.

        When desugaring produces ROOT [assign, ROOT [content]], this merges
        the inner ROOT's children into the outer ROOT.

        Args:
            node: Node to flatten

        Returns:
            Flattened node
        """
        if not isinstance(node.item, str) or node.item != NODE_ROOT_ITEM:
            return node
        new_children = []
        for child in node.children:
            flattened = self._flatten_root_nodes(child)
            if isinstance(flattened.item, str) and flattened.item == NODE_ROOT_ITEM:
                new_children.extend(flattened.children)
            else:
                new_children.append(flattened)
        return Node(item=NODE_ROOT_ITEM, children=new_children)

    def resolve_query(
        self, query_node: Node, ctx: ExecContextAPI
    ) -> tuple[Forest, list[AttributeDescriptor], list[RenderDescriptor]]:
        """Resolve query node to forest, attributes, and renders.

        Variables store unexpanded forests (with operator descriptors).
        When referenced, the forest's structure is merged into the query tree.
        Operators are applied later by the caller (UdanContext).

        Args:
            query_node: Query node to process
            ctx: Execution context for dependency injection and query-time logging

        Returns:
            Tuple of (forest, attribute_descriptors, render_tools).
            The forest carries the folded forest type descriptor in its
            ``types`` field; the returned attribute_descriptors list equals
            ``forest.types.flattened_requested()``.
        """
        # Desugar parenthesized subqueries into anonymous variable assignments
        # Transforms: difference (range 3) (range 1 4)
        # Into:       :=_anon0 (range 3), :=_anon1 (range 1 4), difference _anon0 _anon1
        query_node = self._desugar_subqueries(query_node)
        query_node = self._flatten_root_nodes(query_node)

        at_ds, render, children, ftd = self._process_query_children(query_node, ctx)

        # Filter out the None markers; every descriptor stays in the tree - the chain
        # the orchestrator walks is these children in written order, operators and
        # attributes alike (attributes also stay in the returned at_ds)
        children = [ch for ch in children if ch is not None]
        node = Node(item=NODE_ROOT_ITEM, children=children)

        # Renders on a sourceless chain apply to nothing: report the missing data source
        self._type_system.require_source_for_output(ftd, render, node)

        forest = node.convert_to_forest()
        # Fold the forest type descriptor onto the forest for on-demand
        # attribute calculation; it replaces the flat requested-attribute list
        forest.types = ftd

        # The whole resolved state in one line: every chain descriptor in written
        # order, operators and attributes alike (per-descriptor lines above only
        # show each tool at its own resolution moment)
        ctx.debug(f"resolved state: {[ch.item for ch in node.children]}")

        # If no explicit render specs, check for supported_renders from operators
        if not render:
            # Collect supported_renders from operator metadata
            supported_renders = self._collect_supported_renders(node)
            if supported_renders:
                ctx.debug(f"Collected supported_renders: {[(r.name, r.args) for r in supported_renders]}")
                # Use the LAST operator's supported_renders (most recent in the sequence)
                # This is important for queries like "fruits, ?" where we want the
                # question descriptor's render, not the first operator's render
                # Marked from_supported so frontends can treat it as "no user render"
                render = [supported_renders[-1].model_copy(update={"from_supported": True})]
        elif self._first_item_render(render) is None:
            # Aggregate-only renders (:list, :org-structure, ...) wrap per-item lines
            # instead of replacing them, so the items still need a per-item render:
            # take the operator's supported one (e.g. commits + :list renders the
            # commit-log line inside the list)
            item_render = self._last_supported_item_render(node)
            if item_render is not None:
                ctx.debug(f"Aggregate-only renders, appending supported item render: {item_render.name}")
                render.append(item_render.model_copy(update={"from_supported": True}))

        return forest, at_ds, render

    def _process_query_children(
        self, query_node: Node, ctx: ExecContextAPI
    ) -> tuple[list[AttributeDescriptor], list[RenderDescriptor], list[Node], ForestTypeDescriptor]:
        """Process query node children and extract attribute descriptors, renders, and types.

        This handles variable assignments, variable references, and regular query
        interpretation, returning the processed children along with collected
        attribute descriptors, render tools, and the folded forest type
        descriptor.

        Args:
            query_node: Query node whose children should be processed
            ctx: Execution context for dependency injection and query-time logging

        Returns:
            Tuple of (attribute_descriptors, render_tools, children_nodes, types)
        """
        at_ds: list[AttributeDescriptor] = []
        render: list[RenderDescriptor] = []
        ftd = ForestTypeDescriptor()
        # Note: last_operator is reset for each top-level expression to avoid cross-contamination
        # between separate expressions in comma-separated lists (e.g., "fruits, ?")
        children = []
        for query_ch in query_node.children:
            # Unwrap ROOT nodes that contain a single child
            # This handles cases like (intersect x y) where the entire query is wrapped in parens
            node_to_process = query_ch
            if isinstance(query_ch.item, str) and query_ch.item == NODE_ROOT_ITEM and len(query_ch.children) == 1:
                node_to_process = query_ch.children[0]

            # Check for variable assignments BEFORE calling interpret
            # Handle both manual assignments (:=var) and anonymous (__ASSIGN__var)
            is_assignment = False
            var_name = None
            if isinstance(node_to_process.item, str):
                if node_to_process.item.startswith(NODE_ASSIGN_PREFIX):
                    # Anonymous assignment from subquery desugaring
                    is_assignment = True
                    var_name = node_to_process.item[len(NODE_ASSIGN_PREFIX) :]
                elif node_to_process.item.startswith(":="):
                    # Manual assignment: :=var_name
                    is_assignment = True
                    var_name = node_to_process.item[2:]  # Remove := prefix

            if is_assignment:
                assert var_name is not None
                ctx.debug(f"Processing assignment for variable '{var_name}'")

                # Evaluate the child expression to get the Forest
                if node_to_process.children:
                    # Validate chain if RHS is a CHAIN node
                    rhs = node_to_process.children[0]
                    if isinstance(rhs.item, str) and rhs.item == "CHAIN":
                        self._validate_chain(rhs.children)
                    # Create a temporary ROOT with the assignment expression
                    temp_node = Node(item=NODE_ROOT_ITEM, children=node_to_process.children)
                    # Resolve to get Forest with operator descriptors (UNEXPANDED)
                    temp_forest, _, _ = self.resolve_query(temp_node, ctx)
                    # Infer type from forest content
                    var_type = _infer_variable_type(temp_forest)
                    # Store with type
                    self._symbols_env.set_variable(var_name, temp_forest, type=var_type, ctx=ctx)
                    ctx.debug(
                        f"Stored variable '{var_name}' with type '{var_type}' and "
                        f"{len(temp_forest.items)} items (unexpanded)",
                    )
                # Don't add assignment to the tree
                continue

            chain_items = self._collect_chain_items(node_to_process)
            child_nodes, ftd = self._interpret_chain_items(chain_items, at_ds, render, ftd, ctx)
            children.extend(child_nodes)

        return at_ds, render, children, ftd

    def _collect_chain_items(self, node_to_process: Node) -> list[Node]:
        """Collect and expand chain items from a CHAIN or single node.

        Handles CHAIN unwrapping and expansion of multi-child ROOT nodes
        (parenthesized groups like ``(range 5; range 3)``) into individual items.
        """
        if isinstance(node_to_process.item, str) and node_to_process.item == "CHAIN":
            self._validate_chain(node_to_process.children)
            chain_items = node_to_process.children
        else:
            chain_items = [node_to_process]

        # Expand multi-child ROOT nodes within chain items.
        # e.g., (range 5; range 3), sort → the parenthesized group is a
        # ROOT with 2 children that should be interpreted individually.
        final_items: list[Node] = []
        for ci in chain_items:
            if isinstance(ci.item, str) and ci.item == NODE_ROOT_ITEM and len(ci.children) > 1:
                for root_child in ci.children:
                    # Unwrap single-child ROOT wrappers
                    child = root_child
                    if isinstance(child.item, str) and child.item == NODE_ROOT_ITEM and len(child.children) == 1:
                        child = child.children[0]
                    # If the expanded child is itself a CHAIN, validate and unwrap
                    if isinstance(child.item, str) and child.item == "CHAIN":
                        self._validate_chain(child.children)
                        final_items.extend(child.children)
                    else:
                        final_items.append(child)
            else:
                final_items.append(ci)

        return final_items

    def _interpret_chain_items(
        self,
        chain_items: list[Node],
        at_ds: list[AttributeDescriptor],
        render: list[RenderDescriptor],
        ftd: ForestTypeDescriptor,
        ctx: ExecContextAPI,
    ) -> tuple[list[Node], ForestTypeDescriptor]:
        """Interpret a list of chain items and return the resulting nodes and forest types.

        Handles variable reference expansion and regular interpretation. The
        forest type descriptor is folded with `_types_after` per chain item, in
        the same order the engine will apply the operators; attributes collected
        by an item are attached to the deepest level existing at that position.

        Args:
            chain_items: Chain items (already collected and expanded)
            at_ds: List to collect attribute descriptors (appended by interpretation)
            render: List to collect render tools
            ftd: Forest type descriptor before this chain
            ctx: Execution context for dependency injection and query-time logging

        Returns:
            Tuple of (resulting nodes, forest type descriptor after the chain)
        """
        results: list[Node] = []
        # The completions context folds this expression alone: `;` starts a fresh chain,
        # while ftd spans the whole query (see _process_query_children)
        expr_ftd = ForestTypeDescriptor()
        for chain_item in chain_items:
            at_ds_before = len(at_ds)
            last_operator: list = []
            try:
                result = self._interpret_query(chain_item, at_ds, render, last_operator, ctx)
            except QueryMiss as miss:
                # Nothing found: the wrapped-in answer (answer_miss) is asked for the
                # query that answers the miss, which continues the pipeline instead
                # of the item - interpreted like any chain item, annotated with the
                # chain types below, and presented by the render engine
                ctx.warning(miss.reason)
                answered = self.answer_miss(miss)
                if answered is None:
                    raise ExceptionWithAdvice(f"{miss.reason} - nothing answers it") from None
                try:
                    result = self._interpret_query(answered, at_ds, render, last_operator, ctx)
                except QueryMiss:
                    # The answer found nothing itself (its tool is not registered)
                    raise ExceptionWithAdvice(f"{miss.reason} - nothing answers it") from None

            # Handle variable references
            if result and isinstance(result.item, str) and result.item.startswith(NODE_VAR_PREFIX):
                var_name_ref = result.item[len(NODE_VAR_PREFIX) :]  # Remove NODE_VAR_PREFIX
                ctx.debug(f"Expanding variable reference '{var_name_ref}'")
                # Get the variable's forest (contains operator descriptors)
                var_forest, _ = self._symbols_env.get_variable_with_type(var_name_ref)
                # Merge the variable's forest into the current tree
                # Convert forest to node and extract children
                var_node = var_forest.convert_to_node()
                # Add the variable's children to our tree (may contain operator descriptors)
                results.extend(var_node.children)
                # Fold the spliced items too: their descriptors carry the variable's types
                for var_child in var_node.children:
                    ftd = self._types_after(ftd, var_child)
                    expr_ftd = self._types_after(expr_ftd, var_child)
                    # A spliced attribute is a chain item at the splice position: the
                    # orchestrator applies it there, so it belongs to this query's
                    # attribute list (the render footer and the end pass read it)
                    if isinstance(var_child.item, AttributeDescriptor) and var_child.item not in at_ds:
                        at_ds.append(var_child.item)
                continue

            if result is not None:
                result = self._derive_extender_on_depth(result, expr_ftd, ctx)
                result = _annotate_chain_item_types(result, expr_ftd, self._registry.get_metadatas())
                results.append(result)
                ftd = self._types_after(ftd, result)
                expr_ftd = self._types_after(expr_ftd, result)
                for at_d in at_ds[at_ds_before:]:
                    ftd = ftd.with_requested(at_d)
        return results, ftd

    def _derive_extender_on_depth(self, result: Node, ftd: ForestTypeDescriptor, ctx: ExecContextAPI) -> Node:
        """Auto-target an extender at the deepest level whose item type fits its input type.

        An extender in a chain consumes items of its declared input type, but the level
        the previous operator created need not provide it. When a shallower level of the
        chain does, the extender is re-targeted there by deriving the on_depth tool_arg -
        the same depth the user would pass as --on-depth=N. Explicit --on-depth wins,
        and so does an explicit --position: the user named the node there. Undeclared or
        "any" input types and "any" chain levels derive nothing (unknown must not guess,
        mirroring is_item_type_accepted).

        Args:
            result: Resolved chain item node
            ftd: Forest type descriptor of this expression's chain built so far
            ctx: Execution context for query-time logging

        Returns:
            Node whose extender descriptor carries the derived on_depth, or the node unchanged
        """
        item = result.item
        if not isinstance(item, OperatorDescriptor):
            return result
        op_m = self._registry.get_metadata(item.name)
        # The extender kind lives in its plugin package, so the guard matches by name
        # until the "the resolver retargets extenders" rule becomes a kind declaration
        if op_m is None or op_m.tool_type != "extender":
            return result
        if any(arg_k in (ARG_ON_DEPTH, ARG_POSITION) for arg_k, _ in item.tool_args):
            return result
        item_type = op_m.item_type
        levels = [depth.name for depth in ftd.depths]
        if not item_type or item_type == ITEM_TYPE_ANY or not levels or ITEM_TYPE_ANY in levels:
            return result
        accepted = accepted_item_types(item_type)
        if levels[-1] in accepted:
            return result
        fitting = [level_idx for level_idx, level in enumerate(levels) if level in accepted]
        if not fitting:
            return result
        on_depth = fitting[-1]
        ctx.debug(f"derived --on-depth={on_depth} for extender '{item.name}' (item_type={item_type}, chain {ftd})")
        descriptor = item.model_copy(update={"tool_args": (*item.tool_args, (ARG_ON_DEPTH, on_depth))})
        return Node.create(item=descriptor, children=result.children)

    def _types_after(self, ftd: ForestTypeDescriptor, node: Node | None) -> ForestTypeDescriptor:
        """One fold step: how does this resolved chain item change the forest's level types?

        Tool transitions live in TypeSystem.combine, which rejects
        combinations that cannot describe a real forest. A bare numeric literal
        types its level exactly ("int" / "float"); anything else that is not a
        resolved OperatorDescriptor produces items of undeclared type (string
        literals, subquery results): one level of "any" - items exist, their
        type is unknown. Attribute descriptors are known - they are attached by
        the caller (with_attribute) and pass through unchanged here.

        Args:
            ftd: Forest type descriptor before this chain item
            node: Resolved chain item node, or None (markers such as debug - no effect)

        Returns:
            Forest type descriptor after the item; empty depths mean the chain has no data source

        Raises:
            TypeCombinationError: If the tool cannot be combined with
                the descriptor (see TypeSystem.combine)
        """
        if node is None:
            return ftd
        item = node.item
        if isinstance(item, AttributeDescriptor):
            return ftd
        if isinstance(item, (int, float)) and not isinstance(item, bool):
            # A bare numeric literal: its level type is known exactly ("bool" is
            # an int subclass, so it is excluded - filter shorthand bools are not
            # numeric data)
            number_type = "float" if isinstance(item, float) else "int"
            return ForestTypeDescriptor(depths=[TypeDescriptor(name=number_type)])
        if not isinstance(item, OperatorDescriptor):
            return ForestTypeDescriptor.unknown()
        return self._type_system.combine(ftd, item)

    # ========================================================================
    # PRIVATE METHODS - Main interpretation
    # ========================================================================

    def _interpret_query(
        self,
        query_node: Node,
        at_ds: list[AttributeDescriptor],
        render: list[RenderDescriptor],
        last_operator: list[OperatorDescriptor],
        ctx: ExecContextAPI,
    ) -> Node | None:
        """Interpret a query node and resolve tools.

        Args:
            query_node: Node to interpret
            at_ds: List to collect attribute descriptors
            render: List to collect render tools
            last_operator: List tracking the chain's resolved operators (used for at_d argument binding)
            ctx: Execution context for dependency injection and query-time logging

        Returns:
            Resolved node or None if the item was consumed (markers, renders)

        todo: add support for "group"/"group by" prefix syntax
        """
        item = query_node.item
        ctx.debug(f"interpret_query, item: {item}")

        # Handle ROOT nodes: unwrap and interpret the single child
        # This happens when parenthesized expressions like (attr_name arg) are used
        if isinstance(item, str) and item == NODE_ROOT_ITEM and len(query_node.children) == 1:
            ctx.debug(f"Unwrapping ROOT node to process child: {query_node.children[0].item}")
            return self._interpret_query(query_node.children[0], at_ds, render, last_operator, ctx)

        # interpret_fn callback for sub-components; keeps the 4-arg signature
        # while binding this query's exec context (query-time logging flows to ctx)
        interpret_fn = partial(self._interpret_query, ctx=ctx)

        # Handle variable assignment: :=var_name
        if isinstance(item, str) and item.startswith(":="):
            return self._variable_handler.handle_assignment(
                query_node, item, at_ds, render, last_operator, interpret_fn, ctx
            )

        # Handle variable references: check if item is a variable reference with $ prefix
        # Only do this if it's a standalone reference (no children), not an argument to another operator
        if isinstance(item, str) and item.startswith("$") and not query_node.children:
            return self._variable_handler.handle_reference(item, ctx)

        # Get tools keys for render spec handling
        tools_keys = self._registry.get_tools()

        # Handle :nolimit — silently consume, prevents auto-limit injection.
        # TODO: when templates are introduced, replace with `limit --no`.
        # Handle `debug` marker — enable debug mode for this query's exec context only
        # (never on the shared logger, which would leak into subsequent queries).
        # Handle `debug-time` marker — show the elapsed execution time (no debug log;
        # combine with `debug` to get both).
        # Otherwise, handle render specs (:render-name) or filter out render markers.
        if isinstance(item, str) and item == NOLIMIT_TOKEN:
            handled, result = True, None
        elif isinstance(item, str) and item == DEBUG:
            ctx.is_debug = True
            handled, result = True, None
        elif isinstance(item, str) and item == DEBUG_TIME:
            # Implies debug: the timestamped log (is_debug) is shown along with the
            # elapsed time (is_time); is_time also sticks for the rest of the
            # session (see _execute_query_impl in UdanContext)
            ctx.is_debug = True
            ctx.is_time = True
            handled, result = True, None
        else:
            handled, result = self._try_handle_render_spec(
                query_node, at_ds, render, last_operator, tools_keys, interpret_fn, ctx
            )
        if handled:
            return result

        # Handle parameterized attribute notation: attr_name(arg)
        result = self._try_handle_parameterized_attribute(item, at_ds, ctx)
        if result is not None:
            return result

        # Handle string literals (marked with NODE_STRING_PREFIX)
        # These should be returned as-is without matching against tools
        if isinstance(item, str) and item.startswith(NODE_STRING_PREFIX):
            # Strip the prefix and return the actual string value as a leaf node
            return Node.leaf(item[len(NODE_STRING_PREFIX) :])

        # Handle bare numbers: like quoted strings they are literal data,
        # resolved to their numeric value instead of a tool name
        number = _number_literal(item)
        if number is not None:
            return Node.leaf(number)

        # todo: add support for "group"/"group by" prefix syntax here

        # Check for composite attributes (e.g., "pfc.proteins") BEFORE domain resolution
        is_composite_attr = self._detect_composite_attribute(query_node, ctx)

        # Resolve tool key (handle full-path resolution or regular resolution)
        tool_key = self._resolve_tool_with_full_path(query_node, tools_keys, is_composite_attr, ctx)

        # If resolution returned a Node (should return as-is)
        if isinstance(tool_key, Node):
            return tool_key

        # Get or create metadata for the tool
        metadata = self._get_or_create_metadata(tool_key, item, ctx)

        # Handle auto-detected renders (tools with tool_type="render" but no ":" prefix)
        result = self._try_handle_auto_detected_render(
            metadata, query_node, at_ds, render, last_operator, tools_keys, interpret_fn, ctx
        )
        if result is not None:
            # Node.leaf(None) is a special marker meaning "handled, no more output"
            # Otherwise return the result node
            return None if result.item is None else result

        # Filter render specs out of the arguments before binding them
        children = self._filter_render_specs_from_children(query_node.children, render, ctx)

        # Create descriptor from arguments and return
        descriptor = self._descriptor_factory.create_descriptor_from_args(
            tool_key, metadata, children, at_ds, render, last_operator, interpret_fn, ctx
        )
        return Node.leaf(descriptor)

    # ========================================================================
    # PRIVATE METHODS - Render specification handling
    # ========================================================================

    def _get_expected_render_args(self, render_name: str) -> int:
        """Determine how many arguments a render expects.

        Args:
            render_name: Name of the render

        Returns:
            Number of expected arguments (0 for varargs renders)
        """
        # Check metadata for expected args
        metadata = self._registry.get_metadata(render_name)
        if metadata is None:
            return 0

        # Special case: the attr render (plugins_renders.render_attr) is handled specially
        # and expects 1 user argument (field_name)
        if render_name == "attr":
            return 1

        # Aggregate renders (shape="children") normally take system-provided args, not user args
        # The system provides: depths, forest, attr_ds, ctx
        if metadata.meta and metadata.meta.get("shape") == "children":
            return 0

        # Count non-optional parameters (excluding 'item' and 'indent' which are implicit)
        properties = metadata.parameters.get("properties", {})
        required = set(metadata.parameters.get("required", []))
        # Exclude common implicit params
        implicit_params = {"item", "indent"}
        return len([p for p in properties if p in required and p not in implicit_params])

    def _render_has_varargs(self, render_name: str) -> bool:
        """Check if a render function accepts variable arguments (*args).

        Args:
            render_name: Name of the render

        Returns:
            True if the render has VAR_POSITIONAL parameters
        """
        try:
            render_fn = self._registry.resolve(render_name, kind=RENDER).fn
            # Unwrap to get the original function
            actual_fn = unwrap_function(render_fn)

            # Check for VAR_POSITIONAL parameters (e.g., *columns)
            for param in inspect.signature(actual_fn).parameters.values():
                if param.kind == inspect.Parameter.VAR_POSITIONAL:
                    return True
        except ValueError, AttributeError:
            pass

        return False

    def _is_render_key(self, tool_key: str) -> bool:
        """Check if a tool key is a render.

        Args:
            tool_key: Tool key (name or alias)

        Returns:
            True if the key resolves to a render tool
        """
        metadata = self._registry.get_metadata(tool_key)
        return metadata is not None and metadata.tool_type == RENDER

    def _resolve_render_name(self, render_name: str, ctx: ExecContextAPI) -> str:
        """Resolve a render spec name (:name) by exact match, then unique substring.

        Bare names never search renders (see _resolve_tool_key), so ":name"
        is the only place short render names are resolved: exact render key first,
        then a unique substring among render keys.

        Args:
            render_name: Render name typed after ":"
            ctx: Execution context for query-time logging

        Returns:
            Resolved render key. When nothing matches, the name is returned unchanged
            so that _validate_render_name reports it with the available renders.
        """
        renders = self._registry.get_tools(kind=RENDER)
        if render_name in renders:
            return render_name

        tool_matches = [tool_key for tool_key in renders if render_name in tool_key]
        if len(tool_matches) > 1:
            # Matches may be name + aliases of one render (e.g. render_excel_tree/excel-tree)
            single_match = self._check_single_metadata_match(tool_matches, ctx)
            if single_match:
                return single_match

            preferred_match = self._find_preferred_match(tool_matches, render_name)
            if preferred_match:
                ctx.debug(f"Found ambiguous render '{render_name}', selected preferred: {preferred_match}")
                return preferred_match

            prefix_match = self._find_prefix_match(tool_matches, render_name)
            if prefix_match:
                ctx.debug(f"Found ambiguous render '{render_name}', selected prefix match: {prefix_match}")
                return prefix_match

            raise QueryMiss(
                render_name,
                RENDER.name,
                f"ambiguous render '{render_name}' - listing the matches",
            )
        if len(tool_matches) == 1:
            ctx.debug(f"Resolved render spec '{render_name}' to: {tool_matches[0]}")
            return tool_matches[0]
        return render_name

    def _validate_render_name(self, render_name: str) -> None:
        """Report an unknown render as a miss.

        Args:
            render_name: Name of the render to validate

        Raises:
            QueryMiss: If render name is not found; the registered answerers
                decide what the query continues as
        """
        # The attr render is handled specially in plugins_renders.render_attr,
        # so a missing registry key of its own is not an error here
        if render_name == "attr":
            return

        renders = self._registry.get_tools(kind=RENDER)
        if render_name not in renders:
            raise QueryMiss(
                render_name,
                RENDER.name,
                f"unknown render '{render_name}' - listing renders",
            )

    def _unwrap_root_node(self, node: Node) -> Node:
        """Unwrap ROOT node to get the actual child.

        The parser wraps parenthesized expressions in ROOT nodes.
        e.g., :fmt("string") becomes :fmt -> ROOT -> __STRING__string

        Args:
            node: Node to unwrap

        Returns:
            Unwrapped node (or original if not a ROOT wrapper)
        """
        if node.item == NODE_ROOT_ITEM and len(node.children) == 1:
            return node.children[0]
        return node

    def _is_operator_child(self, child_item: str, tools_keys: list[str]) -> bool:
        """Check if a child item is an operator (not an attribute).

        Args:
            child_item: The child item to check
            tools_keys: List of known tool keys

        Returns:
            True if the child is an operator, False otherwise
        """
        if not isinstance(child_item, str) or child_item not in tools_keys:
            return False
        metadata = self._registry.get_metadata(child_item)
        if metadata is None:
            return False
        return bool(metadata.tool_type != ATTRIBUTE)

    def _collect_positional_args(
        self,
        query_node: Node,
        num_expected: int,
        tools_keys: list[str],
        consumed_children: int,
    ) -> tuple[list[str], int]:
        """Collect positional render arguments from node children.

        Args:
            query_node: The query node containing children
            num_expected: Number of arguments to collect
            tools_keys: List of known tool keys
            consumed_children: Current number of children already consumed

        Returns:
            Tuple of (list of render args, number of children consumed)
        """
        render_args: list[str] = []
        while len(render_args) < num_expected and consumed_children < len(query_node.children):
            child = query_node.children[consumed_children]
            child = self._unwrap_root_node(child)
            child_item = child.item

            # Handle __STRING__ token (format string with spaces/special chars)
            if isinstance(child_item, str) and child_item.startswith("__STRING__"):
                format_string = child_item[10:]  # Remove "__STRING__" prefix
                render_args.append(format_string)
                consumed_children += 1
                continue

            # Check if this child is an operator
            is_operator = self._is_operator_child(child_item, tools_keys)
            if not is_operator and isinstance(child_item, str):
                render_args.append(child_item)
                consumed_children += 1
            else:
                break

        return render_args, consumed_children

    def _collect_named_args(
        self,
        query_node: Node,
        render_args: list[str],
        consumed_children: int,
    ) -> tuple[list[str], int]:
        """Collect named arguments (--key=value) from node children.

        Args:
            query_node: The query node containing children
            render_args: List to append named arguments to
            consumed_children: Current number of children already consumed

        Returns:
            Tuple of (updated render args, number of children consumed)
        """
        while consumed_children < len(query_node.children):
            child = query_node.children[consumed_children]
            child = self._unwrap_root_node(child)
            child_item = child.item

            if isinstance(child_item, str) and child_item.startswith("--"):
                render_args.append(child_item)
                consumed_children += 1
            else:
                break

        return render_args, consumed_children

    def _collect_fallback_arg(
        self,
        query_node: Node,
        tools_keys: list[str],
        consumed_children: int,
    ) -> tuple[str | None, int]:
        """Collect first non-operator child as a fallback positional argument.

        Args:
            query_node: The query node containing children
            tools_keys: List of known tool keys
            consumed_children: Current number of children already consumed

        Returns:
            Tuple of (fallback arg or None, number of children consumed)
        """
        if consumed_children >= len(query_node.children):
            return None, consumed_children

        child = query_node.children[consumed_children]
        child = self._unwrap_root_node(child)
        child_item = child.item

        is_operator = self._is_operator_child(child_item, tools_keys)
        is_special_token = child_item in (":", DEBUG, DEBUG_TIME)

        if not is_operator and not is_special_token and isinstance(child_item, str):
            return child_item, consumed_children + 1

        return None, consumed_children

    def _collect_render_args_from_children(
        self,
        query_node: Node,
        num_expected: int,
        tools_keys,
        consumed_children: int,
    ) -> tuple[list[str], int]:
        """Collect render arguments from node children.

        Args:
            query_node: The query node containing children
            num_expected: Number of arguments to collect
            tools_keys: List of known tool keys
            consumed_children: Current number of children already consumed

        Returns:
            Tuple of (list of render args, number of children consumed)
        """
        # Collect positional arguments
        render_args, consumed_children = self._collect_positional_args(
            query_node, num_expected, tools_keys, consumed_children
        )

        # Collect named arguments
        render_args, consumed_children = self._collect_named_args(query_node, render_args, consumed_children)

        # Collect fallback argument if no args yet
        if not render_args:
            fallback_arg, consumed_children = self._collect_fallback_arg(query_node, tools_keys, consumed_children)
            if fallback_arg:
                render_args.append(fallback_arg)

        return render_args, consumed_children

    def _handle_render_spec(
        self,
        item: str,
        render: list[RenderDescriptor],
        query_node: Node,
        tools_keys,
        ctx: ExecContextAPI,
    ) -> Node | None:
        """Handle render specification syntax (:render-name).

        Args:
            item: The item string (should start with :)
            render: List to collect render tools
            query_node: The query node (to access children for render args)
            tools_keys: List of known tool keys
            ctx: Execution context for query-time logging

        Returns:
            None if handled and no more nodes to process, or a modified node

        Raises:
            ExceptionWithAdvice: If render spec is invalid
        """
        if not isinstance(item, str) or not item.startswith(":"):
            return None

        if item == ":":
            # Chain-position `:` is lowered to the render listing by the parser; this
            # argument-position survivor asks the same question, so it rewrites the
            # same way and the swap point continues the pipeline with the listing
            raise QueryMiss("", RENDER.name, "bare ':' - listing renders")

        # Parse render spec: :render-name [arg1 arg2 ...]
        parts = item[1:].split()
        if not parts:
            raise ExceptionWithAdvice("Render spec cannot be empty. Use : to see available renders.")

        render_name = self._resolve_render_name(parts[0], ctx)
        render_args_from_item = list(parts[1:])
        num_expected_args = self._get_expected_render_args(render_name)

        # Collect render args from item and children
        render_args = render_args_from_item[:]
        consumed_children = 0

        if self._render_has_varargs(render_name):
            # Varargs case: collect ALL available child nodes as args
            # Collect all children that are not tools
            additional_args, final_consumed = self._collect_render_args_from_children(
                query_node, len(query_node.children), tools_keys, consumed_children
            )
            render_args.extend(additional_args)
            consumed_children = final_consumed
        else:
            # Normal case: exact number of args expected
            additional_args, final_consumed = self._collect_render_args_from_children(
                query_node, num_expected_args - len(render_args), tools_keys, consumed_children
            )
            render_args.extend(additional_args)
            consumed_children = final_consumed

        # Validate we have enough args (skip for varargs renders)
        if not self._render_has_varargs(render_name) and len(render_args) < num_expected_args:
            raise ExceptionWithAdvice(
                f"Render :{render_name} expects {num_expected_args} arguments, got {len(render_args)}"
            )

        # Validate render name
        self._validate_render_name(render_name)

        # Add to render list as RenderDescriptor
        # This avoids the need to re-parse the render spec string later
        if render_args:
            render_desc = RenderDescriptor.create(render_name, tuple(render_args))
        else:
            render_desc = RenderDescriptor.create(render_name)
        render.append(render_desc)

        # Return node with unconsumed children for further interpretation
        remaining_children = query_node.children[consumed_children:]
        if len(remaining_children) == 0:
            return None
        elif len(remaining_children) == 1:
            return remaining_children[0]
        else:
            # Multiple remaining children - wrap in ROOT for continued processing
            return Node(item=NODE_ROOT_ITEM, children=remaining_children)

    def _try_handle_render_spec(
        self,
        query_node: Node,
        at_ds: list[AttributeDescriptor],
        render: list[RenderDescriptor],
        last_operator: list[OperatorDescriptor],
        tools_keys: list[str],
        interpret_fn: Callable,
        ctx: ExecContextAPI,
    ) -> tuple[bool, Node | None]:
        """Try to handle render specs (:render-name) or filter out render markers.

        Args:
            query_node: Node containing the query
            at_ds: List to collect attribute descriptors
            render: List to collect render tools
            last_operator: List to track the last operator processed
            tools_keys: List of available tools
            interpret_fn: Function to interpret child nodes recursively
            ctx: Execution context for query-time logging

        Returns:
            Tuple of (handled, result):
            - (True, Node): render spec was processed successfully
            - (True, None): item was filtered out (":" prefix)
            - (False, None): item was not handled (continue processing)
        """
        item = query_node.item
        # Handle render specs (:render-name)
        render_result = self._handle_render_spec(item, render, query_node, tools_keys, ctx)
        if render_result is not None:
            result = self._process_render_result(render_result, at_ds, render, last_operator, interpret_fn)
            return (True, result)

        # Filter out items starting with ":" (unprocessed render specs)
        if isinstance(item, str) and item.startswith(":"):
            return (True, None)

        return (False, None)

    def _try_handle_auto_detected_render(
        self,
        metadata: ToolMetadata,
        query_node: Node,
        at_ds: list[AttributeDescriptor],
        render: list[RenderDescriptor],
        last_operator: list[OperatorDescriptor],
        tools_keys: list[str],
        interpret_fn: Callable,
        ctx: ExecContextAPI,
    ) -> Node | None:
        """Try to handle auto-detected render-type tools.

        Args:
            metadata: Tool metadata
            query_node: Node containing the query
            at_ds: List to collect attribute descriptors
            render: List to collect render tools
            last_operator: List to track the last operator processed
            tools_keys: List of available tools
            interpret_fn: Function to interpret child nodes recursively
            ctx: Execution context for query-time logging

        Returns:
            Node if handled and there are more nodes to process,
            None if handled but no more nodes (render was consumed),
            or if not a render (should continue processing)
        """
        # Auto-detect renders: if tool has tool_type="render", treat it as a render spec
        # even without the ":" prefix. This allows externally provided renders to work correctly.
        if metadata.tool_type == RENDER:
            item = query_node.item
            ctx.debug(f"Auto-detected render-type tool: {item}")
            # Treat this as a render spec by calling _handle_render_spec with ":" prefix
            render_item = f":{item}"
            render_result = self._handle_render_spec(render_item, render, query_node, tools_keys, ctx)
            # _handle_render_spec returns:
            # - None if render was consumed successfully (no children remaining)
            # - Node if there are remaining children to process
            # In both cases, the render was handled, so we should not continue to _create_descriptor_from_args
            # If there are remaining children, process them
            if render_result is not None:
                return self._process_render_result(render_result, at_ds, render, last_operator, interpret_fn)
            # Render was consumed successfully, signal to stop processing by returning a special marker
            # We return Node.leaf(None) to indicate "handled, stop processing"
            return Node.leaf(None)
        return None

    def _process_render_result(
        self,
        render_result: Node,
        at_ds: list[AttributeDescriptor],
        render: list[RenderDescriptor],
        last_operator: list[OperatorDescriptor],
        interpret_fn: Callable,
    ) -> Node | None:
        """Process the result from render spec handling.

        Args:
            render_result: The result node from render spec handling
            at_ds: List to collect attribute descriptors
            render: List to collect render tools
            last_operator: List to track the last operator processed
            interpret_fn: Function to interpret child nodes recursively

        Returns:
            Processed node or None
        """
        # If the result is an operator descriptor, return it directly
        if isinstance(render_result.item, OperatorDescriptor):
            return render_result
        # Render spec was found - check if it returned a modified node to continue interpreting
        if render_result.item == NODE_ROOT_ITEM and len(render_result.children) == 1:
            # Continue with the single child
            return interpret_fn(render_result.children[0], at_ds, render, last_operator)
        elif render_result.item == NODE_ROOT_ITEM:
            # Multiple children - interpret each and return as ROOT
            interpreted_children = [interpret_fn(ch, at_ds, render, last_operator) for ch in render_result.children]
            children = [ch for ch in interpreted_children if ch is not None]
            return Node(item=NODE_ROOT_ITEM, children=children)
        else:
            # Single node returned - continue interpreting it
            return interpret_fn(render_result, at_ds, render, last_operator)

    def _filter_render_specs_from_children(
        self,
        children: list[Node],
        render: list[RenderDescriptor],
        ctx: ExecContextAPI,
    ) -> list[Node]:
        """Filter out render specs from children list.

        Render specs (items starting with :) should not be passed as arguments
        to the tool, but should be collected in the render list.

        Args:
            children: List of child nodes
            render: List to collect render tools
            ctx: Execution context for query-time logging

        Returns:
            List of children with render specs filtered out
        """
        children_without_renders = []
        for ch in children:
            if isinstance(ch.item, str) and ch.item.startswith(":"):
                # This is a render spec, parse it and add to render list
                # Strip the leading ":" and parse the render spec
                spec_str = ch.item[1:]  # Remove ":"
                if spec_str:
                    spec_desc = self._parse_render_spec(spec_str)
                    resolved = self._resolve_render_name(spec_desc.name, ctx)
                    render.append(RenderDescriptor.create(resolved, spec_desc.args))
            else:
                children_without_renders.append(ch)
        return children_without_renders

    def _parse_render_spec(self, spec_str: str) -> RenderDescriptor:
        """Parse a render spec string into a RenderDescriptor.

        Args:
            spec_str: Render spec string like "render-name" or "render-name(arg1,arg2)"

        Returns:
            RenderDescriptor object
        """
        if "(" in spec_str and spec_str.endswith(")"):
            # Parse: render-name(arg1,arg2) -> name="render-name", args=("arg1", "arg2")
            name, args_str = spec_str.split("(", 1)
            args_str = args_str[:-1]  # Remove trailing ")"
            args = tuple(arg.strip() for arg in args_str.split(",")) if args_str.strip() else ()
            return RenderDescriptor.create(name, args)
        else:
            return RenderDescriptor.create(spec_str)

    def _collect_supported_renders(self, node: Node) -> list[RenderDescriptor]:
        """Collect supported_renders from operator metadata in the tree.

        Args:
            node: Root node to search

        Returns:
            List of render descriptors (e.g., [Render(org-item, args=("id", "name"))])
        """

        def collect_recursive(n: Node, replacers_only: bool = False) -> list[RenderDescriptor]:
            renders = []
            if isinstance(n.item, OperatorDescriptor):
                # Get operator metadata
                op_d = n.item
                name = op_d.name
                op_m = self._registry.get_metadata(name)
                if op_m:
                    supported = op_m.meta.get("supported_renders", [])
                    if supported:
                        # If we're only collecting from the kinds that carry a chain's
                        # render, skip the others (the kind declares which one that is)
                        if replacers_only and not op_m.tool_type.declares_output:
                            pass
                        else:
                            # Parse each render spec string into a RenderDescriptor
                            for spec_str in supported:
                                renders.append(self._parse_render_spec(spec_str))
            # Recursively check children
            for child in n.children:
                renders.extend(collect_recursive(child, replacers_only=replacers_only))
            return renders

        # First pass: try collecting from replacers only
        result = collect_recursive(node, replacers_only=True)
        # If replacers have no supported_renders, fall back to all operators
        if not result:
            result = collect_recursive(node, replacers_only=False)
        return result

    def _first_item_render(self, render_ds: list[RenderDescriptor]) -> RenderDescriptor | None:
        """First render spec that renders a single item (aggregate renders excluded).

        Args:
            render_ds: List of render descriptors

        Returns:
            RenderDescriptor, or None when every spec is an aggregate render
        """
        for render_d in render_ds:
            if not is_aggregate_render(self._registry, render_d.name):
                return render_d
        return None

    def _last_supported_item_render(self, node: Node) -> RenderDescriptor | None:
        """Last operator-supported render that renders a single item.

        Args:
            node: Root node to search

        Returns:
            RenderDescriptor, or None when the operators support no per-item render
        """
        supported = [
            render_d
            for render_d in self._collect_supported_renders(node)
            if not is_aggregate_render(self._registry, render_d.name)
        ]
        return supported[-1] if supported else None

    # ========================================================================
    # PRIVATE METHODS - Special item handling
    # ========================================================================

    def _try_handle_parameterized_attribute(
        self, item: str, at_ds: list[AttributeDescriptor], ctx: ExecContextAPI
    ) -> Node | None:
        """Try to handle parameterized attribute notation like attr_name(arg).

        Args:
            item: The query item to check
            at_ds: List to collect attribute descriptors
            ctx: Execution context for query-time logging

        Returns:
            Node with AttributeDescriptor if handled, None otherwise
        """
        if not (isinstance(item, str) and item.endswith(")") and "(" in item):
            return None

        # Extract attribute name and argument
        attr_name = item[: item.index("(")]
        arg_str = item[item.index("(") + 1 : item.rindex(")")]

        ctx.debug(f"Detected parameterized attribute: {attr_name} with arg: {arg_str}")

        # Create an AttributeDescriptor with the argument
        # The argument should be passed as a parameter to the attribute
        metadata = self._registry.get_metadata(attr_name)
        s_type_repr = repr(metadata.tool_type) if metadata else None
        ctx.debug(f"Resolved metadata for {attr_name}: type={type(metadata).__name__}, tool_type={s_type_repr}")

        if not (metadata and metadata.tool_type == ATTRIBUTE and "attribute_type" in metadata.meta):
            # Not an attribute or unknown - continue processing
            debug_type = repr(metadata.tool_type) if metadata else "None"
            ctx.debug(f"Not an attribute or unknown, continuing... tool_type={debug_type}")
            return None

        # This is an attribute - parse its parameters from the input schema
        parameters_schema = metadata.parameters
        props = parameters_schema.get("properties", {})
        prop_names = list(props.keys())

        # Find which parameter to bind (skip 'item' which is framework-injected)
        framework_params = FRAMEWORK_PARAMS_ATTR
        bindable_params = [p for p in prop_names if p not in framework_params]

        ctx.debug(f"Bindable params for {attr_name}: {bindable_params}")

        if not bindable_params:
            raise ExceptionWithAdvice(
                f"Parameterized attribute '{attr_name}' has no query parameters (only the injected 'item'). "
                f"Argument '{arg_str}' cannot be bound."
            )

        # Split the argument string into named (k=v) and positional parts.
        # Supports attr(value), attr(k=v) and attr(k1=v1,k2=v2); a part whose key
        # is not a parameter stays positional so values containing '=' still work.
        named: dict[str, str] = {}
        positional: list[str] = []
        for part in arg_str.split(","):
            part = part.strip()
            if not part:
                continue
            key, eq, value = part.partition("=")
            if eq and key.strip() in bindable_params:
                named[key.strip()] = value.strip()
            else:
                positional.append(part)

        remaining = [p for p in bindable_params if p not in named]
        if len(positional) > len(remaining):
            raise ExceptionWithAdvice(
                f"Parameterized attribute '{attr_name}' takes {len(bindable_params)} parameter(s): {bindable_params}. "
                f"Cannot bind positional argument(s) {positional}. "
                f"Use named argument syntax: {attr_name}({bindable_params[0]}=<value>)"
            )

        args: dict[str, Any] = {}
        try:
            for key, value in named.items():
                param_type = props.get(key, {}).get("type")
                args[key] = convert_string_value(value, param_type)
            for value in positional:
                param_name = remaining.pop(0)
                param_type = props.get(param_name, {}).get("type")
                args[param_name] = convert_string_value(value, param_type)
        except ValueError as e:
            raise ExceptionWithAdvice(f"Cannot bind arguments of parameterized attribute '{attr_name}': {e}") from e

        at_d = AttributeDescriptor.create(attr_name, args, metadata=metadata)
        at_ds.append(at_d)
        ctx.debug(f"Created AttributeDescriptor: {at_d}")
        return Node.leaf(at_d)

    # ========================================================================
    # PRIVATE METHODS - Tool resolution
    # ========================================================================

    def _check_single_metadata_match(self, tool_matches: list[str], ctx: ExecContextAPI) -> str | None:
        """Check if multiple substring matches all refer to the same tool.

        Args:
            tool_matches: List of matched tool keys
            ctx: Execution context for query-time logging

        Returns:
            Shortest key name if all matches refer to same tool, None otherwise
        """
        metadatas = [self._registry.get_metadata(m) for m in tool_matches]
        # Check if all non-None metadatas are the same object (by id)
        unique_metadata_ids = {id(m) for m in metadatas if m is not None}
        if len(unique_metadata_ids) == 1:
            # All matches refer to the same tool, just pick the shortest name
            tool_matches.sort(key=len)
            tool_key = tool_matches[0]
            ctx.debug(
                f"Found multiple matches for '{tool_matches[0]}' that all refer to the same tool, selected: {tool_key}"
            )
            return tool_key
        return None

    def _tool_accepts_additional_arguments(self, tool_key: str) -> bool:
        """Check if a tool function accepts additional user-provided arguments.

        This checks if the tool accepts more than just the implicit data parameter
        (e.g., 'item', 'forest', 'items'). Additional arguments are those beyond the main
        data parameter that the user explicitly provides in the query.

        Args:
            tool_key: The tool key

        Returns:
            True if the tool accepts additional arguments beyond the main data parameter
        """
        func = self._registry.get_function(tool_key)
        if func is None:
            return False

        try:
            sig = inspect.signature(func)
            # Filter out framework-injected parameters like 'ctx' and common data parameter names
            data_param_names = {"ctx", "item", "items", "forest", "forests", "query"}
            user_params = [
                p
                for p in sig.parameters.values()
                if p.name not in data_param_names and p.kind not in (p.VAR_POSITIONAL, p.VAR_KEYWORD)
            ]
            return len(user_params) > 0
        except ValueError, TypeError:
            # If we can't inspect the signature, assume it doesn't accept arguments
            return False

    def _find_match_by_argument_compatibility(
        self, tool_matches: list[str], query_node: Node, ctx: ExecContextAPI
    ) -> str | None:
        """Find best tool match based on argument compatibility.

        If the query has arguments (children), prefer tools that accept additional arguments.
        If the query has no arguments, prefer tools that don't require additional arguments.

        Args:
            tool_matches: List of matched tool keys
            query_node: The query node being resolved
            ctx: Execution context for query-time logging

        Returns:
            Best matching tool key based on argument presence, or None if no clear match
        """
        has_args = len(query_node.children) > 0

        # Categorize tools by whether they accept additional arguments
        accepts_args = [name for name in tool_matches if self._tool_accepts_additional_arguments(name)]
        no_args = [name for name in tool_matches if not self._tool_accepts_additional_arguments(name)]

        if has_args:
            # Query has arguments - prefer tools that accept additional arguments
            if len(accepts_args) == 1:
                ctx.debug(f"Query has arguments, selected tool that accepts additional arguments: {accepts_args[0]}")
                return accepts_args[0]
            elif len(accepts_args) > 1 and len(no_args) == 0:
                # All accept additional arguments but we have multiple - still ambiguous
                return None
        # Query has no arguments - prefer tools that don't require additional arguments
        elif len(no_args) == 1:
            ctx.debug(f"Query has no arguments, selected tool with no required additional arguments: {no_args[0]}")
            return no_args[0]
        elif len(no_args) > 1 and len(accepts_args) == 0:
            # All don't accept additional arguments but we have multiple - still ambiguous
            return None

        return None

    def _find_preferred_match(self, tool_matches: list[str], item: str) -> str | None:
        """Find preferred match from ambiguous tool matches.

        Args:
            tool_matches: List of matched tool keys
            item: The query item (used for preference key lookup)

        Returns:
            Preferred match key if found in preferences, None otherwise
        """
        prefs = self._udan_tools_preferences_input

        # Only check preferences if the query item is a preference key
        if item not in prefs:
            return None

        preferred_value = prefs[item]

        # Check each matched tool against the preferred value
        for match in tool_matches:
            qualified_name = self._format_tool(match)

            # Check if this tool matches the preferred value
            if preferred_value in (qualified_name, match):
                return match

        return None

    def _find_prefix_match(self, tool_matches: list[str], item: str) -> str | None:
        """The one match the typed fragment is a prefix of, when there is exactly one.

        Substring matching puts a prefix (`list-i` of `list-item`) beside an infix
        (`list-i` of `term-list-item`) and calls it ambiguous; the prefix is the
        one the fragment names, so it wins over listing the matches. More than
        one prefix match stays ambiguous.

        Args:
            tool_matches: List of matched tool keys
            item: The typed fragment

        Returns:
            The single key starting with the fragment, None otherwise
        """
        prefix_matches = [match for match in tool_matches if match.startswith(item)]
        return prefix_matches[0] if len(prefix_matches) == 1 else None

    def _matches_tools(self, name: str, tools_keys: list[str]) -> bool:
        """Whether a name resolves against the registry: an exact key, or a substring of one.

        The same match the resolution makes, asked as a yes/no; renders are
        excluded from the substring half, the way bare-name search excludes them
        (see _resolve_tool_key).

        Args:
            name: The name to look up
            tools_keys: Available tool keys

        Returns:
            True when the name matches at least one tool key
        """
        if name in tools_keys:
            return True
        return any(name in tool_key and not self._is_render_key(tool_key) for tool_key in tools_keys)

    def _dash_sugar_item(self, item: Item, tools_keys: list[str], ctx: ExecContextAPI) -> Item:
        """The item a dashed word resolves to: the underscored tool name, or the word as typed.

        Tool names are Python identifiers, so a query word may write the
        underscore as a dash (`insert-diff` -> `insert_diff`). The sugar fires
        only when the word is a miss as typed and the underscored form matches:
        a hyphenated name of its own (an alias like `list-item`) is never rewritten.

        Args:
            item: The query node's item
            tools_keys: Available tool keys
            ctx: Execution context for query-time logging

        Returns:
            The underscored name when the sugar applies, the item unchanged otherwise
        """
        if not isinstance(item, str) or "-" not in item:
            return item
        sugar_name = item.replace("-", "_")
        if (
            sugar_name == item
            or self._matches_tools(item, tools_keys)
            or not self._matches_tools(sugar_name, tools_keys)
        ):
            return item
        ctx.debug(f"Dash sugar: '{item}' resolved as '{sugar_name}'")
        return sugar_name

    def _resolve_tool_key(
        self,
        query_node: Node,
        tools_keys: list[str],
        ctx: ExecContextAPI,
    ) -> Node | str:
        """Resolve a tool key from an item using exact match, substring match, or composite attribute.

        Args:
            query_node: Node containing the item (to check for children)
            tools_keys: List of available tool keys
            ctx: Execution context for query-time logging

        Returns:
            Node if the item should be returned as-is (variable reference or plain data)
            str if the item was resolved to a tool key
        """
        item = query_node.item

        # Handle AttributeDescriptor from bracket syntax like (translate_ru)
        if isinstance(item, AttributeDescriptor):
            item = item.name
            ctx.debug(f"Resolved AttributeDescriptor to name: {item}")

        # First, try exact match
        if item in tools_keys:
            ctx.debug(f"Found exact match: {item}")
            return item

        # No exact match - check if it's a variable reference BEFORE substring matching
        # This prevents variable names like 'a' from matching substrings in tools like 'range'
        if isinstance(item, str) and self._symbols_env.has_variable(item):
            ctx.debug(f"Found variable reference: {item}")
            return Node.leaf(f"{NODE_VAR_PREFIX}{item}")

        # Dash sugar: `insert-diff` names `insert_diff` (see _dash_sugar_item)
        item = self._dash_sugar_item(item, tools_keys, ctx)

        # Handle trailing underscore: list all tools with that prefix
        # e.g., "sort_" lists the tools starting with "sort_"
        if isinstance(item, str) and item.endswith("_"):
            prefix = item
            tool_matches = [tool_key for tool_key in tools_keys if tool_key.startswith(prefix)]
            if tool_matches:
                raise QueryMiss(
                    prefix,
                    "",
                    f"tool '{item}' not found - listing the '{prefix}' matches",
                )

        # Fall back to substring matching.
        # Renders are excluded from bare-name search: a render sharing a substring
        # with an inserter/operator (e.g. excel_tree) would make the bare name
        # ambiguous. Renders are addressed by full name (exact match above) or via
        # ":name", which searches renders by substring (see _resolve_render_name).
        tool_matches = [tool_key for tool_key in tools_keys if item in tool_key and not self._is_render_key(tool_key)]

        if len(tool_matches) > 1:
            # Multiple matches - check if they all refer to same tool
            single_match = self._check_single_metadata_match(tool_matches, ctx)
            if single_match:
                return single_match

            # Check for preferred match in user preferences
            preferred_match = self._find_preferred_match(tool_matches, item)
            if preferred_match:
                ctx.debug(f"Found ambiguous match '{item}', selected preferred: {preferred_match}")
                return preferred_match

            # Smart parser: use argument presence to resolve ambiguity
            # If query has arguments, prefer tools that accept arguments
            # If query has no arguments, prefer tools that don't require arguments
            argument_compatible_match = self._find_match_by_argument_compatibility(tool_matches, query_node, ctx)
            if argument_compatible_match:
                return argument_compatible_match

            # No clear preference - list the matches
            raise QueryMiss(item, "", f"ambiguous tool '{item}' - listing the matches")

        if len(tool_matches) == 1:
            ctx.debug(f"Found exactly one tool key: {tool_matches[0]}")
            return tool_matches[0]

        # No substring matches found
        # Check if this is a composite attribute (e.g., "pfc.proteins")
        if self._detect_composite_attribute(query_node, ctx):
            base_attr_name, field_path = item.split(".", 1)
            ctx.debug(f"Found composite attribute: {item} (base: {base_attr_name}, field: {field_path})")
            return item  # Use the full composite name as the key

        # Not a composite attribute and not found
        # If item has children, it's being used as an operator - should error
        # If item has no children and is not a quoted string literal, should also error
        if query_node.children:
            # An unknown tool with arguments is a usage error, not a search:
            # name the miss and offer the close names. Answering with the listing
            # would make every miss behave like `?` - and the listing filters by the
            # missed name, which matches nobody, so it shows the whole registry.
            raise self._unknown_tool_error(item, tools_keys)
        else:
            # Check if this is a special internal node (variable reference or string literal)
            # These have special prefixes and should be allowed through
            if isinstance(item, str) and (
                item.startswith(NODE_VAR_PREFIX)
                or item.startswith(NODE_STRING_PREFIX)
                or "=" in item  # KEYVAL tokens (key=value syntax for positional arguments)
            ):
                return query_node
            # Bare non-numeric literals without quotes are not allowed
            # User must use quoted literals (e.g., "abcdef") instead
            # (bare numbers are literal data, handled before resolution)
            similar = self._find_similar_tools(
                item, [tool_key for tool_key in tools_keys if not self._is_render_key(tool_key)]
            )
            # A bare word is a usage error, not a search: name the quote form, and when
            # a name is close, list it as a suggestion. Never answer with the docs of
            # one "similar" name - a short word is within edit distance 2 of half the
            # registry, and its docs would read as the answer to what the user typed.
            if similar:
                raise ExceptionWithAdvice(
                    f"Bare literal '{item}' is not allowed.\n"
                    f'If you want to use this as a literal string, quote it: "{item}"\n'
                    f"Did you mean one of these?\n{self._format_tools_list(similar)}"
                )
            raise ExceptionWithAdvice(
                f"Bare literal '{item}' is not allowed.\n"
                f'If you want to use this as a literal string, quote it: "{item}"'
            )

    def _unknown_tool_error(self, item: str, tools_keys: list[str]) -> ExceptionWithAdvice:
        """Build the not-found error for an unknown tool, offering the close names.

        Args:
            item: The unknown tool name
            tools_keys: Available tool keys to suggest from

        Returns:
            The exception to raise - names the miss, lists the close names when there
            are any, and points at the `?` listing for the rest
        """
        similar = self._find_similar_tools(
            item, [tool_key for tool_key in tools_keys if not self._is_render_key(tool_key)]
        )
        message = f"Tool '{item}' not found."
        if similar:
            message += f"\nDid you mean one of these?\n{self._format_tools_list(similar)}"
        return ExceptionWithAdvice(message + "\nRun '?' to list the available tools.")

    def _find_similar_tools(self, item: str, tools_keys: list[str]) -> list[str]:
        """Find tools similar to item using Levenshtein distance.

        Returns up to _MAX_SIMILAR_SUGGESTIONS most similar tools, using the last
        segment (after last dot) for comparison, then sorted by distance. Names
        further than _MAX_SIMILAR_SUGGESTION_DISTANCE edits away are not offered.

        Args:
            item: The unknown item
            tools_keys: List of available tool keys

        Returns:
            List of tool keys sorted by similarity (closest first), up to _MAX_SIMILAR_SUGGESTIONS
        """
        candidates = []
        for tool_key in tools_keys:
            # Compare against the last segment (after last dot) for domain-qualified names
            # e.g., for "demo.fruits", compare against "fruits"
            last_segment = tool_key.rsplit(".", 1)[-1]
            dist = levenshtein_distance(item, last_segment)
            if dist <= _MAX_SIMILAR_SUGGESTION_DISTANCE:
                candidates.append((dist, tool_key))
        candidates.sort(key=lambda x: (x[0], x[1]))
        return [tool_key for _, tool_key in candidates[:_MAX_SIMILAR_SUGGESTIONS]]

    def _detect_composite_attribute(self, query_node: Node, ctx: ExecContextAPI) -> bool:
        """Check if item is a composite attribute (e.g., "pfc.proteins" or "demo.pfc.proteins").

        Args:
            query_node: Node containing the item
            ctx: Execution context for query-time logging

        Returns:
            True if item is a composite attribute, False otherwise
        """
        item = query_node.item
        # Handle non-string items (e.g., boolean True/False for filter shorthand)
        if not isinstance(item, str):
            return False
        # Must contain a dot to be a composite attribute
        if "." not in item or query_node.children:
            return False

        # Split into base attribute name and field path
        base_attr_name, field_path = item.split(".", 1)

        # Check if the base is an attribute (has metadata without tool_type)
        base_metadata = self._registry.get_metadata(base_attr_name)
        ctx.debug(f"Checking composite attribute: item={item}, base={base_attr_name}, field={field_path}")
        ctx.debug(f"  base_metadata: {base_metadata is not None}")
        if base_metadata:
            ctx.debug(f"  base_metadata.tool_type: {repr(base_metadata.tool_type)}")
            ctx.debug(f"  base is attribute: {base_metadata.tool_type == ATTRIBUTE}")
            # Direct match: base is an attribute
            if base_metadata.tool_type == ATTRIBUTE and isinstance(base_metadata, AttributeMetadata):
                ctx.debug(f"Found composite attribute: {item} (base: {base_attr_name}, field: {field_path})")
                return True
            # Check for domain-qualified composite attribute (e.g., "demo.pfc.proteins")
            # If there are multiple dots, the middle part might be the attribute
            if "." in field_path and base_metadata.tool_type != ATTRIBUTE:
                # Split field_path to check if the first part is the attribute
                # e.g., "demo.pfc.proteins" -> base="demo", field="pfc.proteins"
                # We need to check if "pfc" (or "demo.pfc") is an attribute
                parts = field_path.split(".", 1)
                if len(parts) >= 1:
                    # Check if base.first_part is an attribute (domain.attr.field format)
                    qualified_attr = f"{base_attr_name}.{parts[0]}"
                    attr_metadata = self._registry.get_metadata(qualified_attr)
                    if (
                        attr_metadata
                        and attr_metadata.tool_type == ATTRIBUTE
                        and isinstance(attr_metadata, AttributeMetadata)
                    ):
                        ctx.debug(f"  Found domain-qualified composite attribute: {qualified_attr}")
                        return True
                    # Also check if first_part alone is an attribute
                    first_part_metadata = self._registry.get_metadata(parts[0])
                    if (
                        first_part_metadata
                        and first_part_metadata.tool_type == ATTRIBUTE
                        and isinstance(first_part_metadata, AttributeMetadata)
                    ):
                        # But only if it's from the same domain
                        if first_part_metadata.meta.get("domain") == base_attr_name:
                            ctx.debug(f"  Found domain-specific attribute: {parts[0]} in domain {base_attr_name}")
                            return True

        return False

    def _resolve_tool_with_full_path(
        self,
        query_node: Node,
        tools_keys: list[str],
        is_composite_attr: bool,
        ctx: ExecContextAPI,
    ) -> Node | str:
        """Resolve tool key, handling full-path resolution (domain.name) or regular resolution.

        Args:
            query_node: Node containing the item
            tools_keys: List of available tool keys
            is_composite_attr: Whether the item is a composite attribute
            ctx: Execution context for query-time logging

        Returns:
            Node if should return as-is, str (tool key) if resolved successfully
        """
        item = query_node.item
        # A bare scalar (e.g. the 3 in `attr(3)` mis-routed into resolution) is
        # a value, not a tool name - fail with a clean error instead of
        # a TypeError from string operations on a non-string item.
        if not isinstance(item, str) and not isinstance(item, AttributeDescriptor):
            raise ExceptionWithAdvice(
                f"'{item!r}' is a literal value and cannot be used as a tool. "
                f"Literal values are only valid as arguments, e.g. 'range {item}'."
            )
        # Support full-path resolution (e.g., "demo.fruits")
        # If item contains '.', treat as domain.name format
        if isinstance(item, str) and "." in item and not is_composite_attr:
            domain_part, name_part = item.rsplit(".", 1)
            # Check if there's a tool with name_part that has domain=domain_part
            if name_part in tools_keys:
                metadata = self._registry.get_metadata(name_part)
                if metadata and metadata.meta.get("domain") == domain_part:
                    ctx.debug(f"Found full-path match: {domain_part}.{name_part}")
                    return name_part
                # If item has children, it's being used as an operator - should error
                elif query_node.children:
                    raise QueryMiss(
                        name_part,
                        "",
                        f"tool '{name_part}' exists but not in domain '{domain_part}' - listing the matches",
                    )
                else:
                    return query_node
            # If item has children, it's being used as an operator - should error
            elif query_node.children:
                raise QueryMiss(
                    name_part,
                    "",
                    f"tool '{name_part}' not found in domain '{domain_part}' - listing the matches",
                )
            else:
                return query_node
        else:
            # Resolve tool key (exact match, substring match, etc.)
            resolution_result = self._resolve_tool_key(query_node, tools_keys, ctx)
            if isinstance(resolution_result, Node):
                # Resolution returned a Node (variable reference or plain data)
                return resolution_result
            else:
                # Resolution returned a tool key (string)
                return resolution_result

    def _get_or_create_metadata(self, tool_key: str, item: str, ctx: ExecContextAPI):
        """Get metadata for tool key, or create synthetic metadata for composite attributes.

        Args:
            tool_key: Tool key
            item: Original item (for error messages)
            ctx: Execution context for query-time logging

        Returns:
            Metadata object

        Raises:
            ExceptionWithAdvice: If metadata is missing and not a composite attribute
        """
        metadata = self._registry.get_metadata(tool_key)
        ctx.debug(f"Get metadata for tool_key={tool_key}: metadata={metadata is not None}")
        if metadata is None:
            # Check if this is a composite attribute (contains a dot)
            if "." in tool_key:
                # Create synthetic metadata for composite attributes
                ctx.debug(f"Creating synthetic metadata for composite attribute: {tool_key}")

                # Empty schema for composite attributes (they have no parameters)
                empty_schema = {"properties": {}, "required": [], "type": "object"}
                # Output schema for composite attributes (can be any type)
                output_schema = {
                    "anyOf": [
                        {"type": "string"},
                        {"type": "number"},
                        {"type": "boolean"},
                        {"type": "null"},
                        {"type": "object"},
                        {"type": "array"},
                    ]
                }

                metadata = AttributeMetadata(
                    name=tool_key,
                    fn_path="composite",
                    parameters=empty_schema,
                    output_schema=output_schema,
                    tool_type=ATTRIBUTE,
                    attribute_type="composite",
                )
                ctx.debug(f"Created synthetic metadata: {metadata}")
            else:
                raise ExceptionWithAdvice(f"Tool '{item}' found but metadata is missing. This is an internal error.")
        return metadata
