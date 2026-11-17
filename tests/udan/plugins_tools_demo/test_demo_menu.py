"""Tests for menu inserter and menu_fruits extender."""

import pytest

import udan.plugins_tools_demo.plugins_demo
import udan.plugins_tools_demo.plugins_fruits
import udan.plugins_tools_demo.plugins_vegetables
from tests.conftest import make_qp, register_tools_from_module
from udan.core.api_constants import ARG_ON_DEPTH
from udan.core.api_forests import Node
from udan.core.api_operators import OperatorDescriptor
from udan.core.api_query_processor import QueryProcessorAPI
from udan.core.api_type_system import ForestTypeDescriptor
from udan.core.impl_debug_logger import DebugLogger
from udan.core.impl_exec_context import ExecContext
from udan.core_tools_loading.api_types import TypeDescriptor
from udan.plugins_tools_demo import plugins_demo, plugins_fruits, plugins_vegetables
from udan.plugins_tools_demo.plugins_vegetables import Vegetable
from udan.plugins_tools_examples import plugins_builtins, plugins_org
from udan.renders import plugins_renders

opd = OperatorDescriptor.create

# Days extended with vegetables (extend_menu_vegetables) and fruits
# (extend_menu_fruits): both extenders consume the str days, so the fruits are
# added next to the vegetables instead of replacing them
MENU_DAYS_VEGETABLES_FRUITS = [
    "day-1",
    Vegetable(name="potato", quantity=1),
    {"name": "apple", "quantity": 1},
    "day-2",
    Vegetable(name="carrot", quantity=1),
    {"name": "orange", "quantity": 1},
    "day-3",
    Vegetable(name="potato", quantity=2),
    Vegetable(name="broccoli", quantity=1),
    {"name": "apple", "quantity": 2},
    {"name": "orange", "quantity": 1},
    "day-4",
    Vegetable(name="carrot", quantity=1),
    Vegetable(name="spinach", quantity=1),
    Vegetable(name="mandrake"),
    {"name": "apple", "quantity": 1},
    {"name": "grape", "quantity": 1},
    {"name": "mango", "quantity": 1},
]
MENU_DAYS_VEGETABLES_FRUITS_DEPTHS = [0, 1, 1, 0, 1, 1, 0, 1, 1, 1, 1, 0, 1, 1, 1, 1, 1, 1]


@pytest.fixture
def ctx(make_ctx):
    """Provide an UdanContext for testing."""
    ctx = make_ctx()
    register_tools_from_module(ctx, udan.plugins_tools_demo.plugins_demo.__name__)
    register_tools_from_module(ctx, udan.plugins_tools_demo.plugins_fruits.__name__)
    return ctx


@pytest.fixture
def ctx_with_renders(make_ctx):
    """Provide an UdanContext with demo plugins, renders, and org renders registered."""

    ctx = make_ctx()
    register_tools_from_module(ctx, udan.plugins_tools_demo.plugins_demo.__name__)
    register_tools_from_module(ctx, udan.plugins_tools_demo.plugins_fruits.__name__)
    register_tools_from_module(ctx, plugins_builtins.__name__)
    register_tools_from_module(ctx, plugins_renders.__name__)
    register_tools_from_module(ctx, plugins_org.__name__)
    return ctx


def test_menu_inserter_basic(make_ctx):
    """Test menu inserter returns expected days using execute_query."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_renders)
    qp = make_qp(ctx)
    register_tools_from_module(ctx, udan.plugins_tools_demo.plugins_demo.__name__)
    register_tools_from_module(ctx, udan.plugins_tools_demo.plugins_fruits.__name__)

    forest, attrs, render_specs, out = qp.execute_query("menu")

    # Expected: ["day-1", "day-2", "day-3", "day-4"]
    assert forest.items == ["day-1", "day-2", "day-3", "day-4"]
    assert forest.depths == [0, 0, 0, 0]


def test_menu_via_query(ctx_with_renders):
    qp_with_renders = make_qp(ctx_with_renders)
    """Test menu inserter through query execution."""
    forest, attrs, render_specs, out = qp_with_renders.execute_query("menu, :list")
    assert out == "[day-1, day-2, day-3, day-4]"


def test_menu_items_count(make_ctx):
    """Test that menu returns exactly 4 items using execute_query."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_renders)
    qp = make_qp(ctx)
    register_tools_from_module(ctx, udan.plugins_tools_demo.plugins_demo.__name__)
    register_tools_from_module(ctx, udan.plugins_tools_demo.plugins_fruits.__name__)

    forest, attrs, render_specs, out = qp.execute_query("menu")
    assert len(forest.items) == 4


