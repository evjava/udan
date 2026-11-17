"""The output engine of a container with no output-producing service.

Producing output is the renders domain (udan.renders owns the render kind and the
renders, and provides the engine on every normal boot). A container built without
that provider - a bare IOC() in a test - still runs queries: the chain applies,
values are computed, but nothing turns the forest into text, so the output step
answers with the advice that says what is missing.
"""

from collections.abc import Sequence

from udan.core.api_exceptions import ExceptionWithAdvice
from udan.core.api_exec_context import ExecContextAPI
from udan.core.api_forests import Forest
from udan.core.api_logger import LoggerAPI
from udan.core.api_output_engine import OutputEngineAPI
from udan.core_tools_loading.api_tools import ToolDescriptor

_NO_OUTPUT_ADVICE = (
    "Output is not enabled: this container was built without the output engine "
    "the renders domain provides (udan.renders, part of udan, provides it on every "
    "normal boot), so the query has no output. Build the container through "
    "create_udan_container() to run queries that produce output."
)


class NoOutputEngine(OutputEngineAPI):
    """No output package enabled: producing fails with advice, the IOC log still reads."""

    def __init__(self, logger: LoggerAPI) -> None:
        """Initialize over the app-scoped logger.

        Args:
            logger: The shared app logger, whose startup log the debug output shows
        """
        self._logger = logger

    def output_forest(
        self,
        forest: Forest,
        requested: Sequence[ToolDescriptor],
        output_specs: Sequence[ToolDescriptor],
        ctx: ExecContextAPI,
        frontend: str = "",
    ) -> str:
        """Refuse: producing output is the renders package's work.

        Raises:
            ExceptionWithAdvice: Always, with what is missing
        """
        raise ExceptionWithAdvice(_NO_OUTPUT_ADVICE)

    def default_output_specs(self) -> list[ToolDescriptor]:
        """Nothing to default to: no output package is enabled."""
        return []

    def get_ioc_debug_log(self, show_time: bool = False) -> str:
        """Get debug log from the IOC-injected logger."""
        return self._logger.get_log(show_time=show_time)
