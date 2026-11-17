"""Descriptor factory for QueryProcessor.

Creates OperatorDescriptor and AttributeDescriptor instances from bound arguments.
"""

from collections.abc import Callable
from typing import Any

from udan.core.api_attributes import (
    ATTRIBUTE,
    ATTRIBUTE_TYPE_AGGREGATE,
    ATTRIBUTE_TYPE_COLUMN,
    AttributeDescriptor,
    AttributeMetadata,
)
from udan.core.api_constants import (
    ARG_MAX_DEPTH,
    ARG_ON_DEPTH,
    ARG_POSITION,
    FRAMEWORK_PARAMS_ALL,
    NODE_ROOT_ITEM,
    NODE_STRING_PREFIX,
    NODE_VAR_PREFIX,
    DepthSelector,
)
from udan.core.api_descriptor_factory import DescriptorFactoryAPI
from udan.core.api_exceptions import ExceptionWithAdvice
from udan.core.api_exec_context import ExecContextAPI
from udan.core.api_forests import Node
from udan.core.api_operators import (
    OperatorDescriptor,
)
from udan.core.api_query_processor import QueryMiss
from udan.core.api_symbols_env import SymbolsEnvAPI
from udan.core.utils_binding import (
    convert_boolean_string,
    convert_value,
)
from udan.core_tools_loading.api_tools import (
    ToolKind,
    ToolMetadata,
    validate_parameters_schema,
)
from udan.core_tools_loading.api_tools_registry import ToolsRegistryAPI
from udan.parsing.api_query_parser import parse_named_argument
from udan.renders.api_renders import RenderDescriptor

# Constants for parameter display formatting
_MAX_PARAM_DEFAULT_LENGTH = 30


