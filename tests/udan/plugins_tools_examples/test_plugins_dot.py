"""Tests for plugins_dot module."""

import pytest

import udan.plugins_tools_core.plugins_system
import udan.plugins_tools_demo.plugins_demo
import udan.plugins_tools_demo.plugins_fruits
import udan.plugins_tools_examples.plugins_builtins
import udan.plugins_tools_examples.plugins_dot
import udan.renders.plugins_renders
from tests.conftest import make_qp, register_tools_from_module
from udan.core.api_forests import Node
from udan.core_tools_loading.api_types import Edge
from udan.plugins_tools_examples.plugins_dot import as_dot


@pytest.fixture
def ctx_with_dot(make_ctx):
    """Provide an UdanContext with demo and dot plugins registered."""
    ctx = make_ctx()
    register_tools_from_module(ctx, udan.plugins_tools_demo.plugins_demo.__name__)
    register_tools_from_module(ctx, udan.plugins_tools_demo.plugins_fruits.__name__)
    register_tools_from_module(ctx, udan.plugins_tools_examples.plugins_builtins.__name__)
    register_tools_from_module(ctx, udan.plugins_tools_examples.plugins_dot.__name__)
    register_tools_from_module(ctx, udan.renders.plugins_renders.__name__)
    register_tools_from_module(ctx, udan.plugins_tools_core.plugins_system.__name__)
    return ctx


def test_as_dot_with_fruits_similar(ctx_with_dot):
    qp_with_dot = make_qp(ctx_with_dot)
    """Test as_dot replacer generates DOT from fruits, similar_fruits."""
    forest, attrs, render_specs, out = qp_with_dot.execute_query("fruits, limit 3, similar_fruits, as_dot, :raw")

    # Should have digraph header and footer
    assert "digraph {" in out
    assert "}" in out
    # Should have edge arrows
    assert " -> " in out
    # Should have fruit names
    assert "apple" in out or "orange" in out or "banana" in out


def test_as_png_generates_image(ctx_with_dot):
    qp_with_dot = make_qp(ctx_with_dot)
    """Test as_png generates PNG and returns org-mode link."""
    _, _, _, out = qp_with_dot.execute_query("fruits, limit 2, similar_fruits, as_dot, as_png")

    # Should have org-mode file link format
    assert "[[" in out
    assert "]]" in out
    assert "/tmp/" in out
    assert ".png" in out


def test_as_png_no_bullet_prefix(ctx_with_dot):
    qp_with_dot = make_qp(ctx_with_dot)
    """Test as_png returns org link without bullet prefix."""
    _, _, _, out = qp_with_dot.execute_query("fruits, limit 2, similar_fruits, as_dot, as_png")

    # Should NOT have bullet prefix
    assert not out.startswith("- ")
    assert "#+ATTR_ORG" in out
    assert "[[" in out
    assert "]]" in out


def test_as_dot_default_top_to_bottom(ctx_with_dot):
    qp_with_dot = make_qp(ctx_with_dot)
    """Test as_dot with default lr=False (top to bottom)."""
    _, _, _, out = qp_with_dot.execute_query("fruits, limit 2, similar_fruits, as_dot, :raw")

    # Should have rankdir=TB (default)
    assert "rankdir=TB" in out


def test_as_dot_folds_edges_into_one_labeled_edge():
    """Test Edge children between the same pair fold into one edge labeled with their metadata."""
    package = Node.create(
        "src/udan.operator_sorter",
        [
            Node.leaf(Edge(source="udan.operator_sorter", target="udan", metadata="udan.core.api_forests.Item")),
            Node.leaf(Edge(source="udan.operator_sorter", target="udan", metadata="udan.core.api_forests.Node")),
        ],
    )
    ((depth, digraph),) = as_dot([package])

    expected = (
        "digraph {\n"
        "  rankdir=TB;\n"
        '  "udan.operator_sorter" -> "udan" [label="udan.core.api_forests.Item\\nudan.core.api_forests.Node"];\n'
        "}"
    )
    assert depth == 1
    assert digraph == expected


def test_as_dot_splits_edges_by_target():
    """Test Edge items through different targets stay separate edges, sorted."""
    package = Node.create(
        "a",
        [
            Node.leaf(Edge(source="a", target="d2", metadata="d2.e.X")),
            Node.leaf(Edge(source="a", target="d1", metadata="d1.e.X")),
            Node.leaf(Edge(source="a", target="d1", metadata="d1.u.Y")),
        ],
    )
    ((_, digraph),) = as_dot([package])

    expected = 'digraph {\n  rankdir=TB;\n  "a" -> "d1" [label="d1.e.X\\nd1.u.Y"];\n  "a" -> "d2" [label="d2.e.X"];\n}'
    assert digraph == expected


