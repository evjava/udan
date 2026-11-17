"""Variable handling for QueryProcessor."""

import itertools
from collections.abc import Callable

from udan.core.api_attributes import AttributeDescriptor
from udan.core.api_constants import NODE_ASSIGN_PREFIX, NODE_VAR_PREFIX
from udan.core.api_exec_context import ExecContextAPI
from udan.core.api_forests import Node
from udan.core.api_operators import OperatorDescriptor
from udan.core.api_symbols_env import SymbolsEnvAPI
from udan.core.api_variable_handler import VariableHandlerAPI
from udan.renders.api_renders import RenderDescriptor


class VariableHandler(VariableHandlerAPI):
    """Handles variable assignment and references."""

    def __init__(self, symbols_env: SymbolsEnvAPI):
        """Initialize variable handler.

        Args:
            symbols_env: Symbol environment for variable storage
        """
        self._symbols_env = symbols_env
        self._anon_counter = itertools.count()

    def get_anon_var_name(self) -> str:
        """Generate a unique anonymous variable name.

        Returns:
            Anonymous variable name (e.g., "_anon0", "_anon1", ...)
        """
        return f"_anon{next(self._anon_counter)}"

    def handle_assignment(
        self,
        query_node: Node,
        item: str,
        at_ds: list[AttributeDescriptor],
        render: list[RenderDescriptor],
        last_operator: list[OperatorDescriptor],
        interpret_fn: Callable[[Node, list, list[RenderDescriptor], list], Node | None],
        ctx: ExecContextAPI,
    ) -> Node:
        """Handle variable assignment: :=var_name.

        Args:
            query_node: Node containing the assignment
            item: The assignment string (e.g., ":=var_name")
            at_ds: List to collect attribute descriptors
            render: List to collect render tools
            last_operator: List to track the last operator processed
            interpret_fn: Function to interpret child expressions
            ctx: Execution context for query-time logging

        Returns:
            Node with assignment marker

        Raises:
            ValueError: If no expression is provided for assignment
        """
        var_name = item[2:]  # Remove := prefix
        ctx.debug(f"Variable assignment: {var_name}")

        # Interpret the expression being assigned
        if not query_node.children:
            raise ValueError(f"Variable assignment '{var_name}' requires an expression")

        # Interpret the child expression
        child_result = interpret_fn(query_node.children[0], at_ds, render, last_operator)

        # We need to resolve this to a Forest
        # For now, we'll store a marker and let the query processor handle it
        # Return a special marker that the query processor will recognize
        if child_result:
            return Node.create(f"{NODE_ASSIGN_PREFIX}{var_name}", [child_result])
        else:
            return Node.create(f"{NODE_ASSIGN_PREFIX}{var_name}", [])

    def handle_reference(self, item: str, ctx: ExecContextAPI) -> Node:
        """Handle variable reference: $var_name.

        Args:
            item: The variable reference string (e.g., "$var_name")
            ctx: Execution context for query-time logging

        Returns:
            Node with variable marker

        Raises:
            ValueError: If variable is not defined
        """
        var_name = item[1:]  # Remove $ prefix
        if self._symbols_env.has_variable(var_name):
            # This is a standalone variable reference (e.g., just "$a" to retrieve it)
            ctx.debug(f"Variable reference: ${var_name}")
            # Return a marker for variable expansion
            return Node.leaf(f"{NODE_VAR_PREFIX}{var_name}")
        else:
            raise ValueError(f"Variable '${var_name}' is not defined")