class DescriptorFactory(DescriptorFactoryAPI):
    """Factory for creating operator and attribute descriptors from query arguments."""

    def __init__(
        self,
        symbols_env: SymbolsEnvAPI,
        udan_tools_variables_defaults: dict[str, dict[str, object]],
        registry: ToolsRegistryAPI | None = None,
    ):
        """Initialize descriptor factory.

        Args:
            symbols_env: SymbolsEnvAPI instance for variable management
            udan_tools_variables_defaults: Default values for tool variables
            registry: Tools registry, consulted to define columns (None in
                hand-built factories that never meet a column-definition attribute)
        """
        self._symbols_env = symbols_env
        self._udan_tools_variables_defaults = udan_tools_variables_defaults
        self._registry = registry

    def create_descriptor_from_args(
        self,
        tool_key: str,
        metadata: ToolMetadata,
        children: list[Node],
        at_ds: list[AttributeDescriptor],
        render: list[RenderDescriptor],
        last_operator: list[OperatorDescriptor],
        interpret_fn: Callable[[Node, list, list[RenderDescriptor], list], Node | None],
        ctx: ExecContextAPI,
    ) -> AttributeDescriptor | OperatorDescriptor:
        """Create descriptor (operator or attribute) from bound arguments.

        Args:
            tool_key: Tool key
            metadata: Tool metadata
            children: Argument nodes, render specs already filtered out by the caller
            at_ds: List to collect attribute descriptors
            render: List to collect render tools
            last_operator: List to track the last operator processed
            interpret_fn: Function to interpret child nodes recursively
            ctx: Execution context for query-time logging

        Returns:
            ToolDescriptor (OperatorDescriptor or AttributeDescriptor)
        """
        # Handle nested children: interpret them to get the actual descriptors
        # This happens for parameterized attributes like (attr_name arg)
        processed_children = []
        for ch in children:
            if ch.children:
                # This child has nested children - interpret it to get a descriptor
                # For example: (attribute_tag_checker python) becomes an AttributeDescriptor
                interpreted = interpret_fn(ch, at_ds, render, last_operator)
                if interpreted is not None:
                    processed_children.append(interpreted)
                else:
                    processed_children.append(ch)
            else:
                processed_children.append(ch)

        children = processed_children
        # Now all children should be leaf nodes (descriptors or simple values)
        assert all(not (ch.children) for ch in children), "Nested children not supported yet"

        try:
            # Syntactic sugar: filter with boolean attribute shorthand
            # Allow `filter bool-attr` to be interpreted as `filter bool-attr == True`
            shorthand_result = self._apply_filter_boolean_shorthand(
                metadata, tool_key, children, last_operator, interpret_fn, ctx
            )
            if shorthand_result is not None:
                # Shorthand was applied - use the returned args
                args_dict, on_depth, max_depth, position = shorthand_result
            else:
                # Use bind_with_schema_ext for proper type conversion and defaults
                args_dict, on_depth, max_depth, position = self._bind_with_schema_ext(
                    metadata, children, last_operator, interpret_fn, ctx
                )

            # Post-processing for filter operators: convert boolean string literals
            # This handles both shorthand and explicit syntax for filter_by_attribute
            if metadata.tool_type == "filter":
                args_dict = _convert_filter_boolean_values(args_dict)

            # Convert to list format expected by descriptors
            final_args = list(args_dict.items())
        except ExceptionWithAdvice as e:
            # A QueryMiss is deliberately not one of these: a missing required
            # argument that asks for help rides past the binding to the walk's
            # swap point, where the registered answerers decide what continues
            ctx.debug(f"Exception during tool binding: {e}")
            raise
        except ValueError as e:
            # Type conversion failures (convert_value) - keep them as clean
            # query errors instead of raw tracebacks
            raise ExceptionWithAdvice(f"Cannot bind arguments of '{metadata.name}': {e}") from e

        if metadata.tool_type != ATTRIBUTE:
            tool_args_for_create = _operator_sp_args(on_depth, max_depth, position)
            descriptor = OperatorDescriptor.create(tool_key, final_args, tool_args=tool_args_for_create)
            # Track this operator: a question about the chain names it
            last_operator.append(descriptor)
        elif isinstance(metadata, AttributeMetadata) and metadata.attribute_type == ATTRIBUTE_TYPE_COLUMN:
            # A column-definition attribute is a column factory, not a value: the
            # definition registers the column in the registry (the formula rides in
            # the column's metadata) and the descriptor is the column itself, so the
            # native attribute path calculates and renders it under its own name
            column_name = self._define_column(tool_key, dict(final_args), ctx)
            descriptor = AttributeDescriptor.create(column_name)
        else:
            descriptor = AttributeDescriptor.create(tool_key, final_args, metadata=metadata)

        if isinstance(descriptor, AttributeDescriptor):
            ctx.debug(f"{descriptor=}")
            if descriptor not in at_ds:
                at_ds.append(descriptor)

        ctx.debug(f"resolved tool: {descriptor}")
        return descriptor

    def _define_column(self, tool_key: str, args: dict[str, Any], ctx: ExecContextAPI) -> str:
        """Define a column through the attribute's registered definition function.

        The function is the column factory of a column-definition attribute: it
        registers the column for this query and returns its name.

        Args:
            tool_key: Name of the column-definition attribute (e.g. cattr)
            args: Bound arguments of the chain item (the formula, the optional name)
            ctx: Execution context whose query the column is defined in

        Returns:
            Name of the defined column

        Raises:
            ExceptionWithAdvice: If the definition function is missing or does not
                return a column name
        """
        definition_fn = self._registry.get_function(tool_key) if self._registry else None
        if definition_fn is None:
            raise ExceptionWithAdvice(f"'{tool_key}' defines columns, but has no registered definition function")
        # Only the query context and the bound arguments are passed: registry and
        # attribute runtime are injected dependencies of the definition function
        column_name = definition_fn(ctx=ctx, **args)
        if not isinstance(column_name, str) or not column_name:
            raise ExceptionWithAdvice(f"'{tool_key}' did not return a column name (got {column_name!r})")
        return column_name

    def _bind_with_schema_ext(
        self,
        metadata,
        args: list[Node],
        last_operator: list,
        interpret_fn: Callable,
        ctx: ExecContextAPI,
    ) -> tuple[dict, DepthSelector | None, int | None, tuple[int, ...] | None]:
        """Bind parsed argument nodes to a tool metadata.

        Extended version that works with parsed Node objects instead of strings.
        Handles type conversion, defaults, at_d resolution, and named arguments (--key=value).

        Args:
            metadata: ToolMetadata with parameters schema
            args: List of argument nodes (from parsed tree)
            last_operator: List to track the chain's resolved operators
            interpret_fn: Function to interpret child nodes recursively
            ctx: Execution context for query-time logging

        Returns:
            Tuple of (bound_args, on_depth, max_depth, position) where:
            - bound_args: Dictionary of bound arguments with proper types and defaults filled
            - on_depth: depth selector if --on-depth was specified (a level, "all" or "leaf"), None otherwise
            - max_depth: int max depth level if --max-depth was specified, None otherwise
            - position: hierarchy path tuple if --position was specified, None otherwise

        Raises:
            ExceptionWithAdvice: If required arguments are missing
        """
        parameters_schema = metadata.parameters
        validate_parameters_schema(parameters_schema)

        props = parameters_schema.get("properties", {})
        required = set(parameters_schema.get("required", []))
        prop_names = list(props.keys())

        # Check for varargs parameter (marked with description == 'vararg')
        vararg_param = None
        for prop_name, prop_def in props.items():
            if prop_def.get("description") == "vararg":
                vararg_param = prop_name
                break

        result: dict[str, object] = {}

        # Split args into positional and named (e.g., --key=value)
        # Also extract framework-level parameters like --on-depth and --max-depth
        positional, named, on_depth, max_depth, position = self._split_args(args, props, metadata)

        # Handle varargs: collect all positional arguments into a list.
        # Named parameters (e.g. `field: str = "tags"`) may coexist with a vararg:
        # positional arguments feed the vararg, while named --key=value arguments
        # bind to their matching parameters (see named-arg binding below).
        if vararg_param:
            # For varargs, collect all positional arguments, converting each string
            # element per the vararg's items schema: a `list[int]` vararg rejects a
            # word the way an int parameter does, at binding time - not when the tool
            # happens to run (a depth selector can keep it from ever running).
            # Non-string elements pass through, like any converted value does;
            # convert_value reads the parameter out of a properties dict, so the
            # items schema rides under the vararg's own name
            element_props = {vararg_param: _vararg_items_schema(props[vararg_param])}
            vararg_values = []
            for arg_node in positional:
                value = _get_positional_arg_value(arg_node)
                if isinstance(value, str):
                    value = convert_value(element_props, vararg_param, value)
                vararg_values.append(value)
            result[vararg_param] = vararg_values
        else:
            # Bind positional args in order (non-vararg case)
            # Framework parameters are injected automatically (ctx, item, items, nodes)
            bindable_params = [p for p in prop_names if p not in FRAMEWORK_PARAMS_ALL]
            if len(positional) > len(bindable_params):
                # A positional argument with no parameter to bind to would be
                # silently dropped by zip below - raise instead
                extra = [_get_positional_arg_value(arg_node) for arg_node in positional[len(bindable_params) :]]
                raise ExceptionWithAdvice(
                    f"'{metadata.name}' takes {len(bindable_params)} positional argument(s) "
                    f"({', '.join(bindable_params) if bindable_params else 'none'}), "
                    f"but got {len(positional)}: {extra}. "
                    f"Extra arguments have no parameter to bind to; "
                    f"use --key=value syntax for named arguments."
                )
            for arg_node, prop_name in zip(positional, bindable_params):
                bound_value = self._bind_positional_arg(arg_node, prop_name, props, last_operator, interpret_fn, ctx)
                result[prop_name] = bound_value

        # Bind named args (these override positional)
        for key, value in named.items():
            result[key] = convert_value(props, key, value)

        # Check if required arguments are satisfied
        self._check_required_args(metadata, result, required)

        # Fill in defaults from config first (higher priority than schema defaults)
        # Then fill in schema defaults for args that still don't have values
        self._fill_missing_defaults(metadata, result, props)

        return result, on_depth, max_depth, position

    def _split_args(
        self, args: list[Node], props: dict, metadata
    ) -> tuple[list[Node], dict, DepthSelector | None, int | None, tuple[int, ...] | None]:
        """Split argument nodes into positional and named, extracting framework depths.

        Handles --key=value / --flag / --noflag and bare key=value (without dashes,
        only when the key is a known parameter); anything else stays positional.

        Args:
            args: Argument nodes from the parsed tree
            props: Parameter properties schema
            metadata: ToolMetadata (for error messages)

        Returns:
            Tuple of (positional nodes, named args dict, on_depth, max_depth, position)
        """
        positional: list[Node] = []
        named: dict = {}
        on_depth: DepthSelector | None = None
        max_depth = None
        position = None

        for arg_node in args:
            item = arg_node.item
            if isinstance(item, str) and item.startswith("--"):
                # Parse named argument: --key=value, --flag, --noflag
                parsed = parse_named_argument(item, set(props.keys()))
                if parsed is not None:
                    key, value = parsed
                    # Check for framework-level --on-depth / --max-depth / --position parameters
                    if key == ARG_ON_DEPTH:
                        on_depth = _framework_depth_arg("--on-depth", value)
                    elif key == ARG_MAX_DEPTH:
                        max_depth = _framework_int_arg("--max-depth", value)
                    elif key == ARG_POSITION:
                        position = _framework_position_arg("--position", value)
                    elif key not in props:
                        raise self._build_unexpected_argument_error(metadata, key, props)
                    else:
                        named[key] = value
                else:
                    positional.append(arg_node)
            elif (
                isinstance(item, str)
                and "=" in item
                and not item.startswith(NODE_STRING_PREFIX)
                and item.partition("=")[0].strip() in props
            ):
                # Named argument without dashes: key=value (e.g. attr(style=short));
                # only when the key is a known parameter - anything else stays positional
                named[item.partition("=")[0].strip()] = item.partition("=")[2]
            else:
                positional.append(arg_node)

        return positional, named, on_depth, max_depth, position

    def _bind_positional_arg(
        self,
        arg_node: Node,
        prop_name: str,
        props: dict,
        last_operator: list,
        interpret_fn: Callable,
        ctx: ExecContextAPI,
    ) -> object:
        """Bind a single positional argument to its parameter.

        Args:
            arg_node: Argument node to bind
            prop_name: Parameter name to bind to
            props: Parameter properties schema
            last_operator: List tracking the chain's resolved operators
            interpret_fn: Function to interpret child nodes recursively
            ctx: Execution context for query-time logging

        Returns:
            Bound and converted value (AttributeDescriptor or converted value)

        Raises:
            ExceptionWithAdvice: If binding fails
        """
        if prop_name == "at_d":
            # Recursively interpret to get attribute descriptor
            return self._resolve_at_d(arg_node, last_operator, interpret_fn, ctx)

        # Resolve the argument value
        value = self._resolve_regular_arg_value(arg_node, last_operator, prop_name, interpret_fn)

        # Convert value to proper type
        return convert_value(props, prop_name, value)

    def _check_required_args(self, metadata, result: dict, required: set) -> None:
        """Check if all required arguments are satisfied.

        Args:
            metadata: ToolMetadata
            result: Current bound arguments
            required: Set of required parameter names

        Raises:
            ExceptionWithAdvice: If required arguments are missing
        """
        missing = required - result.keys()
        if not missing:
            return

        # Special case: at_d as missing arg is a miss, not a binding error - it
        # rides to the walk's swap point, where the registered answerers answer it
        if "at_d" in missing:
            raise QueryMiss(
                pattern="",
                tool_type="attribute",
                reason="required 'at_d' is missing - listing the attribute tools",
            )

        # Note: API type parameters (like SymbolsEnvAPI) are handled by the dependency injection
        # system at call time. They should have default values (| None) so they're not in 'required'.
        # If someone creates a tool with a required API parameter, they'll get a missing arg error
        # which is correct - they should add a default value.

        # Special case: the framework-injected arguments of a nested operator - the kind
        # declares them (a nested replacer receives items and nodes), so a descriptor may
        # leave them out of its arguments. The kind comes coerced: metadata a caller
        # built by hand may carry the kind's name as a bare string.
        meta = metadata.meta or {}
        tool_type = metadata.tool_type
        if not isinstance(tool_type, ToolKind):
            tool_type = ToolKind(name=str(tool_type))
        is_nested = meta.get("is_nested", False) if isinstance(meta, dict) else False
        framework_injected = set(tool_type.injected_args)
        if is_nested and framework_injected:
            missing_after_framework = missing - framework_injected
            if not missing_after_framework or missing_after_framework == framework_injected:
                # All missing args will be injected by the framework
                return

        # Special case: attribute_runtime is injected by apply_filter and apply_grouper
        # For operators that work with attributes, attribute_runtime is provided by the framework
        if tool_type in ("filter", "grouper") and "attribute_runtime" in missing:
            missing_without_attr_runtime = missing - {"attribute_runtime"}
            if not missing_without_attr_runtime:
                # Only attribute_runtime is missing, which is fine - it will be provided at execution time
                return

        # Special case: item parameter for operators that receive items from a chain
        # When an operator with an 'item' parameter is used after another operator (e.g., "a, b"),
        # the 'item' should be implicitly provided from the previous operator's output.
        # The kind's filter_group is what says it is an operator; attributes answer
        # their own branches below.
        if "item" in missing and tool_type.filter_group == "operator":
            # For operators in a chain, 'item' is considered provided by the framework
            # Check if 'item' is the only missing argument
            missing_without_item = missing - {"item"}
            if not missing_without_item:
                # Only 'item' is missing, which is fine - it will be provided at execution time
                return

        # Special case: attributes always have 'item' as a framework parameter
        # Aggregate attributes have 'items' instead of 'item'
        if "item" in missing and tool_type == ATTRIBUTE:
            missing = missing - {"item"}
            if not missing:
                return
        if (
            "items" in missing
            and tool_type == ATTRIBUTE
            and metadata.meta.get("attribute_type") == ATTRIBUTE_TYPE_AGGREGATE
        ):
            missing = missing - {"items"}
            if not missing:
                return

        raise ExceptionWithAdvice(f"Missing required arguments: {missing}")

    def _fill_missing_defaults(self, metadata, result: dict, props: dict) -> None:
        """Fill in missing arguments from config and schema defaults.

        Args:
            metadata: ToolMetadata
            result: Current bound arguments (modified in place)
            props: Parameter properties schema
        """
        tool_name = metadata.name

        for name, spec in props.items():
            if name in result:
                continue

            # Check config first
            config_value = self._udan_tools_variables_defaults.get(tool_name, {}).get(name)
            if config_value is not None:
                result[name] = config_value
            # Then fall back to schema default
            elif "default" in spec:
                result[name] = spec["default"]

    def _build_unexpected_argument_error(self, metadata, key: str, props: dict) -> ExceptionWithAdvice:
        """Build a helpful error message for unexpected named arguments.

        Args:
            metadata: ToolMetadata
            key: The invalid parameter name
            props: Dictionary of parameter definitions from schema

        Returns:
            ExceptionWithAdvice with helpful message - names the miss and the
            kind, points at `name?` for the tool's help, and lists the user
            parameters one per line
        """
        user_params = []
        for prop_name, prop_def in props.items():
            if prop_name in FRAMEWORK_PARAMS_ALL:
                continue
            if prop_def.get("description") == "vararg":
                continue
            # Build param signature: name: type(=default)
            param_type = prop_def.get("type", "any")
            param_parts = [f"{prop_name}: {param_type}"]
            if "default" in prop_def:
                default_val = prop_def["default"]
                if isinstance(default_val, str) and len(default_val) > _MAX_PARAM_DEFAULT_LENGTH:
                    default_val = default_val[:_MAX_PARAM_DEFAULT_LENGTH] + "..."
                param_parts.append(f"(={default_val})")
            user_params.append("".join(param_parts))

        kind_label = "attribute" if metadata.tool_type == ATTRIBUTE else "operator"
        # One parameter per line (the inline list got hard to read once the
        # signatures grew); `name?` shows the tool's help, so point there
        if user_params:
            param_lines = [f"  - {param}" for param in user_params]
        else:
            param_lines = ["  (no user parameters)"]
        return ExceptionWithAdvice(
            "\n".join(
                [
                    f"- For the {kind_label} `{metadata.name}`, there is no parameter `--{key}`",
                    f"- to show help write `{metadata.name}?`",
                    "- Available parameters:",
                    *param_lines,
                ]
            )
        )

    def _apply_filter_boolean_shorthand(
        self,
        metadata,
        tool_key: str,
        children: list,
        last_operator: list[OperatorDescriptor],
        interpret_fn: Callable,
        ctx: ExecContextAPI,
    ) -> tuple[dict, DepthSelector | None, int | None, tuple[int, ...] | None] | None:
        """Apply boolean shorthand syntax for filter operators.

        Allows:
        - `filter bool-attr` to be interpreted as `filter bool-attr == True`
        - `filter !bool-attr` to be interpreted as `filter bool-attr == False`

        The shorthand applies when the single given attribute cannot form a
        complete comparison by itself: the filter has a `value` parameter that
        is required (bare binding would fail) or effectively defaults to None
        (bare binding would compare against None). Whether this holds is
        decided from the parameter schema up front, then the args are bound
        exactly once with the comparison appended.

        "Single given attribute" counts positional arguments only: framework
        flags (`--on-depth`, `--max-depth`, `--position`) written beside the
        attribute are not arguments of the comparison, so `filter_by_attribute
        is_even --on-depth=1` still takes the shorthand. Named arguments (`--key=value`
        of the filter's own parameters) keep disabling it, as they did before.

        Args:
            metadata: Tool metadata
            tool_key: Tool key
            children: List of child nodes
            last_operator: List to track the last operator processed
            interpret_fn: Function to interpret child nodes recursively
            ctx: Execution context for query-time logging

        Returns:
            Tuple of (bound_args, on_depth, max_depth, position) if shorthand was applied, None otherwise
        """
        if metadata.tool_type != "filter":
            return None

        # The split tells the positional arguments from the framework flags and
        # named args; the flag nodes stay in the list below, so the binding's
        # own split re-reads them and on_depth lands in tool_args as usual
        props = metadata.parameters.get("properties", {})
        positional, named, _, _, _ = self._split_args(children, props, metadata)
        if len(positional) != 1 or named:
            return None

        # Negation shorthand: !attr -> attr == False
        attr_node = positional[0]
        child_item = attr_node.item
        if isinstance(child_item, str) and child_item.startswith("!"):
            attr_name = child_item[1:]
            if not attr_name:
                return None  # Just '!' is not valid
            attr_node = Node.leaf(attr_name)
            comparison_value = "False"
        else:
            comparison_value = "True"

        if not self._filter_comparison_is_unfilled(metadata):
            return None

        other_nodes = [ch for ch in children if ch is not positional[0]]
        children_with_comparison = [attr_node, *other_nodes, Node.leaf("=="), Node.leaf(comparison_value)]
        args_dict, on_depth, max_depth, position = self._bind_with_schema_ext(
            metadata, children_with_comparison, last_operator, interpret_fn, ctx
        )
        ctx.debug(f"Filter shorthand: added default == {comparison_value} for {tool_key}")
        return args_dict, on_depth, max_depth, position

    def _filter_comparison_is_unfilled(self, metadata) -> bool:
        """Check whether a single-argument filter leaves its comparison unfilled.

        The comparison is unfilled when the filter has a `value` parameter that
        is either required or effectively defaults to None (config default or
        schema default). Filters without a `value` parameter (e.g. vararg-only
        `greps`) never take the shorthand.

        Args:
            metadata: Tool metadata

        Returns:
            True if the boolean shorthand should fill the comparison
        """
        parameters_schema = metadata.parameters
        props = parameters_schema.get("properties", {})
        value_spec = props.get("value")
        if value_spec is None or value_spec.get("description") == "vararg":
            return False
        if "value" in parameters_schema.get("required", []):
            return True
        config_default = self._udan_tools_variables_defaults.get(metadata.name, {}).get("value")
        if config_default is not None:
            return False
        return value_spec.get("default") is None

    def _resolve_at_d(
        self, arg_node: Node, last_operator: list, interpret_fn: Callable, ctx: ExecContextAPI
    ) -> AttributeDescriptor:
        """Resolve an at_d argument by interpreting the node.

        Args:
            arg_node: Node containing the at_d reference
            last_operator: List tracking the chain's resolved operators
            interpret_fn: Function to interpret child nodes recursively
            ctx: Execution context for query-time logging

        Returns:
            Resolved AttributeDescriptor

        Raises:
            ExceptionWithAdvice: If resolution fails
        """
        # Check if the arg_node already contains an AttributeDescriptor (from prior interpretation)
        # This happens when parameterized attributes like (attr_name arg) are pre-interpreted
        if isinstance(arg_node.item, AttributeDescriptor):
            ctx.debug(f"Using pre-interpreted AttributeDescriptor: {arg_node.item}")
            return arg_node.item

        # Check if arg_node is a ROOT node with a child that is an AttributeDescriptor
        # This happens when (add_values 1 2) is interpreted and stored as ROOT(AttrD)
        if isinstance(arg_node.item, str) and arg_node.item == NODE_ROOT_ITEM and arg_node.children:
            child = arg_node.children[0]
            if isinstance(child.item, AttributeDescriptor):
                ctx.debug(f"Using AttributeDescriptor from ROOT node: {child.item}")
                return child.item

        node = interpret_fn(arg_node, [], [], last_operator)
        if node is None:
            raise ExceptionWithAdvice(f"Failed to resolve at_d from node: {arg_node}")
        if not isinstance(node.item, AttributeDescriptor):
            raise ExceptionWithAdvice(f"at_d must resolve to AttributeDescriptor, got: {type(node.item)}")
        return node.item

    def _resolve_regular_arg_value(
        self,
        arg_node: Node,
        last_operator: list,
        prop_name: str | None = None,
        interpret_fn: Callable | None = None,
    ) -> object:
        """Resolve a regular (non-at_d) argument value.

        Handles variable references, ROOT unwrapping, and interpretation.

        Args:
            arg_node: Argument node to resolve
            last_operator: List tracking the chain's resolved operators
            prop_name: Parameter name (for determining if variable name or value should be returned)
            interpret_fn: Function to interpret child nodes recursively

        Returns:
            Resolved argument value (str, None, or any item from the forest)
        """
        result = arg_node.item

        # Check if the argument is a variable reference (NODE_VAR_PREFIX)
        if isinstance(arg_node.item, str) and arg_node.item.startswith(NODE_VAR_PREFIX):
            var_name = arg_node.item[len(NODE_VAR_PREFIX) :]
            if prop_name and "var" in prop_name.lower():
                return var_name
            if self._symbols_env.has_variable(var_name):
                var_forest, _ = self._symbols_env.get_variable_with_type(var_name)
                items = var_forest.items
                return items[0] if items else None
            raise ValueError(f"Variable '{var_name}' is not defined")

        # Handle simple leaf nodes (no children): strings and scalar literals.
        # A scalar literal (e.g. the 3 in attr(3)) is a value, not a query to
        # interpret - interpreting it sends it into tool resolution,
        # which crashes on non-string items ("." in 3).
        if isinstance(arg_node.item, (int, float, bool)) and not arg_node.children:
            return result
        if isinstance(arg_node.item, str) and not arg_node.children:
            if arg_node.item.startswith(NODE_STRING_PREFIX):
                return arg_node.item[len(NODE_STRING_PREFIX) :]
            return result

        if interpret_fn is None:
            return result

        if isinstance(arg_node.item, AttributeDescriptor):
            return arg_node.item

        interpreted = interpret_fn(arg_node, [], [], last_operator)
        if interpreted is None:
            return None

        if interpreted.item == NODE_ROOT_ITEM and len(interpreted.children) == 1:
            return interpreted.children[0].item

        return interpreted.item if interpreted.item != NODE_ROOT_ITEM else interpreted


