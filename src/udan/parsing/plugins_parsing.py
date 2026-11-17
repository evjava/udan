"""Query parsing plugin: the container contribution and the plugin declarations.

The package has no tools of its own - its contribution is the query parser
(query text in, query tree out). The steps after the parse are not the
package's: the resolver is core (it binds parsed arguments into descriptors -
resolution, not parsing) and the engine context runs the execution
(``UdanContextAPI.execute_query``) - a caller parses and hands the node over,
the way the CLI (``main``) does.
"""

from udan.decompof import Plugin, provide
from udan.parsing.api_query_parser import QueryParserAPI
from udan.parsing.impl_query_parser import QueryParser


class ParsingPlugin(Plugin):
    """Container contribution of the package: the query parser."""

    @provide
    def query_parser(self) -> QueryParserAPI:
        """Create the query parser."""
        return QueryParser()


DOMAIN = "query_parsing"
PLUGIN = ParsingPlugin
