"""Public API for query processing.

This module defines the public API interface for resolving query trees:
Node in, forest (with attributes and renders) out.
"""

from __future__ import annotations

from udan.core.api_attributes import AttributeDescriptor
from udan.core.api_exec_context import ExecContextAPI
from udan.core.api_forests import Forest, Node
from udan.renders.api_renders import RenderDescriptor


class QueryMiss(Exception):
    """A lookup that found nothing, raised through the resolution walk.

    The resolver knows only that a name found nothing and what the miss was
    about (the fragment the query typed, the kind to narrow by, the reason for
    the query-time log); what answers it is nobody here's business - whatever
    answers ``QueryProcessorAPI.answer_miss`` decides. It is an
    exception because a miss is discovered deep in the walk, past the point
    where a return value could carry it; the chain interpreter catches it at
    the swap point, the one place that knows the chain built so far. The same
    shape as ``OverrideForestException`` (api_exceptions): an exception that
    carries a payload to the one handler that knows what to do with it.

    Deliberately not an ``ExceptionWithAdvice``: a miss is not yet an error -
    it becomes one only when ``answer_miss`` answers nothing.

    The fields are payloads read by the answerer and the swap point, not
    private state (the same reading as OverrideForestException.forest).
    """

    def __init__(self, pattern: str, tool_type: str, reason: str) -> None:
        self.pattern = pattern
        self.tool_type = tool_type
        self.reason = reason
        super().__init__(reason)


class QueryProcessorAPI:
    """API interface for query processing.

    This class defines the public API for resolving query trees into forests,
    collecting the attribute descriptors and render tools the query carries.

    The query processor handles:
    - Resolving query nodes to forest representations
    - Collecting attribute descriptors from the query
    - Collecting render tools from the query
    - Variable assignment and management
    - The misses: when a lookup finds nothing, ``answer_miss`` is asked for the
      query that continues, before the miss becomes the query error

    The processor carries no question logic of its own: ``answer_miss`` answers
    nothing on this base, and the query tree is resolved as parsed. The meaning
    a package adds is wrapped on by its plugin, which decorates the running
    processor - patching ``resolve_query``'s input (a tree transformer) and
    ``answer_miss`` (the answers) in place - instead of this class carrying
    registration surfaces for it.

    The text pipeline (query text in, executed state out) is not here: the
    parser (udan.parsing) turns the text into the tree this interface resolves,
    and the engine context (UdanContextAPI.execute_query) runs the steps after
    the parse - the caller parses and hands the node over.
    """

    def resolve_query(
        self,
        query_node: Node,
        ctx: ExecContextAPI,
    ) -> tuple[Forest, list[AttributeDescriptor], list[RenderDescriptor]]:
        """Resolve query node to forest, attributes, and renders.

        Args:
            query_node: Query node to process (Node from parser)
            ctx: Execution context for dependency injection and query-time logging

        Returns:
            Tuple of (forest, attribute_descriptors, render_tools)
            Variable assignments store unexpanded forests (with operator descriptors)
            in symbols_env, which will be applied when operators are executed.
        """
        raise NotImplementedError

    def answer_miss(self, miss: QueryMiss) -> Node | None:
        """The query answering a lookup that found nothing, None when nothing answers.

        The resolver answers no miss itself - this base returns None, and a
        miss answered nothing becomes the query error. A decorator wraps its
        answer in by patching this method in place (the question sugar
        continues a miss with the listing narrowed to the miss): the answered
        node replaces the missed chain item and is interpreted like any chain
        item.

        Args:
            miss: The miss to answer (the typed fragment, the kind, the reason)

        Returns:
            The query node to interpret in the item's place, or None to pass
        """
        return None