def _operator_sp_args(
    on_depth: DepthSelector | None, max_depth: int | None, position: tuple[int, ...] | None
) -> dict | None:
    """Assemble descriptor tool_args: query-level on_depth/max_depth/position.

    Args:
        on_depth: on_depth value from --on-depth (a level, "all" or "leaf"), None if not specified
        max_depth: max_depth value from --max-depth, None if not specified
        position: hierarchy path tuple from --position, empty when switched off

    Returns:
        Dict of tool_args, or None when nothing was specified. A switched-off position
        stores nothing: the descriptor is the one that had no --position at all.
    """
    tool_args: dict = {}
    if on_depth is not None:
        tool_args[ARG_ON_DEPTH] = on_depth
    if max_depth is not None:
        tool_args[ARG_MAX_DEPTH] = max_depth
    if position:
        tool_args[ARG_POSITION] = position
    return tool_args or None


def _framework_int_arg(flag: str, value: str) -> int:
    """Convert a framework-level --flag=value argument value to an integer.

    Args:
        flag: Flag name as written in queries (e.g. "--max-depth"), used in the error message
        value: Raw string value from the query

    Returns:
        Parsed integer value

    Raises:
        TypeError: If the value is not an integer
    """
    try:
        return int(value)
    except ValueError, TypeError:
        raise TypeError(f"{flag} must be an integer, got: {value}")


