"""Tests for the chain concept: comma groups chains, semicolon separates them."""

import pytest

from tests.conftest import make_qp
from tests.test_helpers import parse_and_interpret
from udan.attributes import plugins_operators_attribute
from udan.core.api_constants import NODE_ROOT_ITEM, NODE_STRING_PREFIX
from udan.core.api_exceptions import ExceptionWithAdvice
from udan.core.api_query_processor import QueryProcessorAPI
from udan.parsing.impl_utils_parsing import parse_tree
from udan.plugins_tools_demo import plugins_demo, plugins_fruits
from udan.plugins_tools_examples import plugins_builtins
from udan.renders import plugins_renders


def test_chain_groups_comma_items():
    """Comma-separated items are grouped into a CHAIN node."""
    tree = parse_tree("a, b, c")
    assert tree.item == NODE_ROOT_ITEM
    assert len(tree.children) == 1
    assert tree.children[0].item == "CHAIN"
    assert [ch.item for ch in tree.children[0].children] == ["a", "b", "c"]


def test_single_item_no_chain_wrapper():
    """A single item without comma does not get a CHAIN wrapper."""
    tree = parse_tree("fruits")
    assert tree.item == NODE_ROOT_ITEM
    assert len(tree.children) == 1
    assert tree.children[0].item == "fruits"


def test_semicolon_no_chain_wrapper():
    """Semicolon-separated single items don't get CHAIN wrappers."""
    tree = parse_tree("a; b")
    assert tree.item == NODE_ROOT_ITEM
    assert len(tree.children) == 2
    assert tree.children[0].item == "a"
    assert tree.children[1].item == "b"


def test_mixed_comma_and_semicolon():
    """Comma groups into chain, semicolon separates chains."""
    tree = parse_tree("fruits, grep berry, :list; range 3, :list")
    assert tree.item == NODE_ROOT_ITEM
    assert len(tree.children) == 2
    # First chain: fruits, grep berry, :list
    chain1 = tree.children[0]
    assert chain1.item == "CHAIN"
    assert len(chain1.children) == 3
    # Second chain: range 3, :list
    chain2 = tree.children[1]
    assert chain2.item == "CHAIN"
    assert len(chain2.children) == 2


def test_chain_with_function_application():
    """Function application within a chain is preserved."""
    tree = parse_tree("fruits, grep berry, :list")
    chain = tree.children[0]
    assert chain.item == "CHAIN"
    # grep berry should be an application node
    grep_node = chain.children[1]
    assert grep_node.item == "grep"
    assert grep_node.children[0].item == "berry"


def test_chain_with_string_literals():
    """String literals within a chain are grouped."""
    tree = parse_tree('"hello", "world"')
    chain = tree.children[0]
    assert chain.item == "CHAIN"
    assert len(chain.children) == 2
    assert chain.children[0].item == f"{NODE_STRING_PREFIX}hello"
    assert chain.children[1].item == f"{NODE_STRING_PREFIX}world"


def test_semicolon_separates_string_literals():
    """Semicolon-separated string literals are separate ROOT children."""
    tree = parse_tree('"abc"; "xyz"')
    assert tree.item == NODE_ROOT_ITEM
    assert len(tree.children) == 2
    assert tree.children[0].item == f"{NODE_STRING_PREFIX}abc"
    assert tree.children[1].item == f"{NODE_STRING_PREFIX}xyz"


def test_parenthesized_subexpr_within_chain():
    """Parenthesized expression within a chain is part of the chain."""
    tree = parse_tree("f (a, b), c")
    chain = tree.children[0]
    assert chain.item == "CHAIN"
    # f (a, b) is an application (parens become its arguments), c is separate in the chain
    assert len(chain.children) == 2


def test_assignment_is_not_a_chain():
    """Assignment statements (:=) are not wrapped in CHAIN."""
    tree = parse_tree("a := x; b")
    assert tree.item == NODE_ROOT_ITEM
    # Assignment is a direct child of ROOT, not a CHAIN
    assert tree.children[0].item.startswith(":=")
    # b is a single item, no CHAIN wrapper
    assert tree.children[1].item == "b"


def test_assignment_with_parenthesized_chain():
    """Assignment with parenthesized comma-list preserves chain inside."""
    tree = parse_tree('a := ("file.txt", extend_file_lines, sgrep depth=1)')
    assign = tree.children[0]
    assert assign.item.startswith(":=")
    # The RHS is a CHAIN node (parenthesized comma-list becomes statement_list -> chain)
    assert len(assign.children) == 1
    rhs = assign.children[0]
    assert rhs.item == "CHAIN"
    assert len(rhs.children) == 3
    assert rhs.children[0].item == f"{NODE_STRING_PREFIX}file.txt"
    assert rhs.children[1].item == "extend_file_lines"
    assert rhs.children[2].item == "sgrep"


# ========================================================================
# Validation tests: invalid chains should error
# ========================================================================


def test_two_string_literals_comma_is_error(make_ctx):
    """Two string literals separated by comma is invalid."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_renders)
    with pytest.raises(ExceptionWithAdvice, match="multiple data sources"):
        parse_and_interpret(ctx, '"abc", "xyz"')


def test_two_inserters_comma_is_error(make_ctx):
    """Two inserters separated by comma is invalid."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_renders)
    with pytest.raises(ExceptionWithAdvice, match="multiple data sources"):
        parse_and_interpret(ctx, "fruits, range 3")


def test_two_ranges_comma_is_error(make_ctx):
    """Two range inserters separated by comma is invalid."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_renders)
    with pytest.raises(ExceptionWithAdvice, match="multiple data sources"):
        parse_and_interpret(ctx, "range 2, range 3")


def test_literal_then_inserter_comma_is_error(make_ctx):
    """A literal followed by an inserter via comma is invalid."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_renders)
    with pytest.raises(ExceptionWithAdvice, match="multiple data sources"):
        parse_and_interpret(ctx, '"hello", range 3')


