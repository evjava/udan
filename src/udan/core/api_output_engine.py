"""Public API for the output engine.

The last step of every query is producing the output string for the resolved,
applied forest. Which tools produce it, and how, is a plugin package's
domain (udan.renders, part of udan); the core names the seam - the service that turns a
forest into text - and hands it the descriptors the query resolved, blind of what
they are. A host that leaves the package out gets the core's own engine, which
answers with the advice that says what is missing.
"""

from __future__ import annotations

from collections.abc import Sequence

from udan.core.api_exec_context import ExecContextAPI
from udan.core.api_forests import Forest
from udan.core_tools_loading.api_tools import ToolDescriptor


class OutputEngineAPI:
    """API interface for producing the output of a query.

    This class defines the public API for converting an applied forest to a
    string representation through the output-producing tools the query
    resolved.
    """

    def output_forest(
        self,
        forest: Forest,
        requested: Sequence[ToolDescriptor],
        output_specs: Sequence[ToolDescriptor],
        ctx: ExecContextAPI,
        frontend: str = "",
    ) -> str:
        """Produce the output string for an applied forest.

        Args:
            forest: The forest to produce the output of
            requested: The descriptors requested with the query (their values may
                be displayed alongside the items)
            output_specs: The output-producing descriptors the query resolved
            ctx: Execution context for dependency injection and query-time logging
            frontend: Requested output frontend, selecting the matching variant
                of a name that has several; empty leaves the choice to the
                engine's own default

        Returns:
            String representation of the forest
        """
        raise NotImplementedError

    def default_output_specs(self) -> list[ToolDescriptor]:
        """The descriptors producing the output when the query named none.

        Returns:
            The default output descriptors (possibly empty)
        """
        raise NotImplementedError

    def get_ioc_debug_log(self, show_time: bool = False) -> str:
        """Get debug log from the IOC-injected logger."""
        raise NotImplementedError
