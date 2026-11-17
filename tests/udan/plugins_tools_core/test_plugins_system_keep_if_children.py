"""Tests for keep_if_children (structural filter keeping parents by children)."""

import pytest

from tests.conftest import make_qp
from udan.attributes import plugins_operators_attribute
from udan.core.api_forests import Node
from udan.plugins_tools_core import plugins_system
from udan.plugins_tools_demo import plugins_demo, plugins_fruits
from udan.plugins_tools_examples import plugins_builtins


@pytest.fixture
def ctx_keep_if_children(make_ctx):
    return make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_system)


def test_keeps_roots_with_matching_child(ctx_keep_if_children):
    qp_keep_if_children = make_qp(ctx_keep_if_children)
    forest, _attrs, _render, _out = qp_keep_if_children.execute_query(
        'range 5, multiply 3, keep_if_children "c % 6 == 0"'
    )
    assert forest.items == [0, 0, 2, 6, 4, 12]
    assert forest.depths == [0, 1, 0, 1, 0, 1]


def test_same_operator_with_other_predicate(ctx_keep_if_children):
    qp_keep_if_children = make_qp(ctx_keep_if_children)
    forest, _attrs, _render, _out = qp_keep_if_children.execute_query('range 5, multiply 3, keep_if_children "c > 8"')
    assert forest.items == [3, 9, 4, 12]
    assert forest.depths == [0, 1, 0, 1]


def test_childless_nodes_are_dropped(ctx_keep_if_children):
    qp_keep_if_children = make_qp(ctx_keep_if_children)
    forest, _attrs, _render, _out = qp_keep_if_children.execute_query('fruits, keep_if_children "len(str(c)) > 0"')
    assert forest is not None
    assert forest.items == []


def test_kept_node_subtree_is_preserved():
    tree = Node(item=1, children=[Node(item=6, children=[Node(item=12), Node(item=18)]), Node(item=3)])
    kept = plugins_system.keep_if_children(nodes=[tree, Node(item=5, children=[Node(item=7)])], expr="c % 6 == 0")
    assert kept == [(0, 1), (1, 6), (2, 12), (2, 18), (1, 3)]


def test_alias_kchildren(ctx_keep_if_children):
    qp_keep_if_children = make_qp(ctx_keep_if_children)
    forest, _attrs, _render, _out = qp_keep_if_children.execute_query('range 5, multiply 3, kchildren "c % 6 == 0"')
    assert forest.items == [0, 0, 2, 6, 4, 12]
    assert forest.depths == [0, 1, 0, 1, 0, 1]


def test_broken_predicate_fails_loud(ctx_keep_if_children):
    qp_keep_if_children = make_qp(ctx_keep_if_children)
    forest, _attrs, _render, out = qp_keep_if_children.execute_query(
        'range 5, multiply 3, keep_if_children "no_such_name > 1"'
    )
    assert forest is None
    assert "keep_if_children" in out
    assert "no_such_name" in out


def test_keeps_whole_tree_when_every_child_matches(ctx_keep_if_children):
    qp_keep_if_children = make_qp(ctx_keep_if_children)
    forest, _attrs, _render, _out = qp_keep_if_children.execute_query(
        'range 5, multiply 3, keep_if_children "c % 3 == 0"'
    )
    assert forest.items == [0, 0, 1, 3, 2, 6, 3, 9, 4, 12]
    assert forest.depths == [0, 1] * 5
