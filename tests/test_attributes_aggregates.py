"""Tests for aggregate attributes (count, sum, min, max).

Target syntax:  fruits, count
                fruits, sum calories
                fruits, min calories
                fruits, max calories

Aggregate attributes compute a single value from all items in scope.
They are stored as regular attribute values on the root node item
("forest") via the standard attribute storage API.

Fruit calories (ambrosia has None, skipped in aggregates):
  apple=52, orange=47, banana=89, strawberry=32, blueberry=57,
  raspberry=52, grape=62, pineapple=50, mango=60
  count=10, sum=501, min=32, max=89
"""

import pytest

import udan.plugins_tools_examples.plugins_builtins
import udan.plugins_tools_examples.plugins_fs
from tests.conftest import make_qp, register_tools_from_module
from udan.attributes import plugins_aggregates_attribute, plugins_operators_attribute
from udan.attributes.api_attribute_storage import AttributeStorageAPI
from udan.core_tools_loading.api_types import Group
from udan.plugins_tools_demo import plugins_demo, plugins_fruits
from udan.plugins_tools_examples import plugins_builtins

ROOT_ITEM = "forest"


@pytest.fixture
def ctx_aggr(make_ctx):
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute)
    register_tools_from_module(ctx, plugins_aggregates_attribute.__name__)
    return ctx


def _get_agg(ctx, name):
    """Get aggregate value from attribute storage by identity."""
    storage = ctx.container.get(AttributeStorageAPI)
    for at_d, values in storage.attributes.items():
        if at_d.name == name:
            return values.get(ROOT_ITEM)
    return None


# --- count ---


def test_count(ctx_aggr):
    qp_aggr = make_qp(ctx_aggr)
    qp_aggr.execute_query("insert_fruits, count")
    assert _get_agg(ctx_aggr, "count") == 10


def test_count_after_filter(ctx_aggr):
    qp_aggr = make_qp(ctx_aggr)

    register_tools_from_module(ctx_aggr, udan.plugins_tools_examples.plugins_builtins.__name__)
    qp_aggr.execute_query("insert_fruits, greps banana, count")
    assert _get_agg(ctx_aggr, "count") == 1


# --- sum ---


def test_sum_without_attr_raises(ctx_aggr):
    qp_aggr = make_qp(ctx_aggr)
    """sum without an attribute name should show available numeric fields."""
    _, _, _, out = qp_aggr.execute_query("insert_fruits, sum")
    assert "'sum' requires an attribute name" in out
    assert "calories" in out
    # Should be nested: header at depth 0, fields at depth 1
    lines = out.strip().split("\n")
    assert any("calories" in line and line.startswith(" ") for line in lines)


def test_sum_calories(ctx_aggr):
    qp_aggr = make_qp(ctx_aggr)
    qp_aggr.execute_query("insert_fruits, sum calories")
    assert _get_agg(ctx_aggr, "sum") == 501


# --- min ---


def test_min_without_attr(ctx_aggr):
    qp_aggr = make_qp(ctx_aggr)
    qp_aggr.execute_query("insert_fruits, min")
    assert _get_agg(ctx_aggr, "min") == 0.0


def test_min_calories(ctx_aggr):
    qp_aggr = make_qp(ctx_aggr)
    qp_aggr.execute_query("insert_fruits, min calories")
    assert _get_agg(ctx_aggr, "min") == 32.0


# --- max ---


def test_max_without_attr(ctx_aggr):
    qp_aggr = make_qp(ctx_aggr)
    qp_aggr.execute_query("insert_fruits, max")
    assert _get_agg(ctx_aggr, "max") == 0.0


def test_max_calories(ctx_aggr):
    qp_aggr = make_qp(ctx_aggr)
    qp_aggr.execute_query("insert_fruits, max calories")
    assert _get_agg(ctx_aggr, "max") == 89.0


# --- composable ---


