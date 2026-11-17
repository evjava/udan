"""Query parsing utilities.

This module contains the query language grammar and parser for converting
query strings into AST node trees.
"""

from lark import Lark, Transformer

from udan.core.api_constants import NODE_ROOT_ITEM, NODE_STRING_PREFIX, NODE_VAR_PREFIX
from udan.core.api_forests import Node

_GRAMMAR = r"""
?start: statement_list

statement_list: statement (";" statement)*

statement: assignment
         | chain

chain: expr ("," expr)*

?expr: atom | application

application: atom (named_arg | atom)+

assignment: ATOM ASSIGN chain

?atom: STRING
     | VAR_REF
     | RENDER
     | CMP_OP
     | BANGED_ID
     | KEYVAL
     | ATOM
     | subexpr


RENDER: /:(?:[a-zA-Z_?][a-zA-Z0-9_\-?]*)?(?![0-9-=])/

CMP_OP: /(!=|==|<=|>=|<|>)/

BANGED_ID: /![a-zA-Z_][a-zA-Z0-9_]*/

KEYVAL: /[a-zA-Z_][a-zA-Z0-9_]*=[^\s,;)]+/

named_arg: NAMED_ARG

subexpr: "(" statement_list ")"

STRING: /"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*'/
VAR_REF: /\$[a-zA-Z_][a-zA-Z0-9_]*/
ASSIGN: ":="
NAMED_ARG: /--[a-zA-Z_][a-zA-Z0-9_-]*([=][^\s,);]+)?/

ATOM: /[^\s(),"'$;=:<>!]+/
%import common.WS
%ignore WS
"""


_parser = Lark(
    _GRAMMAR,
    parser="lalr",
    start="start",
)


class _ToNode(Transformer):
    def ATOM(self, t):
        return Node.create(str(t))

    def BANGED_ID(self, t):
        return Node.create(str(t))

    def STRING(self, t):
        # strip surrounding quotes and mark with NODE_STRING_PREFIX
        # This distinguishes string literals from identifiers
        return Node.create(f"{NODE_STRING_PREFIX}{t[1:-1]}")

    def VAR_REF(self, t):
        # Variable reference: $var_name
        # Convert to NODE_VAR_PREFIX format for variable expansion
        var_name = str(t)[1:]  # Remove the $ prefix
        return Node.create(f"{NODE_VAR_PREFIX}{var_name}")

    def named_arg(self, items):
        # named_arg: NAMED_ARG (--key=value or --flag)
        # items[0] is the raw string like "--comments=False"
        # Keep it as-is, the bind_with_schema_ext function will parse it
        raw_named_arg = str(items[0])
        return Node.create(raw_named_arg)

    def RENDER(self, t):
        # Render spec: :render-name [args...]
        # Keep as-is for parse_render_spec in impl_utils_render_engine.py to parse
        return Node.create(str(t))

    def CMP_OP(self, t):
        # Comparison operator: !=, ==, <=, >=, <, >
        # Keep as-is for interpretation
        return Node.create(str(t))

    def KEYVAL(self, t):
        # Key-value argument: key=value (for positional arguments like skip_rows=1)
        # Keep as-is for interpretation
        return Node.create(str(t))

    def chain(self, items):
        # Comma-separated expressions form a CHAIN node (if more than one)
        # Single items are unwrapped for cleaner AST
        if len(items) == 1:
            return items[0]
        return Node.create("CHAIN", items)

    def subexpr(self, items):
        # Parenthesized expression: items is a statement_list (ROOT node)
        # statement_list already wraps in ROOT, just return it
        return items[0] if len(items) == 1 else Node.create(NODE_ROOT_ITEM, items)

    def atom(self, items):
        # items[0] is the atom content (STRING, VAR_REF, RENDER, CMP_OP, KEYVAL, ATOM, or subexpr)
        return items[0]

    def application(self, items):
        head = items[0]
        args = items[1:]
        return Node.create(head.item, args)

    def assignment(self, items):
        # items[0] is the variable name (ATOM), items[1] is ASSIGN token (ignored), items[2] is the chain
        var_name = items[0].item
        chain_or_expr = items[2]
        return Node.create(f":={var_name}", [chain_or_expr])

    def statement(self, items):
        # A statement is either an assignment or a chain
        return items[0]

    def statement_list(self, items):
        # statement_list contains multiple statements separated by semicolons
        # Flatten all statements into ROOT children
        children: list[Node] = []
        for stmt in items:
            if isinstance(stmt, list):
                children.extend(stmt)
            else:
                children.append(stmt)
        return Node.create(NODE_ROOT_ITEM, children)


def _unwrap_single_root_nodes(node: Node, is_top_level: bool = True) -> Node:
    """Recursively unwrap single-child ROOT nodes (except top-level).

    This cleans up the parsed tree by removing ROOT wrappers that were
    added to mark subqueries, making the output more natural.
    The top-level ROOT node is preserved.

    Args:
        node: Node to clean up
        is_top_level: True if this is the top-level node (should not be unwrapped)

    Returns:
        Cleaned node with single-child ROOT nodes unwrapped (except top-level)
    """
    if not node.children:
        return node

    # Recursively clean children (they are not top-level)
    cleaned_children = [_unwrap_single_root_nodes(child, is_top_level=False) for child in node.children]

    # After cleaning children, check if we have a single ROOT child to unwrap
    # This handles cases like (f x, g y) where subexpr creates ROOT that should be unwrapped
    if len(cleaned_children) == 1:
        child = cleaned_children[0]
        if isinstance(child.item, str) and child.item == NODE_ROOT_ITEM:
            # Unwrap the ROOT child
            return Node(item=node.item, children=child.children)

    # If this is a ROOT node with exactly one child (and it's not a ROOT we already unwrapped),
    # unwrap it. But ONLY if it's not the top-level node
    if not is_top_level and isinstance(node.item, str) and node.item == NODE_ROOT_ITEM and len(cleaned_children) == 1:
        child = cleaned_children[0]
        # Don't unwrap if the child is also a ROOT (that case is handled above)
        if not isinstance(child.item, str) or child.item != NODE_ROOT_ITEM:
            return child

    # Otherwise return node with cleaned children
    return Node(item=node.item, children=cleaned_children)


def parse_tree(text: str, unwrap_single_roots: bool = True) -> Node:
    """Parse text into a node tree.

    Args:
        text: Query string to parse
        unwrap_single_roots: If True (default), unwrap single-child ROOT nodes for cleaner output.
                           If False, keep ROOT wrappers for desugaring.

    Returns:
        Parsed node tree
    """
    # Parse the text into a node tree
    parsed = _ToNode().transform(_parser.parse(text))
    # Optionally unwrap single-child ROOT nodes
    if unwrap_single_roots:
        return _unwrap_single_root_nodes(parsed)
    return parsed