def _framework_depth_arg(flag: str, value: str) -> DepthSelector:
    """Convert a framework-level --on-depth=value argument value to a depth selector.

    Besides a depth level, the value can be one of the two selector words: "all"
    (every node of the input tree) and "leaf" (nodes without children). The words
    are matched exactly; anything that is neither of them nor an integer is an
    error naming the accepted values.

    Args:
        flag: Flag name as written in queries (e.g. "--on-depth"), used in the error message
        value: Raw string value from the query

    Returns:
        Parsed depth selector: a level, "all" or "leaf"

    Raises:
        TypeError: If the value is not an integer, "all" or "leaf"
    """
    if value == "all":
        return "all"
    if value == "leaf":
        return "leaf"
    try:
        return int(value)
    except ValueError, TypeError:
        raise TypeError(f"{flag} must be an integer, 'all' or 'leaf', got: {value}")


def _framework_position_arg(flag: str, value: str) -> tuple[int, ...]:
    """Convert a framework-level --position=value argument to a hierarchy path.

    The path is dot-separated sibling indexes ("1.2" = children[1].children[2]).
    The off-switches - an empty value (`--position=""`) and `-1` - come back as the
    empty path: no position, the operator applies everywhere. A `-1` deeper in a path
    stays an error, only the whole value switches it off.

    Args:
        flag: Flag name as written in queries ("--position"), used in the error message
        value: Raw string value from the query

    Returns:
        Tuple of sibling indexes, one per path component; empty when no position is set

    Raises:
        TypeError: If the value is not a dot-separated path of integers
    """
    if value in ("", "-1"):
        return ()
    try:
        path = tuple(int(component) for component in value.split("."))
    except ValueError as e:
        raise TypeError(f"{flag} must be a dot-separated path of integers, got: {value}") from e
    if any(component < 0 for component in path):
        raise TypeError(f"{flag} must be a path of non-negative indexes, got: {value}")
    return path