def test_count_after_sort(ctx_aggr):
    qp_aggr = make_qp(ctx_aggr)
    qp_aggr.execute_query("insert_fruits, sort_by_field name, count")
    assert _get_agg(ctx_aggr, "count") == 10


# --- grouped aggregates ---


def test_sum_calories_grouped_by_color(ctx_aggr):
    qp_aggr = make_qp(ctx_aggr)
    """Group fruits by color, then sum calories — total should still be 501."""
    qp_aggr.execute_query("insert_fruits, group_by_field color, sum calories")
    assert _get_agg(ctx_aggr, "sum") == 501


def test_sum_calories_grouped_by_ftype(ctx_aggr):
    qp_aggr = make_qp(ctx_aggr)
    """Group fruits by ftype, then sum calories — total should still be 501."""
    qp_aggr.execute_query("insert_fruits, group_by_field ftype, sum calories")
    assert _get_agg(ctx_aggr, "sum") == 501


def test_count_grouped_by_color(ctx_aggr):
    qp_aggr = make_qp(ctx_aggr)
    """Group fruits by color, then count — total should still be 10."""
    qp_aggr.execute_query("insert_fruits, group_by_field color, count")
    assert _get_agg(ctx_aggr, "count") == 10


def _get_group_agg(ctx, name, group_key):
    """Get aggregate value for a specific group."""

    storage = ctx.container.get(AttributeStorageAPI)
    for at_d, values in storage.attributes.items():
        if at_d.name == name:
            for item, val in values.items():
                if isinstance(item, Group) and item.key == group_key:
                    return val
    return None


def test_sum_calories_per_group_by_color(ctx_aggr):
    qp_aggr = make_qp(ctx_aggr)
    """Per-group sums when grouped by color.

    apple=52 (red), strawberry=32 (red), raspberry=52 (red) → red=136
    orange=47 (orange), mango=60 (orange) → orange=107
    banana=89 (yellow), pineapple=50 (yellow) → yellow=139
    blueberry=57 (blue) → blue=57
    grape=62 (purple) → purple=62
    ambrosia=None (None group) → 0 (skipped)
    """
    qp_aggr.execute_query("insert_fruits, group_by_field color, sum calories")
    assert _get_group_agg(ctx_aggr, "sum", "red") == 136
    assert _get_group_agg(ctx_aggr, "sum", "orange") == 107
    assert _get_group_agg(ctx_aggr, "sum", "yellow") == 139
    assert _get_group_agg(ctx_aggr, "sum", "blue") == 57
    assert _get_group_agg(ctx_aggr, "sum", "purple") == 62


def test_count_per_group_by_ftype(ctx_aggr):
    qp_aggr = make_qp(ctx_aggr)
    """Per-group counts when grouped by ftype.

    fruit: apple, orange, banana, grape, pineapple, mango, ambrosia = 7
    berry: strawberry, blueberry, raspberry = 3
    """
    qp_aggr.execute_query("insert_fruits, group_by_field ftype, count")
    assert _get_group_agg(ctx_aggr, "count", "fruit") == 7
    assert _get_group_agg(ctx_aggr, "count", "berry") == 3


def test_sum_calories_nested_groups(ctx_aggr):
    qp_aggr = make_qp(ctx_aggr)
    """Two levels of grouping: by ftype then by color.

    Outer groups (by ftype):
      fruit: apple=52, orange=47, banana=89, grape=62, pineapple=50, mango=60 → sum=360
      berry: strawberry=32, blueberry=57, raspberry=52 → sum=141

    Inner groups (by color within fruit):
      red (in fruit): apple=52 → sum=52
      orange (in fruit): orange=47, mango=60 → sum=107
      yellow (in fruit): banana=89, pineapple=50 → sum=139
      purple (in fruit): grape=62 → sum=62

    Inner groups (by color within berry):
      red (in berry): strawberry=32, raspberry=52 → sum=84
      blue (in berry): blueberry=57 → sum=57
    """
    qp_aggr.execute_query("insert_fruits, group_by_field ftype, group_by_field color, sum calories")
    # Root total
    assert _get_agg(ctx_aggr, "sum") == 501
    # Outer groups (by ftype)
    assert _get_group_agg(ctx_aggr, "sum", "fruit") == 360
    assert _get_group_agg(ctx_aggr, "sum", "berry") == 141
    # Inner groups (by color within berry — must distinguish from red in fruit)
    # There are two "red" groups: one under fruit, one under berry.
    # Both get per-group aggregates stored.
    assert _get_group_agg(ctx_aggr, "sum", "blue") == 57
    assert _get_group_agg(ctx_aggr, "sum", "yellow") == 139
    assert _get_group_agg(ctx_aggr, "sum", "purple") == 62