def test_as_dot_without_labels():
    """Test labels=False folds Edge items into plain unlabeled edges."""
    package = Node.create(
        "a",
        [
            Node.leaf(Edge(source="a", target="d1", metadata="d1.e.X")),
            Node.leaf(Edge(source="a", target="d1", metadata="d1.u.Y")),
            Node.leaf(Edge(source="a", target="d2", metadata="d2.e.X")),
        ],
    )
    ((_, digraph),) = as_dot([package], labels=False)

    expected = 'digraph {\n  rankdir=TB;\n  "a" -> "d1";\n  "a" -> "d2";\n}'
    assert digraph == expected


def test_as_dot_edge_without_metadata_stays_unlabeled():
    """Test Edge items without metadata render as plain edges even with labels on."""
    package = Node.create("a", [Node.leaf(Edge(source="a", target="d"))])
    ((_, digraph),) = as_dot([package])

    expected = 'digraph {\n  rankdir=TB;\n  "a" -> "d";\n}'
    assert digraph == expected


def test_as_dot_keeps_plain_children_alongside_edges():
    """Test children that are not Edge items still render as plain string nodes."""
    package = Node.create(
        "src/a",
        [Node.leaf("udan.core.api_forests.Item"), Node.leaf(Edge(source="a", target="d", metadata="d.e.X"))],
    )
    ((_, digraph),) = as_dot([package])

    expected = 'digraph {\n  rankdir=TB;\n  "src/a" -> "udan.core.api_forests.Item";\n  "a" -> "d" [label="d.e.X"];\n}'
    assert digraph == expected


def test_as_dot_edge_parent_with_no_other_children_is_not_standalone():
    """Test a parent whose only children are Edge items does not land on the standalone rank."""
    package = Node.create("a", [Node.leaf(Edge(source="a", target="d"))])
    ((_, digraph),) = as_dot([package])

    assert "rank=same" not in digraph


def test_ioc_deps_produces_dot(ctx_with_dot):
    qp_with_dot = make_qp(ctx_with_dot)
    """Test ioc_deps + as_dot produces DOT with IOC component edges."""
    _, _, _, out = qp_with_dot.execute_query("udan_ioc_deps, as_dot --lr, :raw")

    assert "digraph {" in out
    assert "rankdir=LR" in out
    # Default ignores Logger, Context, Config
    assert '"Logger"' not in out
    assert '"Context"' not in out
    assert '"Config"' not in out
    # The history storage is the history plugin's container factory, built off its config
    assert '"HistoryLogger" -> "HistoryConfig"' in out
    assert '"SavedQueries" -> "HistoryConfig"' in out
    # ConfigRegistry and Injector should still appear
    assert '"ConfigRegistry"' in out
    # Should still have other components
    assert '"ToolsRegistry"' in out


def test_ioc_deps_no_args_shows_all(ctx_with_dot):
    qp_with_dot = make_qp(ctx_with_dot)
    """Test ioc_deps with explicit ignore shows specified components."""
    _, _, _, out = qp_with_dot.execute_query("udan_ioc_deps ToolsRegistry, as_dot --lr, :raw")

    assert "digraph {" in out
    # Now Logger, Context, Config should appear (not in ignore list)
    assert '"Logger"' in out
    # But ToolsRegistry is ignored
    assert '"ToolsRegistry"' not in out


def test_ioc_deps_to_png(ctx_with_dot):
    qp_with_dot = make_qp(ctx_with_dot)
    """Test ioc_deps piped through as_dot + as_png produces PNG link."""
    _, _, _, out = qp_with_dot.execute_query("udan_ioc_deps, as_dot, as_png")

    # Should be org link without bullet prefix
    assert not out.startswith("- ")
    assert "#+ATTR_ORG" in out
    assert "[[" in out
    assert "]]" in out
    assert "/tmp/" in out
    assert ".png" in out


def test_udan_plugins_deps_produces_dot(ctx_with_dot):
    qp_with_dot = make_qp(ctx_with_dot)
    """Test udan_plugins_deps + as_dot produces DOT with plugin edges."""
    _, _, _, out = qp_with_dot.execute_query("udan_plugins_deps, as_dot --lr, :raw")

    assert "digraph {" in out
    assert "rankdir=LR" in out
    # Should have real cross-plugin edges (e.g. markdown -> org)
    assert "markdown" in out
    assert "org" in out


def test_udan_plugins_deps_with_ignore(ctx_with_dot):
    qp_with_dot = make_qp(ctx_with_dot)
    """Test udan_plugins_deps ignores specified plugins."""
    _, _, _, out_all = qp_with_dot.execute_query("udan_plugins_deps, as_dot --lr, :raw")
    _, _, _, out_ign = qp_with_dot.execute_query("udan_plugins_deps markdown, as_dot --lr, :raw")

    assert "markdown" in out_all
    assert '"markdown"' not in out_ign
