"""The question's misses: what a lookup that found nothing continues with.

The resolver raises a ``QueryMiss`` when a chain item finds nothing - an
ambiguous name, an unknown render, a missing ``at_d`` - and the chain
interpreter asks ``answer_miss`` what continues instead. This module's
answerer is what the plugin's decorator patches in as that answer: the listing
narrowed by the fragment the query typed and the kind the miss was about. The
miss policy - which misses are answerable at all, and with what narrowing -
stays with the resolver's miss sites; only the answering lives here.
"""

from udan.core.api_constants import QUESTION_OPERATOR
from udan.core.api_forests import Node
from udan.core.api_query_processor import QueryMiss


class QuestionMissAnswerer:
    """Answers every miss with the question narrowed by the miss's fragment and kind."""

    def answer_miss(self, miss: QueryMiss) -> Node | None:
        """The question answering the miss: `? --tool_type=<kind> --pattern=<fragment>`.

        Every miss this resolver raises is a "which one did you mean?" - the
        listing of what exists, narrowed to the typed fragment and the kind, is
        the answer. An unfiltered field stays out: an empty pattern or kind is
        simply not written down.

        Args:
            miss: The miss to answer (the typed fragment, the kind, the reason)

        Returns:
            The question node to interpret in the item's place, never None
        """
        args = []
        if miss.tool_type:
            args.append(Node.leaf(f"--tool_type={miss.tool_type}"))
        if miss.pattern:
            args.append(Node.leaf(f"--pattern={miss.pattern}"))
        return Node.create(QUESTION_OPERATOR, args)