def test_no_aggregates_not_stored(make_ctx):
    """Without aggregate attrs, no value stored on root."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute)
    qp = make_qp(ctx)
    qp.execute_query("insert_fruits")
    assert _get_agg(ctx, "count") is None


# --- Aggregates over named cattr columns ---


def test_sum_over_named_cattr_column(ctx_aggr):
    qp_aggr = make_qp(ctx_aggr)
    """sum falls back to named cattr columns when the field is absent from items.

    Items are ints here, so the dict-field read finds nothing and the column
    values come from attribute storage.
    """
    qp_aggr.execute_query("range 6, cattr 'it * 2' --name=d, sum d")
    assert _get_agg(ctx_aggr, "sum") == 30  # 0+2+4+6+8+10


def test_sum_over_named_cattr_column_on_dicts(ctx_aggr):
    qp_aggr = make_qp(ctx_aggr)
    """Aggregates mix dict-field and column reads; None column values are skipped.

    ambrosia has calories None, so its doubled column value is None and excluded.
    """
    qp_aggr.execute_query("insert_fruits, cattr 'calories * 2' --name=double_cal, sum double_cal")
    assert _get_agg(ctx_aggr, "sum") == 1002  # 2 * 501


def test_sum_over_named_cattr_column_lazy(ctx_aggr):
    qp_aggr = make_qp(ctx_aggr)
    """A fresh query aggregates a registered column by re-evaluating it lazily.

    Fruit dicts are unhashable and stored per id, so the second query's items
    miss storage and must be computed through the column's registered evaluator.
    """
    qp_aggr.execute_query("insert_fruits, cattr 'calories * 2' --name=double_cal, sum double_cal")
    qp_aggr.execute_query("insert_fruits, sum double_cal")
    assert _get_agg(ctx_aggr, "sum") == 1002


def _get_agg_for_item(ctx, name, item):
    """Get aggregate value stored for a specific item."""
    storage = ctx.container.get(AttributeStorageAPI)
    for at_d, values in storage.attributes.items():
        if at_d.name == name:
            return values.get(item)
    return None


def test_sum_descends_through_extend_tree(ctx_aggr, tmp_path):
    """Subtree sums land on every node above the leaves, not only on Group items.

    The tree is built by an extender, so its inner nodes are plain Paths:
    the directory, the subdirectory - and the root carries the whole query.
    """
    base = tmp_path / "base"
    (base / "a.py").parent.mkdir(parents=True)
    (base / "a.py").write_text("line1\nline2\n")
    (base / "sub").mkdir()
    (base / "sub" / "b.py").write_text("line1\n")

    register_tools_from_module(ctx_aggr, udan.plugins_tools_examples.plugins_fs.__name__)
    qp_aggr = make_qp(ctx_aggr)
    qp_aggr.execute_query(f"ls_files {tmp_path} 'base', extend_dir '*.py' --max-depth=2, sum count_lines")

    assert _get_agg_for_item(ctx_aggr, "sum", base) == 3
    assert _get_agg_for_item(ctx_aggr, "sum", base / "sub") == 1
    assert _get_agg(ctx_aggr, "sum") == 3
