"""Public API constants for udan query language.

This module contains constants that are part of udan's public API contract.
These constants are used across the framework and may be referenced by users
or tool implementors.
"""

from collections.abc import Set
from typing import Literal

# todo fix: eliminate these constants

# Query Flags
# ===========

# Debug marker for enabling debug mode in queries.
# When this marker is present in a query (e.g., "# q: debug, fruits"),
# udan runs in debug mode with additional logging and diagnostics.
#
# Example usage:
#   "# q: debug, filter name=apple"  # Enable debug mode
#   "# q: fruits"  # Normal mode
DEBUG: str = "debug"

# Time marker for showing query execution time.
# When this marker is present in a query (e.g., "# q: debug-time, fruits"),
# it works like `debug` (full debug log) and additionally enables timestamp
# prefixes ([HH:MM.mmm], the same as the udan_log_time config) and shows the
# elapsed execution time. The elapsed-time line is sticky: once used, later
# queries in the same context (session) keep showing it.
DEBUG_TIME: str = "debug-time"

# Framework Parameters
# ===================

# Parameters that are auto-injected by the framework.
# These are automatically provided by udan's execution framework and
# should NOT be bound from user arguments in tool definitions.
#
# The auto-injected parameters are:
# - "ctx": ExecContext - execution context with logger, symbols, etc.
# - "item": The current item being processed (for single-item tools)
# - "items": List of items being processed (for multi-item tools)
# - "nodes": Parse tree nodes (for tools that need AST access)
#
# Example: When defining a tool, you should NOT list these as parameters:
#   @annotated(meta={"tool_type": "filter"})
#   def my_tool(ctx: ExecContext, item: Node):  # ✅ Correct - ctx and item are auto-injected
#       ...
#
#   @annotated(meta={"tool_type": "filter"})
#   def my_tool(ctx: ExecContext = None):  # ❌ WRONG - don't add default values to framework params
#       ...
FRAMEWORK_PARAMS_ALL: Set[str] = {"ctx", "item", "items", "nodes"}

# Keyword Arguments
# =================

# The single place naming the keyword arguments intercepted by the framework
# instead of being delivered to the tool function, plus the keys the
# engines read back from the descriptor tool_args bag. The query side extracts
# them by name (udan.core.impl_descriptor_factory), descriptors
# carry them in tool_args, and the engines read them back.

# Apply only at (on_depth) or up to (max_depth) the given depth, from --on-depth
# / --max-depth query keywords
ARG_ON_DEPTH: str = "on_depth"
ARG_MAX_DEPTH: str = "max_depth"

# The value of an --on-depth argument: a depth level, or one of the two selector
# words - "all" (every node of the input tree) and "leaf" (nodes without children).
# --max-depth stays a plain integer: it counts recursion levels, it does not select.
type DepthSelector = int | Literal["all", "leaf"]
# Apply only at the given hierarchical position ("1.2" = children[1].children[2]),
# from the --position query keyword
ARG_POSITION: str = "position"
# Reversed order for sorters, from the --desc query keyword or the -field sugar
ARG_DESC: str = "desc"

# Node Item Markers
# =================

# Item values of the special parse-tree nodes. The query parser produces them
# (udan.parsing), the query processor and the engines read them:
# a node whose item is NODE_ROOT_ITEM is a statement-list root, and the prefix
# markers mark a string literal, a variable reference and the target of a
# `:=name` assignment.
NODE_ASSIGN_PREFIX: str = "__ASSIGN__"
NODE_VAR_PREFIX: str = "__VAR__"
NODE_STRING_PREFIX: str = "__STRING__"
NODE_ROOT_ITEM: str = "ROOT"

# Query Tokens
# ============

# Token that disables auto-limit in queries. The query processor consumes it as a
# render-spec-like marker and the context reads it back for the auto-limit decision,
# the same split as the node markers above.
# TODO: when templates are introduced, replace this with `limit --no` syntax.
NOLIMIT_TOKEN: str = ":nolimit"

# The question atom. The parser's completions emit it (an empty query, a trailing
# comma, an EOF retry, the postfix move), the processor's miss sites answer with it
# and annotate it by it, and the listing tool registers it as its alias - so a
# question in a query is an ordinary application of an ordinary tool, and the one
# name the query language gives the question.
QUESTION_OPERATOR: str = "?"

# Sentinel Values
# ==============

# Infinity value for size/weight calculations.
# Used as a sentinel value to represent "unbounded" or "infinite" size/weight.
#
# This is used throughout the framework for:
# - Query complexity estimation (udan.core.impl_query_processor)
# - Cost estimation in the engines (udan.operator/impl_operator_engine)
# - Parameter validation (udan.core.impl_descriptor_factory)
# - Variable resolution complexity (udan.core.impl_variable_handler)
# - Parse tree complexity (udan.parsing.impl_utils_parsing)

# Chain Behavior Meta Keys
# ========================

# Metadata key that short-circuits a chain: a tool whose meta declares it renders
# its own forest instead of the chain's, so nothing about the chain's own output
# can be assumed (`range 5, ?` shows the listing, not the range). The chain walk
# (udan.core.utils_chain) reads it where the query is interpreted.
#
# Example:
#   @annotated(meta={"tool_type": "replacer", "is_nested": True, "overrides_output": True})
OVERRIDES_OUTPUT: str = "overrides_output"

# Metadata key that marks a chain-blind tool: what it lists or suggests depends on
# the item types built so far at its chain position, which only the resolver
# knows. The resolver hands them over as the `item_types` argument of the
# resolved descriptor when the walk interprets the chain.
#
# Example:
#   @annotated(meta={"tool_type": "replacer", "wants_item_types": True})
WANTS_ITEM_TYPES: str = "wants_item_types"

# Variable Types
# ==============

# Type system constants for variable types: values of variable type annotations
# and of TypesRegistryAPI.infer_variable_type_from_forest().
TYPE_QUERY: str = "query"
TYPE_LIST: str = "list"
TYPE_STR: str = "str"
TYPE_INT: str = "int"
TYPE_FOREST: str = "forest"
TYPE_ANY: str = "any"