def _get_positional_arg_value(arg_node: Node) -> object:
    """Get the actual value from a positional argument node."""
    item = arg_node.item
    if isinstance(item, str) and item.startswith(NODE_STRING_PREFIX):
        return item[len(NODE_STRING_PREFIX) :]
    if isinstance(item, (str, int, float, bool, list, dict)):
        return item
    if isinstance(item, (OperatorDescriptor, AttributeDescriptor)):
        return item
    return item


def _vararg_items_schema(param_def: dict) -> dict:
    """Extract the items schema of a vararg parameter, for element conversion.

    Args:
        param_def: JSON schema property definition of the vararg parameter

    Returns:
        Schema of one element (e.g. {"type": "integer"} for `list[int]`), empty
        when the vararg declares none - elements then pass through unconverted
    """
    if param_def.get("type") == "array":
        return param_def.get("items", {})
    for member in param_def.get("anyOf", []):
        if member.get("type") == "array":
            return member.get("items", {})
    return {}


def _convert_filter_boolean_values(args_dict: dict) -> dict:
    """Convert boolean string literals to actual booleans for filter operators."""
    value = args_dict.get("value")
    if isinstance(value, str):
        converted = convert_boolean_string(value)
        if converted is not None:
            args_dict["value"] = converted
    return args_dict
