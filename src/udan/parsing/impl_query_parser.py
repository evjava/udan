"""Query parsing module.

Owns question *syntax*, not question meaning: the atom, its postfix move and the
incomplete-query completions emit the inert `?` atom and name no tool. What the
atom means is decided later, by the registered processor extras, on the tree
this module produces.
"""

import re

from lark.exceptions import LarkError, UnexpectedEOF

from udan.core.api_constants import QUESTION_OPERATOR
from udan.core.api_exceptions import ExceptionWithAdvice
from udan.core.api_exec_context import ExecContextAPI
from udan.core.api_forests import Node
from udan.parsing.api_query_parser import (
    QueryParserAPI,
    QueryParserExtraAPI,
    remove_prefix_if_needed,
)
from udan.parsing.impl_utils_parsing import parse_tree

# Matches either a quoted string literal (kept as-is), a render spec with a
# trailing question mark, a word with a trailing question mark, or a question
# mark glued to the following word. The lookbehind excludes matches that are
# part of other syntax: variable refs ($var?), named args (--name?, --k=v?),
# keyvals (k=v?) and mid-word question marks (foo?bar).
_POSTFIX_QUESTION_PATTERN = (
    r'"(?:[^"\\]|\\.)*"'
    r"|'(?:[^'\\]|\\.)*'"
    r"|(?<![\w.:!=$-])(?P<render_spec>:[a-zA-Z_][a-zA-Z0-9_\-]*)\?(?=[\s,;)\]]|$)"
    r"|(?<![\w.:!=$-])(?P<word>[a-zA-Z_][a-zA-Z0-9_.\-]*)\?(?=[\s,;)\]]|$)"
    r"|(?<![\w.:!=$-])(?P<glued_qmark>\?(?=[a-zA-Z_]))"
)
_POSTFIX_QUESTION_RE = re.compile(_POSTFIX_QUESTION_PATTERN)

# Matches either a quoted string literal (kept as-is) or a `#` comment running
# to the end of the line.
_COMMENT_PATTERN = (
    r'"(?:[^"\\]|\\.)*"'
    r"|'(?:[^'\\]|\\.)*'"
    r"|(?P<comment>#[^\n]*)"
)
_COMMENT_RE = re.compile(_COMMENT_PATTERN)


def _replace_comment(match: re.Match[str]) -> str:
    """Drop a matched comment, keeping string literals as-is."""
    return "" if match.group("comment") is not None else match.group(0)


def _strip_comments(query_text: str) -> str:
    """Remove `#` comments from the query, keeping them inside string literals.

    Lets users annotate a query like in Python: `fruits # the demo data` parses
    as `fruits`. The comment runs to the end of the line, so multi-line queries
    keep the lines after it. A `#` inside a quoted string literal
    (`grep "#tag"`) is data, not a comment.

    Args:
        query_text: The query string to strip

    Returns:
        Query string without comments
    """
    return _COMMENT_RE.sub(_replace_comment, query_text)


def _starts_expression(text: str, pos: int) -> bool:
    """Does the token at `pos` start an expression a tool heads, or is it an argument of one?

    The grammar opens an expression at the query start and after `,`, `(`, `;` and
    the `:=` assignment; an atom anywhere else is an argument of the application
    the previous atom heads. A `)` closes a subexpression, whose arguments are
    interpreted like chain items rather than bound to a tool, so it counts
    as an opening position too.

    Args:
        text: The query text the token belongs to
        pos: Start offset of the token in the text

    Returns:
        True when the token heads an expression
    """
    i = pos - 1
    while i >= 0 and text[i].isspace():
        i -= 1
    if i < 0:
        return True
    return text[i] in ",(;)" or (i >= 1 and text[i - 1 : i + 1] == ":=")