def test_menu_item_format(make_ctx):
    """Test that all menu items follow the expected format using execute_query."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_renders)
    qp = make_qp(ctx)
    register_tools_from_module(ctx, udan.plugins_tools_demo.plugins_demo.__name__)
    register_tools_from_module(ctx, udan.plugins_tools_demo.plugins_fruits.__name__)

    forest, attrs, render_specs, out = qp.execute_query("menu")

    expected = ["day-1", "day-2", "day-3", "day-4"]
    for i, item in enumerate(forest.items):
        assert item == expected[i], f"Item {i} should be {expected[i]}, got {item}"


def test_menu_fruits_extender_all_days(make_ctx):
    """Test menu_fruits extender for all days using execute_query."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_renders)
    qp = make_qp(ctx)
    register_tools_from_module(ctx, udan.plugins_tools_demo.plugins_demo.__name__)
    register_tools_from_module(ctx, udan.plugins_tools_demo.plugins_fruits.__name__)

    forest, attrs, render_specs, out = qp.execute_query("menu, extend_menu_fruits")

    # Forest structure: day-1 (depth 0) -> fruit (depth 1), day-2 (depth 0) -> fruit (depth 1), etc.
    # Expected items: day-1, apple fruit, day-2, orange fruit, day-3,
    #                 apple fruit, orange fruit, day-4, apple, grape, mango
    expected_items = [
        "day-1",
        {"name": "apple", "quantity": 1},
        "day-2",
        {"name": "orange", "quantity": 1},
        "day-3",
        {"name": "apple", "quantity": 2},
        {"name": "orange", "quantity": 1},
        "day-4",
        {"name": "apple", "quantity": 1},
        {"name": "grape", "quantity": 1},
        {"name": "mango", "quantity": 1},
    ]
    expected_depths = [0, 1, 0, 1, 0, 1, 1, 0, 1, 1, 1]

    assert forest.items == expected_items
    assert forest.depths == expected_depths


def test_menu_fruits_direct_day1():
    """Test menu_fruits extender directly for day-1."""
    result = udan.plugins_tools_demo.plugins_fruits.extend_menu_fruits("day-1")
    assert result == [{"name": "apple", "quantity": 1}]


def test_menu_fruits_direct_day2():
    """Test menu_fruits extender directly for day-2."""
    result = udan.plugins_tools_demo.plugins_fruits.extend_menu_fruits("day-2")
    assert result == [{"name": "orange", "quantity": 1}]


def test_menu_fruits_direct_day3():
    """Test menu_fruits extender directly for day-3."""
    result = udan.plugins_tools_demo.plugins_fruits.extend_menu_fruits("day-3")
    assert result == [{"name": "apple", "quantity": 2}, {"name": "orange", "quantity": 1}]


def test_menu_fruits_direct_day4():
    """Test menu_fruits extender directly for day-4."""
    result = udan.plugins_tools_demo.plugins_fruits.extend_menu_fruits("day-4")
    assert result == [
        {"name": "apple", "quantity": 1},
        {"name": "grape", "quantity": 1},
        {"name": "mango", "quantity": 1},
    ]


def test_menu_fruits_direct_day5():
    """Test menu_fruits extender directly for day-5 (empty)."""
    result = udan.plugins_tools_demo.plugins_fruits.extend_menu_fruits("day-5")
    assert result == []


def test_menu_fruits_direct_unknown_day():
    """Test menu_fruits extender directly for unknown day."""
    result = udan.plugins_tools_demo.plugins_fruits.extend_menu_fruits("day-99")
    assert result == []


