"""Tests verifying when a per-item attribute is computed: at its chain position.

An attribute is applied at the position it is written at, over the items that exist
there - exactly once per item, and only there. So `range 6, is_odd, tracked_twice`
computes the attribute for the surviving items only, while the same attribute written
before the filter computes it for every item the filter then selects from.
"""

import pytest

import tests.plugins_test_lazy_attrs as lazy_module
from tests.conftest import make_qp, register_tools_from_module
from udan.plugins_tools_demo import plugins_demo, plugins_fruits


@pytest.fixture
def ctx_with_lazy_attrs(make_ctx):
    """Context with lazy attribute test operators registered."""
    ctx = make_ctx(plugins_demo, plugins_fruits)
    register_tools_from_module(ctx, lazy_module.__name__)
    return ctx


def test_attribute_after_filter_only_surviving_items(ctx_with_lazy_attrs):
    """Attribute AFTER filter: only computed for the items that survive it."""
    lazy_module.reset_call_log()
    ctx = ctx_with_lazy_attrs
    qp = make_qp(ctx)

    af, *_ = qp.execute_query("range 6, is_odd, tracked_twice")

    assert af.items == [1, 3, 5]
    assert lazy_module.call_log == {1: 1, 3: 1, 5: 1}


def test_attribute_before_filter_computes_at_position(ctx_with_lazy_attrs):
    """Attribute BEFORE filter: computed at its position, once per item existing there.

    The filter selects from the values already computed; the items it removes were
    computed for nothing (extra work, no semantic change), and nothing is recomputed
    by a later pass.
    """
    lazy_module.reset_call_log()
    ctx = ctx_with_lazy_attrs
    qp = make_qp(ctx)

    af, *_ = qp.execute_query("range 6, tracked_twice, is_odd")

    assert af.items == [1, 3, 5]
    assert lazy_module.call_log == {0: 1, 1: 1, 2: 1, 3: 1, 4: 1, 5: 1}


def test_attribute_computed_for_all_items_without_filter(ctx_with_lazy_attrs):
    """Without a filter, attribute is computed for all items."""
    lazy_module.reset_call_log()
    ctx = ctx_with_lazy_attrs
    qp = make_qp(ctx)

    af, *_ = qp.execute_query("range 5, tracked_twice")

    assert af.items == [0, 1, 2, 3, 4]
    assert lazy_module.call_log == {0: 1, 1: 1, 2: 1, 3: 1, 4: 1}


def test_attribute_even_filter_both_orderings(ctx_with_lazy_attrs):
    """Even filter with the attribute on either side: position decides what is computed."""
    ctx = ctx_with_lazy_attrs
    qp = make_qp(ctx)

    lazy_module.reset_call_log()
    af, *_ = qp.execute_query("range 6, is_even, tracked_twice")
    assert af.items == [0, 2, 4]
    assert lazy_module.call_log == {0: 1, 2: 1, 4: 1}

    lazy_module.reset_call_log()
    af, *_ = qp.execute_query("range 6, tracked_twice, is_even")
    assert af.items == [0, 2, 4]
    assert lazy_module.call_log == {0: 1, 1: 1, 2: 1, 3: 1, 4: 1, 5: 1}
