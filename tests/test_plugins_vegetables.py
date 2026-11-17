"""Tests for the vegetables plugin: Vegetable(BaseModel) items through the engine.

Mirrors the fruit-plugin checks from test_impl_renders, test_plugins_demo,
test_demo_menu, test_forest_types and test_impl_config, with pydantic models
instead of dicts. The sort/filter/group/map field tools must work on
these object items the same way they work on fruit dicts.
"""

from tests.conftest import make_qp, register_tools_from_module
from udan.attributes import plugins_operators_attribute
from udan.core.api_attributes import AttributeDescriptor
from udan.core.config import UdanConfig
from udan.core.impl_ioc import create_udan_container
from udan.core.impl_udan_context import UdanContext
from udan.core_tools_loading.api_types import Group, TypeDescriptor
from udan.plugins_history import plugins_history
from udan.plugins_tools_core import plugins_help, plugins_system
from udan.plugins_tools_demo import plugins_demo, plugins_vegetables
from udan.plugins_tools_demo.plugins_vegetables import (
    ALL_VEGETABLES,
    Vegetable,
    extend_menu_vegetables,
    insert_vegetables,
)
from udan.plugins_tools_examples import plugins_builtins
from udan.renders import plugins_renders

MODULES = (
    plugins_demo,
    plugins_vegetables,
    plugins_builtins,
    plugins_operators_attribute,
    plugins_help,
    plugins_system,
    plugins_history,
    plugins_renders,
)

POTATO_EMOJI_LINE = "\U0001f954 potato"
CARROT_EMOJI_LINE = "\U0001f955 carrot"
BROCCOLI_EMOJI_LINE = "\U0001f966 broccoli"
SPINACH_EMOJI_LINE = "\U0001f96c spinach"
MANDRAKE_BARE_LINE = "mandrake"

POTATO_RAW = "id=1 name='potato' calories=77 color='brown' ftype='tuber' tags=['vegetable', 'starchy'] quantity=None"
MANDRAKE_RAW = "id=5 name='mandrake' calories=None color=None ftype='vegetable' tags=[] quantity=None"


def _menu_raw(name: str, quantity: int | None) -> str:
    """Rendered menu child line for a minimal Vegetable entry with the given quantity."""
    return f"  - id=0 name='{name}' calories=None color=None ftype='vegetable' tags=[] quantity={quantity}"


def create_vegetables_ctx_with_config(config):
    """Helper to create UdanContext with config and the vegetables plugin registered."""
    container = create_udan_container(config)
    ctx = container.get(UdanContext)._with_plugins()
    ctx.container = container
    register_tools_from_module(ctx, insert_vegetables.__module__)
    return ctx


# --------------------------------------------------------------------------
# Inserter
# --------------------------------------------------------------------------


def test_insert_vegetables_returns_models():
    result = insert_vegetables()

    assert result is ALL_VEGETABLES
    assert len(result) == 5
    assert all(isinstance(vegetable, Vegetable) for vegetable in result)
    assert [vegetable.name for vegetable in result] == ["potato", "carrot", "broccoli", "spinach", "mandrake"]


def test_insert_vegetables_pattern_filter():
    assert [vegetable.name for vegetable in insert_vegetables(pattern="ro")] == ["carrot", "broccoli"]
    assert [vegetable.name for vegetable in insert_vegetables(pattern="MAN")] == ["mandrake"]
    assert len(insert_vegetables(pattern="")) == 5


def test_vegetables_default_render(make_ctx):
    ctx = make_ctx(*MODULES)
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query("vegetables")

    assert out.strip().split("\n") == [
        POTATO_EMOJI_LINE,
        CARROT_EMOJI_LINE,
        BROCCOLI_EMOJI_LINE,
        SPINACH_EMOJI_LINE,
        MANDRAKE_BARE_LINE,
    ]


def test_vegetables_raw_render_shows_model_fields(make_ctx):
    ctx = make_ctx(*MODULES)
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query("vegetables, :raw")

    lines = out.strip().split("\n")
    assert len(lines) == 5
    assert lines[0] == POTATO_RAW
    assert lines[4] == MANDRAKE_RAW


def test_vegetable_render_reachable_by_explicit_spec(make_ctx):
    ctx = make_ctx(*MODULES)
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query("vegetables, :vegetable")

    assert render_specs[0].name == "vegetable"
    assert out.strip().split("\n")[0] == POTATO_EMOJI_LINE


