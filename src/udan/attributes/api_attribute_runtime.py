"""Public API for attribute value resolution.

This module defines the public API interface for computing attribute values.
"""

from __future__ import annotations

from typing import Any

from udan.attributes.api_attribute_contexts import AttributesContextAPI
from udan.attributes.api_attribute_storage import AttributeStorageAPI
from udan.core.api_attributes import ATTRIBUTE, AttributeDescriptor, AttributeValue
from udan.core.api_chain_routing import ChainStepServiceAPI
from udan.core.api_exec_context import ExecContextAPI
from udan.core.api_forests import Forest, Item, Node
from udan.core_tools_loading.api_tool_kinds import ToolKindService
from udan.core_tools_loading.api_tools import ToolKind
from udan.core_tools_loading.api_tools_registry import ToolsRegistryAPI


class AttributeRuntimeAPI(ToolKindService, ChainStepServiceAPI):
    """API interface for attribute value resolution.

    This class defines the public API for computing attribute values
    for items using registered attribute functions.

    It is a kind service: the attribute kind is its own, so a consumer of the
    interface - the chain routing - reads the ownership and the chain step contract
    from the same object.

    Attributes:
        attribute_storage: Attribute storage for on-demand calculation (may be None)
        registry: Tools registry the attribute functions resolve from
    """

    KINDS: tuple[ToolKind, ...] = (ATTRIBUTE,)
    """The kind this runtime owns: attributes, the default kind."""

    attribute_storage: AttributeStorageAPI | None
    registry: ToolsRegistryAPI

    def calculate_attributes_in_forest(
        self,
        forest: Forest,
        attr_descriptors: list[AttributeDescriptor],
        ctx: ExecContextAPI,
    ) -> None:
        """Calculate attributes for all items in a forest.

        Args:
            forest: The forest to calculate attributes for
            attr_descriptors: List of attribute descriptors to calculate
            ctx: Execution context for query-time logging
        """
        raise NotImplementedError

    def calculate_aggregate_attributes(
        self,
        context: AttributesContextAPI,
        nodes: list[Node],
        target_item: Item,
        at_ds: list[AttributeDescriptor],
        ctx: ExecContextAPI,
    ) -> None:
        """Compute aggregate attributes over one stage of a chain.

        The stage-level aggregate entry next to the forest-level one: the bottom-up
        walk stores the aggregate of every inner node's subtree on that node and the
        global value on the stage's root item.

        Args:
            context: Forest context with attribute storage
            nodes: The stage's top-level nodes (its items exist at this chain position)
            target_item: Item the global aggregate value is stored on
            at_ds: Aggregate attribute descriptors to compute
            ctx: Execution context for query-time logging
        """
        raise NotImplementedError

    def calculate_attribute_descriptor_in_node(
        self, context: AttributesContextAPI, at_d: AttributeDescriptor, node: Node
    ) -> None:
        """Calculate attribute for a node and its descendants by descriptor.

        Args:
            context: Forest context with attribute storage
            at_d: Attribute descriptor to calculate
            node: Node to calculate attribute for
        """
        raise NotImplementedError

    def calculate_attribute_descriptor_for_child(
        self, context: AttributesContextAPI, at_d: AttributeDescriptor, child: Node
    ) -> None:
        """Calculate attribute for a single child node by descriptor.

        Args:
            context: Forest context with attribute storage
            at_d: Attribute descriptor to calculate
            child: Node to calculate attribute for (not recursively)
        """
        raise NotImplementedError

    def get_attribute_value(
        self,
        attr_d: AttributeDescriptor,
        item: Item,
        ctx: ExecContextAPI,
    ) -> AttributeValue:
        """Get attribute value for an item.

        Args:
            attr_d: Attribute descriptor
            item: Item to get attribute value from
            ctx: Execution context for query-time logging

        Returns:
            Attribute value

        Raises:
            Exception: If attribute cannot be computed
        """
        raise NotImplementedError

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
            AttributesContext instance
        """
        raise NotImplementedError
