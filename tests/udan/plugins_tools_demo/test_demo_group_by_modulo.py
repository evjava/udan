"""Tests for group_by_modulo grouper."""

from tests.conftest import make_qp
from udan.attributes import plugins_operators_attribute
from udan.core.api_forests import Forest
from udan.core_tools_loading.api_types import Group
from udan.plugins_tools_demo import plugins_demo, plugins_fruits
from udan.plugins_tools_demo.plugins_demo import group_by_modulo
from udan.plugins_tools_examples import plugins_builtins

GROUP_0 = Group(key="0(mod 2)")
GROUP_1 = Group(key="1(mod 2)")
GROUP_0_MOD_3 = Group(key="0(mod 3)")
GROUP_1_MOD_3 = Group(key="1(mod 3)")
GROUP_2_MOD_3 = Group(key="2(mod 3)")

EXPECTED_MODULO_2 = Forest(
    items=[GROUP_0, 0, 2, 4, GROUP_1, 1, 3, 5],
    depths=[0, 1, 1, 1, 0, 1, 1, 1],
)

EXPECTED_MODULO_3 = Forest(
    items=[GROUP_0_MOD_3, 0, 3, GROUP_1_MOD_3, 1, 4, GROUP_2_MOD_3, 2, 5],
    depths=[0, 1, 1, 0, 1, 1, 0, 1, 1],
)


def test_group_by_modulo_direct():
    """Test group_by_modulo grouper function directly."""

    # Divisor 2 (default)
    assert group_by_modulo(0) == Group(key="0(mod 2)")
    assert group_by_modulo(4) == Group(key="0(mod 2)")
    assert group_by_modulo(1) == Group(key="1(mod 2)")
    assert group_by_modulo(5) == Group(key="1(mod 2)")

    # Other divisors, string divisor from query parsing
    assert group_by_modulo(5, 3) == Group(key="2(mod 3)")
    assert group_by_modulo(5, "3") == Group(key="2(mod 3)")
    assert group_by_modulo(9, 10) == Group(key="9(mod 10)")


def test_range_6_group_by_modulo_2(make_ctx):
    """Test range 6, group_by_modulo 2 -> group=0 [0, 2, 4], group=1 [1, 3, 5]."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute)
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query("range 6, group_by_modulo 2")

    assert forest.items == EXPECTED_MODULO_2.items
    assert forest.depths == EXPECTED_MODULO_2.depths


def test_range_6_group_by_modulo_3(make_ctx):
    """Test range 6, group_by_modulo 3 -> three groups with pairwise remainders."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute)
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query("range 6, group_by_modulo 3")

    assert forest.items == EXPECTED_MODULO_3.items
    assert forest.depths == EXPECTED_MODULO_3.depths


def test_group_by_modulo_render(make_ctx):
    """Test rendered output of range 6, group_by_modulo 2."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute)
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query("range 6, group_by_modulo 2")

    lines = out.strip().split("\n")
    assert lines == [
        "- group=0(mod 2)",
        "  - 0",
        "  - 2",
        "  - 4",
        "- group=1(mod 2)",
        "  - 1",
        "  - 3",
        "  - 5",
    ]


def test_group_by_modulo_default_divisor(make_ctx):
    """Test group_by_modulo without an argument uses divisor 2."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute)
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query("range 6, group_by_modulo")

    assert forest.items == EXPECTED_MODULO_2.items
    assert forest.depths == EXPECTED_MODULO_2.depths
