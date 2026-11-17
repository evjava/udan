"""udan.parsing: the query language.

Owns the query language's text half: the Lark grammar with its parse tree
(``impl_utils_parsing``) and the preprocessing that turns the query text (the
``# q:`` prefix, comments, postfix ``?``, the incomplete-query completions)
into that tree (``impl_query_parser``, contract in ``api_query_parser`` beside
its ``QueryParserExtraAPI`` transformer seam). The steps after the parse are
not the package's: the resolver is core (``udan.core.impl_query_processor``) and
the engine context runs the execution (``UdanContextAPI.execute_query``) - a
caller parses and hands the node over, the way the CLI (``main``) does.

The package is part of udan, so Plugins discovers it on every boot the way it
discovers udan.operator*: the container resolves ``QueryParserAPI`` from it on
every normal boot, so udan without the query language is not a build that
starts.
"""