def _replace_postfix_question(match: re.Match[str]) -> str:
    """Replace a `word?`, `:name?` or glued `?word` match with its prefix form, keeping string literals as-is.

    A `word?` heading an expression moves its question mark (`extend?` -> `? extend`).
    A `word?` in argument position keeps it glued: there the question is about the
    word, not about the tool the word is an argument of
    (`extend_by_inserter ls_files?`), and moving it would turn it into the `spec ?`
    tool-docs form - the question sugar answers that pair.
    """
    word = match.group("word")
    if word is not None:
        if not _starts_expression(match.string, match.start()):
            return match.group(0)
        return f"? {word}"
    render_spec = match.group("render_spec")
    if render_spec is not None:
        return f":?{render_spec[1:]}"
    if match.group("glued_qmark") is not None:
        return "? "
    return match.group(0)


def _move_postfix_questions(query_text: str) -> str:
    """Rewrite question marks into the prefix question form `? word`.

    Lets users search tools by suffixing a word with a question mark or
    by gluing the question mark to its front, e.g. `range 5, extend?` and
    `range 5, ?extend` are both interpreted as `range 5, ? extend`. A render
    spec moves its question mark the same way: `:json?` becomes `:?json`, the
    render-question form.
    String literals and tokens belonging to other syntax (variables `$var?`,
    keyvals `k=v?`, named args `--name?`, embedded `foo?bar`) are left unchanged.

    Args:
        query_text: The query string to rewrite

    Returns:
        Query string with question marks moved to prefix position
    """
    return _POSTFIX_QUESTION_RE.sub(_replace_postfix_question, query_text)


class QueryParser(QueryParserAPI):
    """Query parser with preprocessing and parsing capabilities."""

    def __init__(self) -> None:
        """Initialize query parser."""
        # The registered parser extras: query-text transformers applied before the
        # parser's main work (see register_parser_extra).
        self._parser_extras: list[QueryParserExtraAPI] = []

    def register_parser_extra(self, extra: QueryParserExtraAPI) -> None:
        """Register a parser extra: applied before the parser's main work.

        Args:
            extra: The extra to register; it runs after the registered ones
        """
        self._parser_extras.append(extra)

    def unregister_parser_extra(self, extra: QueryParserExtraAPI) -> None:
        """Unregister a parser extra registered before.

        Args:
            extra: The extra to remove

        Raises:
            ValueError: If the extra is not registered
        """
        self._parser_extras.remove(extra)

    def parse_text_to_tree(self, query_text: str, ctx: ExecContextAPI) -> Node:
        """Parse query text into a tree, handling incomplete queries.

        Applies the text preprocessing (remove prefix, strip comments, apply the
        registered parser extras, move postfix question marks, complete an
        incomplete query with the question atom) and then parses. The tree is
        returned with the question syntax intact: what the question atom means
        is decided later, by the registered processor extras.

        Args:
            query_text: The query string to parse
            ctx: Execution context for query-time logging

        Returns:
            Parsed query tree
        """
        # Remove prefix if present
        query_text = remove_prefix_if_needed(query_text, "# q:")

        # `#` comments run to the end of the line and never reach the parser;
        # a query that is only a comment falls back to the question atom.
        query_text = _strip_comments(query_text).strip()

        # Empty query → question atom
        if not query_text:
            query_text = QUESTION_OPERATOR
        else:
            # The registered parser extras rewrite before the parser's main work:
            # the text they return is the text the heuristics and the parse read.
            for extra in self._parser_extras:
                query_text = extra.transform_query_text(query_text)

            # Postfix question mark → prefix question
            # e.g., "range 5, extend?" → "range 5, ? extend"
            query_text = _move_postfix_questions(query_text)

            # Trailing comma → the question atom
            # e.g., "fruits," → "fruits,?"
            if query_text.endswith(","):
                query_text += QUESTION_OPERATOR

        # Parse with incomplete query handling
        try:
            query_tree = parse_tree(query_text, unwrap_single_roots=False)
        except UnexpectedEOF:
            query_text += QUESTION_OPERATOR
            query_tree = parse_tree(query_text, unwrap_single_roots=False)
        except LarkError as ex:
            # A parse failure is a query problem, not a Python one: without debug it
            # becomes the advice - lark's own detail (position, the excerpt, what was
            # expected) without the traceback - and with debug it propagates as is.
            if ctx.is_debug:
                raise
            raise ExceptionWithAdvice(f"Query parse error: {ex}") from ex
        ctx.debug(f"{query_tree=}")
        return query_tree
