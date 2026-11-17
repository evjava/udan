"""Public API for Udan operator types.

The kind-blind part every operator kind shares: the descriptor and metadata an
operator resolves to, and the Operator contract the engine evaluates. The operator
kinds live in the core's operator package (udan.operator, one plugins_operator_*.py
module per kind) and a host package may add kinds of its own - each reaches the
framework through the same
declarations: the kind service's KINDS fills the vocabulary, the chain service's
apply_chain_step takes its groups, and the registered applicator applies its descriptors.
"""

from collections.abc import Iterable

from udan.core.api_chain_context import ChainContextAPI
from udan.core.api_constants import ARG_MAX_DEPTH
from udan.core.api_exec_context import ExecContextAPI
from udan.core.api_forests import Node
from udan.core_tools_loading.api_tools import ToolDescriptor, ToolMetadata


class Operator:
    """Base class for operators.

    An operator represents a specific operation that can be applied to
    transform, filter, or otherwise process items in a forest.

    Attributes:
        op_d: The operator descriptor containing name and arguments
    """

    op_d: OperatorDescriptor

    def apply(
        self,
        ctx: ExecContextAPI,
        attr_ctx: ChainContextAPI,
        children: Iterable[Node],
    ) -> Iterable[Node]:
        """Apply this operator to the given children.

        Args:
            ctx: The execution context
            attr_ctx: The attributes context
            children: The child nodes to process

        Returns:
            Iterable of result nodes
        """
        raise NotImplementedError


# The query keyword of an operator kind is data on the kind (the `query_keyword`
# field: "insert" for inserters, "filter" for filters, ...), so a
# plugin kind can introduce a keyword of its own; the loader resolves a keyword back to the
# kind that claims it (insert -> inserter, filter -> filter, ...).


class OperatorDescriptor(ToolDescriptor):
    """Descriptor for an operator.

    Extends ToolDescriptor with operator-specific functionality.
    """

    def get_max_depth(self) -> int:
        """Get the maximum depth for this operator.

        Returns:
            Maximum depth value from tool_args, or 0 if not specified
        """
        tool_args = self.tool_args
        for arg_k, arg_v in tool_args:
            if arg_k == ARG_MAX_DEPTH:
                assert isinstance(arg_v, int)
                return arg_v
        # default
        return 0


class OperatorMetadata(ToolMetadata):
    """Metadata for operator tools.

    The item contract (item_type / output_type / output_semantic), the nesting flag
    and the attribute dependencies are ToolMetadata fields: every kind's
    metadata carries them, so a reader of the contract needs no operator metadata.
    What this class adds is the marker a tool is an operator's, which the walk
    and the per-kind listing surfaces read; the kind itself is `tool_type`, as on every
    metadata.
    """
