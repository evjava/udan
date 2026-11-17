"""The question sugar plugin: the container contribution, the decorator, and the attach verbs.

The package's contribution is the question's meaning in both places the
resolver meets it: the sugar (the tree transformer that rewrites
question-shaped nodes into the applications that answer them) and the miss
answerer (the query that continues when a lookup finds nothing). Both are
decorations of the query processor that is already running - a declaration
cannot say them - so they ride the PLUGIN's attach/detach verbs
(``decompof.plugin.Plugin``): attach decorates the resolver (the sugar onto
``resolve_query``'s input, the answerer onto ``answer_miss``), detach
undecorates it. The verbs' annotated parameters are dependencies validated at
build, so a boot without the query package fails here, loudly, instead of
silently leaving the questions meaningless.
"""

from collections.abc import Callable
from typing import Any

from udan.core.api_attributes import AttributeDescriptor
from udan.core.api_exec_context import ExecContextAPI
from udan.core.api_forests import Forest, Node
from udan.core.api_query_processor import QueryProcessorAPI
from udan.core_tools_loading.api_tools_registry import ToolsRegistryAPI
from udan.decompof import Plugin, provide
from udan.plugins_help_sugar.impl_miss_answers import QuestionMissAnswerer
from udan.plugins_help_sugar.impl_query_sugar import QuerySugar
from udan.renders.api_renders import RenderDescriptor


def _decorate_query_processor(
    query_processor: QueryProcessorAPI, sugar: QuerySugar, miss_answerer: QuestionMissAnswerer
) -> QueryProcessorAPI:
    """The resolver decorated with the question's meaning: a QueryProcessorAPI in, one out.

    Two methods are decorated: the input of ``resolve_query`` runs through the
    sugar first (every question-shaped node becomes the application that
    answers it, before the resolver's main work), and ``answer_miss`` answers
    a lookup that found nothing with the question narrowed to what the query
    typed. The decorated resolver is the resolver itself - the same object,
    the same interface, the same reference its holders keep - because both
    decorated points are consulted on the resolver: the chain interpreter asks
    the processor's own ``answer_miss`` at the swap point, and the resolver
    re-enters its own ``resolve_query`` for a variable assignment's
    right-hand side. A decorated twin would never be asked either question.

    Args:
        query_processor: The resolver to decorate
        sugar: The tree transformer applied to resolve_query's input
        miss_answerer: The answerer decorated in as answer_miss

    Returns:
        The decorated resolver, still a QueryProcessorAPI
    """
    resolve_query = query_processor.resolve_query

    def resolve_query_with_sugar(
        query_node: Node, ctx: ExecContextAPI
    ) -> tuple[Forest, list[AttributeDescriptor], list[RenderDescriptor]]:
        """Resolve the tree the sugar rewrote; the resolver's own signature."""
        return resolve_query(sugar.transform_query_tree(query_node), ctx)

    query_processor.resolve_query = resolve_query_with_sugar
    query_processor.answer_miss = miss_answerer.answer_miss
    return query_processor


def _unwrap_query_processor(
    query_processor: QueryProcessorAPI, resolve_query: Callable[..., Any], answer_miss: Callable[..., Any]
) -> QueryProcessorAPI:
    """The resolver with the question's meaning off: the two methods back, the same resolver.

    Args:
        query_processor: The decorated resolver to undecorate
        resolve_query: The resolve_query the decoration replaced
        answer_miss: The answer_miss the decoration replaced

    Returns:
        The undecorated resolver, still a QueryProcessorAPI
    """
    query_processor.resolve_query = resolve_query
    query_processor.answer_miss = answer_miss
    return query_processor


class HelpSugarPlugin(Plugin):
    """Container contribution: the question's meaning, decorated onto the processor."""

    @provide
    def query_sugar(self, registry: ToolsRegistryAPI) -> QuerySugar:
        """Create the tree transformer that gives the question atom its meaning."""
        return QuerySugar(registry)

    miss_answerer = provide(source=QuestionMissAnswerer, provides=QuestionMissAnswerer)

    def __init__(self) -> None:
        """Remember what the decoration replaced, so detach can put it back."""
        self._undecorated: tuple[Callable[..., Any], Callable[..., Any]] | None = None
        self._decorated: QueryProcessorAPI | None = None

    def attach(
        self, query_processor: QueryProcessorAPI, sugar: QuerySugar, miss_answerer: QuestionMissAnswerer
    ) -> None:
        """Wrap the running resolver: decorating it is registering the question's meaning."""
        self._undecorated = (query_processor.resolve_query, query_processor.answer_miss)
        self._decorated = _decorate_query_processor(query_processor, sugar, miss_answerer)

    def detach(self) -> None:
        """Unwrap the resolver: its own two methods back, the question's meaning off."""
        if self._decorated is None or self._undecorated is None:
            return
        resolve_query, answer_miss = self._undecorated
        _unwrap_query_processor(self._decorated, resolve_query, answer_miss)
        self._decorated = None
        self._undecorated = None


DOMAIN = "help_sugar"
PLUGIN = HelpSugarPlugin