def test_vegetables_render_listed(make_ctx):
    ctx = make_ctx(*MODULES)
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query("vegetables, :")

    assert out.startswith("- domain=")
    assert "render_vegetable" in out


# --------------------------------------------------------------------------
# Attributes
# --------------------------------------------------------------------------


def test_vegetable_translate_ru_attribute(make_ctx):
    ctx = make_ctx(*MODULES)
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query(
        "vegetables, vegetable_translate_ru, map_attr vegetable_translate_ru, :list"
    )

    assert out == "[картофель, морковь, брокколи, шпинат, None]"


def test_vegetable_translate_ru_upper_dependencies_translate(make_ctx):
    ctx = make_ctx(*MODULES)
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query(
        "vegetables, vegetable_translate_ru_upper, map_attr vegetable_translate_ru_upper, :list"
    )

    assert out == "[КАРТОФЕЛЬ, МОРКОВЬ, БРОККОЛИ, ШПИНАТ, None]"


def test_vegetable_pfc_attribute(make_ctx):
    ctx = make_ctx(*MODULES)
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query("vegetables, vegetable_pfc, map_attr vegetable_pfc, :list")

    assert out == (
        "[{'proteins': 2.0, 'fats': 0.1, 'carbs': 17.0}, {'proteins': 0.9, 'fats': 0.2, 'carbs': 9.6}, "
        "{'proteins': 2.8, 'fats': 0.4, 'carbs': 6.6}, {'proteins': 2.9, 'fats': 0.4, 'carbs': 3.6}, None]"
    )


def test_vegetable_cost_attribute(make_ctx):
    ctx = make_ctx(*MODULES)
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query("vegetables, vegetable_cost, map_attr vegetable_cost, :list")

    assert out == "[0.4, 0.3, 1.5, 1.8, None]"


# --------------------------------------------------------------------------
# Extenders
# --------------------------------------------------------------------------


def test_similar_vegetables_creates_nested_structure(make_ctx):
    """Bucket by crc32(name) % 4: potato is alone, carrot~mandrake, broccoli~spinach."""
    ctx = make_ctx(*MODULES)
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query("vegetables, similar_vegetables")

    assert out.strip().split("\n") == [
        POTATO_EMOJI_LINE,
        CARROT_EMOJI_LINE,
        f"  {MANDRAKE_BARE_LINE}",
        BROCCOLI_EMOJI_LINE,
        f"  {SPINACH_EMOJI_LINE}",
        SPINACH_EMOJI_LINE,
        f"  {BROCCOLI_EMOJI_LINE}",
        MANDRAKE_BARE_LINE,
        f"  {CARROT_EMOJI_LINE}",
    ]


def test_extend_menu_vegetables_direct():
    day1 = extend_menu_vegetables("day-1")
    assert [vegetable.name for vegetable in day1] == ["potato"]
    assert day1[0].quantity == 1
    assert day1[0].calories is None

    day3 = extend_menu_vegetables("day-3")
    assert [(vegetable.name, vegetable.quantity) for vegetable in day3] == [("potato", 2), ("broccoli", 1)]

    day4 = extend_menu_vegetables("day-4")
    assert [vegetable.name for vegetable in day4] == ["carrot", "spinach", "mandrake"]

    assert extend_menu_vegetables("day-5") == []
    assert extend_menu_vegetables("day-unknown") == []


def test_extend_menu_vegetables_via_query(make_ctx):
    ctx = make_ctx(*MODULES)
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query("menu, extend_menu_vegetables")

    assert out.strip().split("\n") == [
        "- day-1",
        _menu_raw("potato", 1),
        "- day-2",
        _menu_raw("carrot", 1),
        "- day-3",
        _menu_raw("potato", 2),
        _menu_raw("broccoli", 1),
        "- day-4",
        _menu_raw("carrot", 1),
        _menu_raw("spinach", 1),
        _menu_raw("mandrake", None),
    ]


# --------------------------------------------------------------------------
# Forest types
# --------------------------------------------------------------------------


def test_vegetables_forest_types(make_ctx):
    ctx = make_ctx(*MODULES)
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query("vegetables")

    assert forest.types.depths == [TypeDescriptor(name="Vegetable", semantic="vegetable")]