def test_menu_fruits_via_query(ctx_with_renders):
    qp_with_renders = make_qp(ctx_with_renders)
    """Test menu_fruits extender through query execution."""
    forest, attrs, render_specs, out = qp_with_renders.execute_query("menu, extend_menu_fruits, :org")
    # Should contain the tree structure with days and their fruits
    assert "day-1" in out
    assert "day-2" in out
    assert "day-3" in out
    assert "day-4" in out
    assert "apple" in out
    assert "orange" in out
    assert "grape" in out
    assert "mango" in out


@pytest.fixture
def ctx_menu_extenders(make_ctx):
    """Provide a context with the menu inserter and both menu extenders registered."""
    return make_ctx(plugins_demo, plugins_fruits, plugins_vegetables)


def test_menu_vegetables_and_fruits_extenders(ctx_menu_extenders):
    qp_menu_extenders = make_qp(ctx_menu_extenders)
    """Chained menu extenders both extend the days: fruits must not replace vegetables.

    extend_menu_fruits consumes str (the days), so the core derives --on-depth=0
    (the days sit at level 0, one level above the Vegetable level the previous
    extender created) and the fruits are added next to the vegetables.
    """
    forest, attrs, render_specs, out = qp_menu_extenders.execute_query(
        "menu, extend_menu_vegetables, extend_menu_fruits"
    )

    assert forest.items == MENU_DAYS_VEGETABLES_FRUITS
    assert forest.depths == MENU_DAYS_VEGETABLES_FRUITS_DEPTHS


def test_menu_extenders_explicit_on_depth(ctx_menu_extenders):
    qp_menu_extenders = make_qp(ctx_menu_extenders)
    """The prescribed explicit form of the query gives the same forest."""
    forest, attrs, render_specs, out = qp_menu_extenders.execute_query(
        "menu, extend_menu_vegetables, extend_menu_fruits --on-depth=0"
    )

    assert forest.items == MENU_DAYS_VEGETABLES_FRUITS
    assert forest.depths == MENU_DAYS_VEGETABLES_FRUITS_DEPTHS


def test_menu_extender_on_depth_targets_level_one(ctx_menu_extenders):
    qp_menu_extenders = make_qp(ctx_menu_extenders)
    """An explicit --on-depth=1 extends the vegetables, not the days."""
    forest, attrs, render_specs, out = qp_menu_extenders.execute_query(
        "menu, extend_menu_vegetables, similar_vegetables --on-depth=1"
    )

    names = [item.name if isinstance(item, Vegetable) else item for item in forest.items]
    assert names == [
        "day-1",
        "potato",
        "day-2",
        "carrot",
        "mandrake",
        "day-3",
        "potato",
        "broccoli",
        "spinach",
        "day-4",
        "carrot",
        "mandrake",
        "spinach",
        "broccoli",
        "mandrake",
        "carrot",
    ]
    assert forest.depths == [0, 1, 0, 1, 2, 0, 1, 1, 2, 0, 1, 2, 1, 2, 1, 2]


MENU_DAYS_VEGETABLES_FTD = ForestTypeDescriptor(depths=[TypeDescriptor(name="str"), TypeDescriptor(name="Vegetable")])


def test_derive_extender_on_depth_lets_a_selector_word_win(ctx_menu_extenders):
    """An explicit --on-depth word names the target, so the extender is not re-targeted.

    extend_menu_fruits consumes str while the level extend_menu_vegetables creates is
    Vegetable, so the core derives --on-depth=0 for it - unless the query already
    carries an --on-depth, whatever that value is.
    """
    qp_menu_extenders = ctx_menu_extenders.container.get(QueryProcessorAPI)
    exec_ctx = ExecContext(logger=DebugLogger(log_time=False))

    derived = qp_menu_extenders._derive_extender_on_depth(
        Node.create(item=opd("extend_menu_fruits")), MENU_DAYS_VEGETABLES_FTD, exec_ctx
    )
    assert derived.item.tool_args == ((ARG_ON_DEPTH, 0),)

    explicit = opd("extend_menu_fruits", tool_args=[(ARG_ON_DEPTH, "leaf")])
    kept = qp_menu_extenders._derive_extender_on_depth(Node.create(item=explicit), MENU_DAYS_VEGETABLES_FTD, exec_ctx)
    assert kept.item.tool_args == ((ARG_ON_DEPTH, "leaf"),)
