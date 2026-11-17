"""Public API for query parsing.

This module defines the public API interface for parsing query strings
into tree structures, plus the query text conventions both sides of the
parser share: the `# q:` prefix and the `--key=value` named argument token.
"""

from __future__ import annotations

from udan.core.api_exec_context import ExecContextAPI
from udan.core.api_forests import Node


class QueryParserExtraAPI:
    """A parser extra: a query-text transformer applied before the parser's main work.

    Registered on the parser with ``QueryParserAPI.register_parser_extra`` and removed
    with ``unregister_parser_extra``; it is just a transformer - one method, one job.
    Every registered extra runs once per parse, in registration order, each seeing the
    previous one's output, before udan's own heuristics and before the parse: the text
    an extra returns is the text the parser parses.
    """

    def transform_query_text(self, query_text: str) -> str:
        """Rewrite the query text before the parser parses it.

        Args:
            query_text: The query text, prefix-stripped and comment-stripped

        Returns:
            The rewritten query text; it must parse (raise ``ExceptionWithAdvice``
            for a user-facing error), and a raw ``#`` must not be emitted - udan
            strips comments before the extras run, so the output is not stripped
        """
        raise NotImplementedError


class QueryParserAPI:
    """API interface for query parsing.

    This class defines the public API for parsing query strings into tree structures.
    The parser handles query transformations, incomplete queries, and operator expansion,
    plus the parser extras: query-text transformers registered on it, applied before
    its main work.
    """

    def parse_text_to_tree(self, query_text: str, ctx: ExecContextAPI) -> Node:
        """Parse query text into a tree, handling incomplete queries.

        Applies query transformations (remove prefix, expand incomplete operators,
        handle trailing comma) and then parses. If the query is incomplete
        (UnexpectedEOF error), appends a default operator and retries parsing.

        Args:
            query_text: The query string to parse
            ctx: Execution context for query-time logging

        Returns:
            Parsed query tree (Node object)
        """
        raise NotImplementedError

    def register_parser_extra(self, extra: QueryParserExtraAPI) -> None:
        """Register a parser extra: applied before the parser's main work.

        Args:
            extra: The extra to register; it runs after the registered ones
        """
        raise NotImplementedError

    def unregister_parser_extra(self, extra: QueryParserExtraAPI) -> None:
        """Unregister a parser extra registered before.

        Args:
            extra: The extra to remove

        Raises:
            ValueError: If the extra is not registered
        """
        raise NotImplementedError


def parse_named_argument(item: str, known_keys: set[str] | None = None) -> tuple[str, str] | None:
    """Parse a named argument string like --key=value, --flag, or --noflag.

    Args:
        item: Argument string starting with --
        known_keys: Parameter names known from the signature, used to decide if a
            leading "no" is a negation. Without it any name starting with "no" is
            treated as a negation (e.g. --normalize becomes rmalize=false).

    Returns:
        Tuple of (key, value) or None if not a valid named argument

    Raises:
        ValueError: If argument format is invalid
    """
    # Remove leading --
    key_value = item[2:]

    # Handle boolean flags: --noarg -> arg=false, --arg -> arg=true
    if "=" not in key_value:
        # Check for --no- and --noarg format BEFORE replacing dashes
        if key_value.startswith("no-"):
            prefix_len = 3  # Remove 'no-' prefix
        elif key_value.startswith("no"):
            prefix_len = 2  # Remove 'no' prefix
        else:
            prefix_len = 0

        if prefix_len:
            stripped = key_value[prefix_len:]
            if not stripped:
                # Bare --no / --no- has no name left
                return None
            direct_key = key_value.replace("-", "_")
            negated_key = stripped.replace("-", "_")
            # A leading "no" is a negation only when the stripped name is a known parameter
            # and the literal name is not: --normalize stays normalize=true even when a
            # rmalize parameter exists, and --noa stays noa=true when both a and noa exist.
            if known_keys is None or (negated_key in known_keys and direct_key not in known_keys):
                return (negated_key, "false")
            # Not a negation: keep the flag as typed
            return (direct_key, "true")

        # Convert dashes to underscores in argument names only (no value to preserve)
        return (key_value.replace("-", "_"), "true")
    elif "=" in key_value:
        # Split on first = to separate key and value
        key, value = key_value.split("=", 1)
        # Convert dashes to underscores in argument name only, not in value
        key = key.replace("-", "_")
        # Strip matching quotes from value (both single and double quotes)
        if (value.startswith("'") and value.endswith("'")) or (value.startswith('"') and value.endswith('"')):
            value = value[1:-1]
        return (key, value)
    else:
        raise ValueError(f"Named argument must be in --key=value, --flag, or --noflag format, got: {item}")


def remove_prefix_if_needed(text, prefix):
    """Drop the prefix when the text carries it, return the text unchanged when it does not."""
    if text.startswith(prefix):
        return text[len(prefix) :]
    if len(text) == len(prefix) and text == prefix:
        return ""
    return text
