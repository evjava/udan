"""Udan command-line interface.

This module provides the CLI for udan using argparse. The CLI lives in the
parsing package because it is a query-language entry point: it parses whole
query texts with the package's parser and hands the node to the engine context
(``UdanContextAPI.execute_query``), which runs the steps of the execution - it
cannot run on the context alone, and the context does not parse.
"""

import argparse
import sys
import time
import traceback

from udan.core.api_exceptions import ExceptionWithAdvice
from udan.core.api_udan_context import UdanContextAPI
from udan.core.config import UdanConfig
from udan.core.impl_ioc import create_udan_container
from udan.parsing.api_query_parser import QueryParserAPI


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments.

    Args:
        argv: List of command-line arguments. If None, uses sys.argv[1:].

    Returns:
        Namespace with parsed arguments.
    """
    if argv is None:
        argv = sys.argv[1:]

    # Pre-process: handle --query flag before argparse
    # We need to extract --query=value before argparse splits on spaces
    query_value = None
    filtered_argv = []
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg.startswith("--query="):
            # Extract the value after --query=
            query_value = arg.split("=", 1)[1]
        elif arg == "--query":
            # Next arg is the query value
            if i + 1 < len(argv):
                query_value = argv[i + 1]
                i += 1  # Skip the next arg
        else:
            filtered_argv.append(arg)
        i += 1

    description = "Universal Data Navigator - Query language for hierarchical data exploration"
    parser = argparse.ArgumentParser(prog="udan", description=description)
    parser.add_argument("query", nargs="?", help="Query string to execute (e.g., 'fruits', 'menu, sort name')")
    parser.add_argument("--comment", default="", help="Comment to describe the purpose of this query")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode for verbose")

    args = parser.parse_args(filtered_argv)

    # Use --query value if provided, otherwise use positional query
    if query_value is not None:
        args.query = query_value

    # If still no query, error
    if args.query is None:
        parser.error("the following arguments are required: query")

    return args


def main(query: str, comment: str = "", debug: bool = False) -> str:
    """Execute a udan query and return the result.

    The composition the context's execute_query expects: this CLI parses the
    text with the parsing package's parser and hands the node over; the context
    runs the steps (validate, resolve, apply, limit, render, debug, history).

    Args:
        query: The query string to execute (e.g., "fruits", "menu, sort name")
        comment: Optional comment describing the purpose/goal of this query.
                 This is stored in the history JSONL file for tracking.
        debug: Enable debug mode for verbose output during query execution.
               Use this when troubleshooting query issues or understanding
               how queries are processed.

    Returns:
        The rendered output string from the query execution.

    Raises:
        SystemExit: When the query fails - a failed parse directly, a failed
            resolve through the context's None-forest result. The rendered
            error advice goes to stderr and the exit code is 1, so a scripted
            pipeline tells a failing query from an empty result.

    Examples:
        # Basic query
        python -m udan.parsing.main "fruits"

        # Query with comment for history tracking
        python -m udan.parsing.main "menu" --comment="Planning weekly meals"

        # Debug mode to understand query processing
        python -m udan.parsing.main "fruits, sort name" --debug

        # Combined flags
        python -m udan.parsing.main "web_list https://example.com, :list" --comment="Research" --debug
    """
    container = create_udan_container(UdanConfig())
    ctx = container.get(UdanContextAPI)
    ctx = ctx.load_core()
    parser = container.get(QueryParserAPI)
    exec_ctx = ctx.create_exec_context(debug=debug)
    query_text = str(query)
    started = time.perf_counter()
    try:
        query_node = parser.parse_text_to_tree(query_text, exec_ctx)
    except Exception as ex:
        # A failed parse takes the same contract the context gives the rest of
        # an execution: the advice (or the traceback) as the output, the debug
        # prepended, the failure in the history - then the CLI reports it on
        # stderr and exits non-zero.
        out = ex.advice if isinstance(ex, ExceptionWithAdvice) else traceback.format_exc()
        exec_ctx.debug("#execute_query: FAIL")
        debug_info = ctx.execution_debug_text(exec_ctx, started)
        ctx.log_execution_result(query_text, success=False, error=ex, comment=comment or None)
        print((debug_info + "\n" + out).strip(), end="", file=sys.stderr)
        raise SystemExit(1) from ex
    forest, _, _, out, _debug_info = ctx.execute_query(
        query_node, exec_ctx, query_text=query_text, started=started, comment=comment or None
    )
    if forest is None:
        # A failed query renders its error advice as the output string. For the
        # CLI that is a diagnostic, not a result: it belongs on stderr with a
        # non-zero exit, or every scripted pipeline reports success silently.
        print(out, end="", file=sys.stderr)
        raise SystemExit(1)
    return out


def main_io() -> None:
    """Main I/O function that reads arguments, executes query, and prints results."""
    args = _parse_args()
    result = main(args.query, args.comment, args.debug)
    print(result, end="")


if __name__ == "__main__":
    main_io()
