"""Public API for descriptor creation in Udan queries.

This module defines the public interface for creating operator and attribute
descriptors from query arguments.
"""

from collections.abc import Callable

from udan.core.api_attributes import AttributeDescriptor
from udan.core.api_exec_context import ExecContextAPI
from udan.core.api_forests import Node
from udan.core.api_operators import OperatorDescriptor
from udan.core_tools_loading.api_tools import ToolMetadata
from udan.renders.api_renders import RenderDescriptor


class DescriptorFactoryAPI:
    """Interface for creating operator and attribute descriptors.

    This class provides methods for creating descriptors from query arguments,
    handling parameter binding, and managing nested children.
    """

    def create_descriptor_from_args(
        self,
        tool_key: str,
        metadata: ToolMetadata,
        children: list[Node],
        at_ds: list[AttributeDescriptor],
        render: list[RenderDescriptor],
        last_operator: list[OperatorDescriptor],
        interpret_fn: Callable,
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
        raise NotImplementedError
