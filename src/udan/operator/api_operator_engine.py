"""Public API for operator application engine.

This module defines the public API interface for applying operators to
tree structures.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from pydantic import BaseModel

from udan.core.api_attributes import AttributeDescriptor
from udan.core.api_chain_context import ChainContextAPI
from udan.core.api_chain_routing import ChainStepServiceAPI
from udan.core.api_constants import DepthSelector
from udan.core.api_exec_context import ExecContextAPI
from udan.core.api_forests import Forest, Node
from udan.core_tools_loading.api_tool_kinds import ToolKindService
from udan.core_tools_loading.api_tools import ToolKind


class OperatorArgs(BaseModel):
    """Pre-extracted operator metadata for applicators.

    The applicator contract's data side: the engine resolves an operator's metadata
    once per application and hands the applicator this, so applicators - the engine's
    own, and the ones other modules contribute for their kinds - read a shape instead
    of reaching into metadata.
    """

    model_config = {"arbitrary_types_allowed": True}

    is_nested: bool
    on_depth: DepthSelector | None
    max_depth: int
    position: tuple[int, ...] | None = None
    per_item_attrs: dict[str, AttributeDescriptor] = {}  # param_name -> AttributeDescriptor


Applicator = Callable[
    [dict[str, Any], Callable, ExecContextAPI, ChainContextAPI, Iterable[Node], int, OperatorArgs],
    Iterable[Node],
]
"""The uniform shape every operator applicator has, whoever contributes it."""


class OperatorsEngineAPI(ToolKindService, ChainStepServiceAPI):
    """API interface for operator application engine.

    This class defines the public API for applying operators to tree structures.
    The operator engine handles expansion and application of operators in queries.

    The engine manages:
    - Resolving operator descriptors to executable operators
    - Applying operators in forest representations
    - Applying operators in node trees recursively
    - Applying a chain segment handed to it by the orchestrator (a chain step)

    It is a kind service in shape only - it declares no kind (KINDS below) and takes
    no chain groups at chain position: every operator kind is instantiated beside the
    plugin package whose service owns it, and the routing hands that service the
    kind's groups. What makes the engine a service anyway is what no kind can own:
    the walk every kind's operators go through, the dispatch the kind services
    register their applicators into (register_applicator), and the chain step
    adapter every kind service delegates its groups to. See docs/architecture.md,
    the OperatorsEngine section, for why it stays.
    """

    KINDS: tuple[ToolKind, ...] = ()
    """The kinds whose chain groups this engine takes: none.

    Every operator kind is instantiated beside the package whose service owns it, so
    the engine owns no kind's chain groups - each service takes its kind's groups and
    delegates here, because the walk is what this engine owns. The declaration stays
    (the routing reads KINDS off every service it holds) and is about chain position,
    not about what this engine can apply: a descriptor of any kind still reaches the
    walk when it is nested inside a run, and is applied through the applicator that
    kind's service registered (register_applicator).
    """

    def register_applicator(self, kind: ToolKind, applicator: Applicator) -> None:
        """Register the applicator of an operator kind whose chain groups another service owns.

        The walk applies operator descriptors wherever they appear - nested inside a
        run as operator children or chain items of an expanded variable, not only at
        the chain positions the routing hands to their kind service. A kind service
        whose descriptors can appear in those positions contributes its applicator
        here, at container build; the engine dispatches by kind and never names the
        contributing ones.

        Args:
            kind: The kind the applicator applies
            applicator: The uniform applicator of that kind's operators
        """
        raise NotImplementedError

    def unregister_applicator(self, kind: ToolKind) -> None:
        """Take a kind's applicator back off the dispatch - the detach to register's attach.

        The inverse of `register_applicator`: takes a kind's applicator back off the
        dispatch, so the engine stops applying that kind's descriptors the way it
        never applied them before the plugin was loaded. The kind service itself
        does not call this - the container build that registered its applicator
        has no teardown.

        Args:
            kind: The kind whose applicator comes off
        """
        raise NotImplementedError

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
            attr_context: Attributes context for nested variable expansion

        Returns:
            Updated args_dict with variables expanded to required types
        """
        raise NotImplementedError

    def apply_operators_with_contexts(
        self, forest: Forest, ctx: ExecContextAPI, attr_context: ChainContextAPI, item_cap: int | None = None
    ) -> tuple[Forest, Any]:
        """Apply operators to a forest with provided contexts.

        Args:
            forest: Forest with operator descriptors to apply
            ctx: Execution context.
            attr_context: Attributes context (must be provided by caller).
            item_cap: Optional bound on how many items the last operator of the
                top-level chain may produce. Pass the default limit here when
                the auto-limit will apply, so lazy sources (db cursors, files)
                stop producing items once the limit is reached.

        Returns:
            Forest with operators applied (actual data)
        """
        raise NotImplementedError