def test_vegetable_attribute_attaches_to_level(make_ctx):
    ctx = make_ctx(*MODULES)
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query("vegetables, vegetable_cost")

    assert forest.types.depths == [
        TypeDescriptor(name="Vegetable", semantic="vegetable", requested=[AttributeDescriptor.create("vegetable_cost")])
    ]
    assert out.strip().split("\n")[0] == POTATO_EMOJI_LINE


# --------------------------------------------------------------------------
# Universal field tools on model items
# --------------------------------------------------------------------------


def test_sort_by_field_on_vegetable_models(make_ctx):
    ctx = make_ctx(*MODULES)
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query("vegetables, sort_by_field calories, map_field name, :list")

    assert out == "[spinach, broccoli, carrot, potato, mandrake]"


def test_sort_by_field_on_vegetable_models_desc(make_ctx):
    ctx = make_ctx(*MODULES)
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query(
        "vegetables, sort_by_field calories --desc, map_field name, :list"
    )

    assert out == "[potato, carrot, broccoli, spinach, mandrake]"


def test_filter_field_on_vegetable_models(make_ctx):
    ctx = make_ctx(*MODULES)
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query(
        "vegetables, filter_field color == green, map_field name, :list"
    )

    assert out == "[broccoli, spinach]"


def test_filter_field_numeric_comparison_on_vegetable_models(make_ctx):
    ctx = make_ctx(*MODULES)
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query("vegetables, filter_field calories > 35, map_field name, :list")

    assert out == "[potato, carrot]"


def test_group_by_field_on_vegetable_models(make_ctx):
    ctx = make_ctx(*MODULES)
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query("vegetables, group_by_field color")

    group_items = [item for item in forest.items if isinstance(item, Group)]
    assert {group.key for group in group_items} == {"brown", "orange", "green", None}

    green_idx = next(idx for idx, item in enumerate(forest.items) if isinstance(item, Group) and item.key == "green")
    green_names = []
    for idx in range(green_idx + 1, len(forest.items)):
        if forest.depths[idx] == 0:
            break
        green_names.append(forest.items[idx].name)
    assert green_names == ["broccoli", "spinach"]


def test_group_by_intervals_on_vegetable_models(make_ctx):
    ctx = make_ctx(*MODULES)
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query("vegetables, group_by_intervals calories 30 50")

    assert out.strip().split("\n") == [
        "- [50..) ::",
        f"  {POTATO_EMOJI_LINE}",
        "- [30..50) ::",
        f"  {CARROT_EMOJI_LINE}",
        f"  {BROCCOLI_EMOJI_LINE}",
        "- (..30) ::",
        f"  {SPINACH_EMOJI_LINE}",
        "- None ::",
        f"  {MANDRAKE_BARE_LINE}",
    ]


def test_map_field_on_vegetable_models(make_ctx):
    ctx = make_ctx(*MODULES)
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query("vegetables, map_field name, :list")

    assert out == "[potato, carrot, broccoli, spinach, mandrake]"


# --------------------------------------------------------------------------
# Config defaults
# --------------------------------------------------------------------------


def test_insert_vegetables_with_config_default():
    config = UdanConfig()
    config.udan_tools_variables_defaults["insert_vegetables"] = {"pattern": "bro"}
    ctx = create_vegetables_ctx_with_config(config)
    qp = make_qp(ctx)

    forest, attrs, render_specs, out = qp.execute_query("insert_vegetables")

    assert out.strip().split("\n") == [BROCCOLI_EMOJI_LINE]


def test_insert_vegetables_with_explicit_empty_pattern():
    config = UdanConfig()
    config.udan_tools_variables_defaults["insert_vegetables"] = {"pattern": "bro"}
    ctx = create_vegetables_ctx_with_config(config)
    qp = make_qp(ctx)

    forest, attrs, render_specs, out = qp.execute_query("insert_vegetables --pattern=''")

    assert len(out.strip().split("\n")) == 5
    assert out.strip().split("\n")[0] == POTATO_EMOJI_LINE


def test_insert_vegetables_with_explicit_pattern():
    config = UdanConfig()
    config.udan_tools_variables_defaults["insert_vegetables"] = {"pattern": "bro"}
    ctx = create_vegetables_ctx_with_config(config)
    qp = make_qp(ctx)

    forest, attrs, render_specs, out = qp.execute_query("insert_vegetables --pattern=in")

    assert out.strip().split("\n") == [SPINACH_EMOJI_LINE]