def test_inserter_then_literal_comma_is_error(make_ctx):
    """An inserter followed by a literal via comma is invalid."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_renders)
    with pytest.raises(ExceptionWithAdvice, match="multiple data sources"):
        parse_and_interpret(ctx, 'range 3, "hello"')


# ========================================================================
# Full execution tests: valid behavior with semicolons
# ========================================================================


def test_chain_semicolon_two_inserters(make_ctx):
    """Semicolon separates two independent inserter chains."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_renders)
    qp = make_qp(ctx)
    _, _, _, out = qp.execute_query("range 2; range 3, :list")
    assert out == "[0, 1, 0, 1, 2]"


def test_chain_semicolon_two_literals(make_ctx):
    """Semicolon separates two independent literal chains."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_renders)
    qp = make_qp(ctx)
    _, _, _, out = qp.execute_query('"abc"; "xyz", :list')
    assert out == "[abc, xyz]"


def test_chain_semicolon_literal_after_inserter(make_ctx):
    """A literal statement written after an inserter statement comes after its items."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_renders)
    qp = make_qp(ctx)
    _, _, _, out = qp.execute_query("range 3; 7, :list")
    assert out == "[0, 1, 2, 7]"


def test_chain_semicolon_string_after_inserter(make_ctx):
    """A string statement written after an inserter statement comes after its items."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_renders)
    qp = make_qp(ctx)
    _, _, _, out = qp.execute_query('range 3; "abc", :list')
    assert out == "[0, 1, 2, abc]"


def test_chain_semicolon_literals_after_inserter(make_ctx):
    """Two literal statements written after an inserter keep their own order too."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_renders)
    qp = make_qp(ctx)
    _, _, _, out = qp.execute_query("range 3; 7; 8, :list")
    assert out == "[0, 1, 2, 7, 8]"


def test_chain_semicolon_inserter_after_literal(make_ctx):
    """A literal statement written before an inserter statement comes before its items."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_renders)
    qp = make_qp(ctx)
    _, _, _, out = qp.execute_query("7; range 3, :list")
    assert out == "[7, 0, 1, 2]"


def test_chain_valid_inserter_plus_operators(make_ctx):
    """Normal chain: inserter + operators remains valid."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_renders)
    qp = make_qp(ctx)
    _, _, _, out = qp.execute_query("fruits, grep berry, :list")
    assert "strawberry" in out
    assert "blueberry" in out


def test_chain_assignment_then_usage(make_ctx):
    """Assignment followed by chain with variable reference."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_renders)
    qp = make_qp(ctx)
    _, _, _, out = qp.execute_query("a := range 3; a, :list")
    assert out == "[0, 1, 2]"


def test_chain_normal_single_inserter(make_ctx):
    """Single inserter without comma works as before."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_renders)
    qp = make_qp(ctx)
    _, _, _, out = qp.execute_query("range 3, :list")
    assert out == "[0, 1, 2]"


# ========================================================================
# Parenthesized groups within chains
# ========================================================================


def test_parens_group_with_operator(make_ctx):
    """(range 5; range 3), sort — parenthesized group followed by operator."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_renders)
    qp = make_qp(ctx)
    _, _, _, out = qp.execute_query("(range 5; range 3), sort, :list")
    assert out == "[0, 0, 1, 1, 2, 2, 3, 4]"


def test_parens_group_without_operator(make_ctx):
    """(range 5; range 3), :list — parenthesized group, no operator."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_renders)
    qp = make_qp(ctx)
    _, _, _, out = qp.execute_query("(range 5; range 3), :list")
    assert out == "[0, 1, 2, 3, 4, 0, 1, 2]"


def test_parens_group_with_unique(make_ctx):
    """(range 5; range 3), unique — dedup combined output."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_renders)
    qp = make_qp(ctx)
    _, _, _, out = qp.execute_query("(range 5; range 3), unique, :list")
    assert out == "[0, 1, 2, 3, 4]"


def test_parens_group_three_sources(make_ctx):
    """(range 5; range 3; range 2), sort — three sources in parens."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_renders)
    qp = make_qp(ctx)
    _, _, _, out = qp.execute_query("(range 5; range 3; range 2), sort, :list")
    assert out == "[0, 0, 0, 1, 1, 1, 2, 2, 3, 4]"


def test_parens_group_literal_after_inserter(make_ctx):
    """(range 3; 7), :list — the group keeps the written order of its statements."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_renders)
    qp = make_qp(ctx)
    _, _, _, out = qp.execute_query("(range 3; 7), :list")
    assert out == "[0, 1, 2, 7]"


def test_parens_group_with_limit(make_ctx):
    """(range 5; range 3), sort, limit 5 — parens + multiple operators."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_renders)
    qp = make_qp(ctx)
    _, _, _, out = qp.execute_query("(range 5; range 3), sort, limit 5, :list")
    assert out == "[0, 0, 1, 1, 2]"


def test_parens_group_preserved_after_desugaring(make_ctx):
    """Parenthesized group is preserved (not flattened) during desugaring."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_renders)

    tree = parse_tree("(range 5; range 3), sort")
    desugared = ctx.container.get(QueryProcessorAPI)._desugar_subqueries(tree)
    chain = desugared.children[0]
    assert chain.item == "CHAIN"
    # First child should still be ROOT (not flattened into range, range)
    assert chain.children[0].item == NODE_ROOT_ITEM
    assert len(chain.children[0].children) == 2
