"""Public API for variable handling in Udan queries.

This module defines the public interface for variable assignment and reference
handling during query processing.
"""

from collections.abc import Callable

from udan.core.api_attributes import AttributeDescriptor
from udan.core.api_exec_context import ExecContextAPI
from udan.core.api_forests import Node
from udan.core.api_operators import OperatorDescriptor
from udan.renders.api_renders import RenderDescriptor


class VariableHandlerAPI:
    """Interface for variable assignment and reference handling.

    This class provides methods for handling variable assignments (:=var_name)
    and variable references ($var_name) in query processing.
    """

    def get_anon_var_name(self) -> str:
        """Generate a unique anonymous variable name.

        Returns:
            Anonymous variable name (e.g., "_anon0", "_anon1", ...)
        """
        raise NotImplementedError

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
        raise NotImplementedError

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
        raise NotImplementedError
