"""Public API interface for UdanContext.

Defines the public interface that consumers of UdanContext can depend on.
Implementation lives in impl_udan_context.py.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Self

from udan.core.api_exec_context import ExecContextAPI
from udan.core.api_forests import Forest, Node
from udan.core_tools_loading.api_tools import ToolDescriptor
from udan.core_tools_loading.api_tools_registry import ToolsRegistryAPI
from udan.renders.api_renders import RenderDescriptor


class UdanContextAPI:
    """Public API interface for Udan execution context.

    The context runs the steps of a query execution after the parse: it holds
    the resolver (Node -> Forest, QueryProcessorAPI), and execute_query walks
    the resolve half and the engine half together - validate preferences,
    resolve, the item cap, apply, auto-limit, render, debug finalization,
    history logging - with the error contract; prepare_query_state runs
    resolve, apply and render only. It names no parser: the text -> Node
    stage is the query language's own (udan.parsing), and the caller parses
    before handing the node over - the way the CLI (udan.parsing.main) does.
    """

    @property
    def registry(self) -> ToolsRegistryAPI:
        raise NotImplementedError

    def create_exec_context(self, debug: bool = False) -> ExecContextAPI:
        """Create a new execution context for direct API usage."""
        raise NotImplementedError

    def apply_state(
        self,
        forest: Forest,
        requested: Sequence[ToolDescriptor],
        output_specs: Sequence[ToolDescriptor],
        exec_ctx: ExecContextAPI,
    ) -> tuple[Forest, list, str]:
        """Apply the chain, fold the descriptors discovered on the way, apply the values, produce output.

        No item cap, no auto-limit, no debug finalization, no history: errors
        propagate to the caller.
        """
        raise NotImplementedError

    def run_state(  # noqa: PLR0913
        self,
        forest: Forest,
        requested: Sequence[ToolDescriptor],
        output_specs: Sequence[ToolDescriptor],
        exec_ctx: ExecContextAPI,
        *,
        started: float,
        query_text: str,
        item_cap: int | None = None,
        comment: str | None = None,
        prepend_debug: bool = True,
        apply: bool = True,
    ) -> tuple[Forest | None, list, Sequence[ToolDescriptor], str, str]:
        """The engine half of a full execution, with the error contract.

        Applies with the item cap, auto-limits to the same cap, produces the
        output, finalizes the debug output and logs history. Never raises: a
        failure is a None forest with the message in the output string. An
        introspection override renders its own forest instead - one raised by the
        engine inside the application, and one handed in by the caller when the
        resolve half already produced an override forest (type combination).

        Args:
            forest: Resolved forest the chain applies to; with apply=False the
                override forest to produce the output of directly
            requested: Descriptors resolved with the forest
            output_specs: Output descriptors resolved with the forest; the
                override output falls back to the engine's default when empty
            exec_ctx: Execution context (with logger, symbols_env)
            started: The caller's perf_counter, so the `debug-time` line still
                covers the whole query
            query_text: The query the state was resolved from (the history label)
            item_cap: Item cap for chain application, None when uncapped;
                the same cap drives the auto-limit truncation
            comment: Optional comment describing the query purpose (history)
            prepend_debug: When True, prepend debug info to the output string;
                when False, return it separately as the fifth element
            apply: When False, skip chain application and the auto-limit:
                `forest` is an override forest and produces its output as resolved
        """
        raise NotImplementedError

    def execute_query(  # noqa: PLR0913
        self,
        query_node: Node,
        exec_ctx: ExecContextAPI,
        *,
        query_text: str,
        started: float | None = None,
        comment: str | None = None,
        prepend_debug: bool = True,
    ) -> tuple[Forest | None, list, Sequence[ToolDescriptor], str, str]:
        """Execute a parsed query node: the resolve half and the engine half, with the error contract.

        Validates the preferences, resolves the node (the query processor), applies
        with the item cap, auto-limits, renders, finalizes the debug output and logs
        history. Never raises: a failure is a None forest with the message in the
        output string; an introspection override (type combination) renders its own
        forest instead. Parse errors are the caller's: the caller parsed the node
        this method takes.

        Args:
            query_node: The parsed query tree (the parser's product)
            exec_ctx: Execution context (with logger, symbols_env)
            query_text: The query the node was parsed from (the debug line and
                the history label)
            started: The caller's perf_counter captured before the parse, so the
                `debug-time` line still covers the whole query; None captures at entry
            comment: Optional comment describing the purpose/goal of the query (history)
            prepend_debug: When True, prepend debug info to the output string (CLI behavior);
                when False, return it separately as the fifth element (API behavior)

        Returns:
            Tuple of (forest, requested, output_specs, output_string, debug_info)
            If an error occurs, output_string contains the error message
            and forest will be None.
        """
        raise NotImplementedError

    def prepare_query_state(
        self, query_node: Node, exec_ctx: ExecContextAPI
    ) -> tuple[Forest, list, list[RenderDescriptor], str]:
        """Prepare the query state (resolve, apply, render) without limits or finalization.

        Unlike execute_query this applies no item cap and no auto-limit, does no
        debug finalization, and logs no history; errors propagate to the caller
        instead of becoming a None-forest result. For flows that post-process the
        state and own their reporting; the caller parses the node this method takes.

        Args:
            query_node: The parsed query tree (the parser's product)
            exec_ctx: Execution context (with logger, symbols_env)

        Returns:
            Tuple of (forest, attrs, render_tools, output_string)
        """
        raise NotImplementedError

    def execution_debug_text(self, exec_ctx: ExecContextAPI, started: float) -> str:
        """Collect the debug text of a finished execution: the context's log plus the time line."""
        raise NotImplementedError

    def log_execution_result(
        self,
        query_text: str,
        success: bool,
        result: tuple[Forest, list, Sequence[ToolDescriptor], str] | None = None,
        error: Exception | None = None,
        comment: str | None = None,
    ) -> None:
        """Log an execution result to history."""
        raise NotImplementedError

    def load_core(self) -> Self:
        raise NotImplementedError

    def detach(self) -> None:
        """Unwire every SUBSCRIBE declaration the boot wired on the bus.

        The mirror image of load_core's subscription wiring: shutting the
        context down leaves the bus as it found it.
        """
        raise NotImplementedError

    def output_forest(
        self,
        forest: Forest,
        requested: Sequence[ToolDescriptor],
        output_specs: Sequence[ToolDescriptor],
        exec_ctx: ExecContextAPI,
        frontend: str = "",
    ) -> str:
        """Produce the output string for a forest, through the output engine.

        Args:
            forest: The forest to produce the output of
            requested: The descriptors requested with the query
            output_specs: The output descriptors the query resolved
            exec_ctx: Execution context (with logger, symbols_env)
            frontend: Requested output frontend for the output resolution;
                empty leaves the choice to the output engine's own default
        """
        raise NotImplementedError

    def has_variable(self, name: str) -> bool:
        raise NotImplementedError
