"""Tests for the tags plugin (has_tag, group_by_tags_max, group_by_tags_fixed, filter_tags, show_tags_tree)."""

import json
from types import SimpleNamespace

import udan.plugins_tools_examples.plugins_json
from tests.conftest import make_qp, register_tools_from_module
from udan.core_tools_loading.api_types import Group
from udan.plugins_tools_demo import plugins_demo, plugins_fruits
from udan.plugins_tools_examples import plugins_tags
from udan.plugins_tools_examples.plugins_org_parser import OrgItem
from udan.plugins_tools_examples.plugins_tags import (
    NO_OTHER_TAGS_TAG,
    filter_tags,
    group_by_tags_fixed,
    group_by_tags_max,
    has_tag,
    show_tags_tree,
    tags_tree_item,
)


def _node(tags):
    """Build a SimpleNamespace node wrapping a tagged dict item (replacer input)."""
    return SimpleNamespace(item={"tags": tags})


def _group_keys(pairs):
    """Return the (depth, Group.key) pairs for grouping markers only."""

    return [(depth, item.key) for depth, item in pairs if isinstance(item, Group)]


def _group_keys_with_order(pairs):
    """Return the (depth, key, order) triples for grouping markers."""

    return [(depth, item.key, item.order) for depth, item in pairs if isinstance(item, Group)]


def _group_members(pairs):
    """Return a mapping group_key -> list of member items (depth-1 leaves)."""

    result = {}
    current = None
    for depth, item in pairs:
        if isinstance(item, Group):
            current = item.key
            result[current] = []
        else:
            result[current].append(item)
    return result


def _query_group_members(forest):
    """Return a mapping group_key -> list of member items from an executed forest."""

    return _group_members(list(zip(forest.depths, forest.items)))


def test_example_from_spec():
    """Items (a,b), (b,c), (d) -> groups (b) and (others)."""
    nodes = [
        _node(["a", "b"]),
        _node(["b", "c"]),
        _node(["d"]),
    ]
    pairs = group_by_tags_max(nodes)

    assert _group_keys(pairs) == [(0, "b"), (0, "others")]

    members = _group_members(pairs)
    assert members["b"] == [{"tags": ["a", "b"]}, {"tags": ["b", "c"]}]
    assert members["others"] == [{"tags": ["d"]}]


def test_most_popular_first():
    """Groups are ordered by descending tag frequency."""
    nodes = [
        _node(["x", "a"]),
        _node(["a"]),
        _node(["b"]),
        _node(["b"]),
        _node(["b"]),
        _node(["c"]),
    ]
    # a=2, b=3, c=1, x=1 -> order b, a, then c/x collapse into others.
    pairs = group_by_tags_max(nodes, collapse_on=1)

    assert _group_keys(pairs) == [(0, "b"), (0, "a"), (0, "others")]


def test_group_order_is_sequence_position():
    """Each Group carries an explicit order reflecting its position."""
    nodes = [
        _node(["a"]),
        _node(["b"]),
        _node(["b"]),
    ]
    # a=1 (collapses), b=2 -> kept=[b], others=[a].
    pairs = group_by_tags_max(nodes, collapse_on=1)

    assert _group_keys_with_order(pairs) == [(0, "b", 0), (0, "others", 1)]


def test_collapse_on_zero_makes_every_tag_its_own_group():
    nodes = [
        _node(["a"]),
        _node(["b"]),
    ]
    pairs = group_by_tags_max(nodes, collapse_on=0)

    assert _group_keys(pairs) == [(0, "a"), (0, "b")]


def test_no_tags_go_to_others():
    nodes = [
        _node(["a"]),
        _node([]),
    ]
    # a freq=1 <= collapse_on=1 -> a collapses too; no-tag also others.
    pairs = group_by_tags_max(nodes, collapse_on=1)

    assert _group_keys(pairs) == [(0, "others")]
    members = _group_members(pairs)
    assert members["others"] == [{"tags": ["a"]}, {"tags": []}]


def test_ties_broken_alphabetically():
    """Equal frequencies keep all tags as separate groups in alphabetical order."""
    nodes = [
        _node(["c"]),
        _node(["a"]),
        _node(["b"]),
    ]
    # a=b=c=1 <= collapse_on=1 -> everything collapses; use collapse_on=0.
    pairs = group_by_tags_max(nodes, collapse_on=0)

    assert _group_keys(pairs) == [(0, "a"), (0, "b"), (0, "c")]


def test_item_with_multiple_tags_picks_most_popular():
    """An item carrying several tags is assigned to its most frequent one."""
    nodes = [
        _node(["a", "b"]),  # a and b; b more frequent overall
        _node(["b"]),
        _node(["b"]),
    ]
    # a=1, b=3. collapse_on=1 -> keep b; the (a,b) item joins b, a has no sole owner.
    pairs = group_by_tags_max(nodes, collapse_on=1)

    assert _group_keys(pairs) == [(0, "b")]
    members = _group_members(pairs)
    assert members["b"] == [{"tags": ["a", "b"]}, {"tags": ["b"]}, {"tags": ["b"]}]


def test_duplicate_tags_are_deduplicated():

    nodes = [_node(["a", "a", "b"])]
    pairs = group_by_tags_max(nodes, collapse_on=0)

    keys = [item.key for _depth, item in pairs if isinstance(item, Group)]
    assert keys == ["a", "b"]


# -- group_by_tags_fixed -------------------------------------------------------


def test_group_by_tags_fixed_example():
    """Items are assigned to the first matching fixed group, else <others>."""

    groups = ["a,b", "b,c", "d"]

    assert group_by_tags_fixed({"tags": ["a", "b"]}, groups) == Group(key="a,b", order=0)
    assert group_by_tags_fixed({"tags": ["b", "c"]}, groups) == Group(key="b,c", order=1)
    assert group_by_tags_fixed({"tags": ["d"]}, groups) == Group(key="d", order=2)
    assert group_by_tags_fixed({"tags": ["x"]}, groups) == Group(key="<others>", order=3)


def test_group_by_tags_fixed_first_match_wins():
    """An item matching several groups goes to the earliest listed one."""

    groups = ["a,b", "b,c"]
    # has both a,b and b,c -> matches "a,b" first.
    assert group_by_tags_fixed({"tags": ["a", "b", "c"]}, groups) == Group(key="a,b", order=0)


def test_group_by_tags_fixed_empty_group_spec_skipped():
    """Empty/blank group specs do not accidentally match everything."""

    groups = ["", " d "]
    assert group_by_tags_fixed({"tags": ["d"]}, groups) == Group(key="d", order=1)
    assert group_by_tags_fixed({"tags": []}, groups) == Group(key="<others>", order=2)


def test_group_by_tags_fixed_custom_field():
    """The field parameter selects which item field holds the tags."""

    groups = ["a,b", "c"]

    assert group_by_tags_fixed({"other_fields": ["a", "b"]}, groups, field="other_fields") == Group(key="a,b", order=0)
    assert group_by_tags_fixed({"other_fields": ["c"]}, groups, field="other_fields") == Group(key="c", order=1)
    assert group_by_tags_fixed({"other_fields": ["x"]}, groups, field="other_fields") == Group(key="<others>", order=2)
    # When a custom field is given, the default "tags" field is ignored.
    assert group_by_tags_fixed({"tags": ["a", "b"], "other_fields": ["c"]}, groups, field="other_fields") == Group(
        key="c", order=1
    )


def test_group_by_tags_fixed_query_default_field(make_ctx, tmp_path):
    """Query with a vararg grouper that also has a named parameter works (no restriction)."""
    ctx = make_ctx()
    qp = make_qp(ctx)
    register_tools_from_module(ctx, udan.plugins_tools_examples.plugins_json.__name__, verbose=False)
    register_tools_from_module(ctx, plugins_tags.__name__, verbose=False)

    data_file = tmp_path / "items.json"
    data_file.write_text(
        json.dumps(
            [
                {"name": "alpha", "tags": ["a"]},
                {"name": "beta", "other_fields": ["a"]},
            ]
        )
    )

    forest, _attrs, _render_specs, _out = qp.execute_query(f'read_json "{data_file}", group_by_tags_fixed "a"')

    members = _query_group_members(forest)
    assert members == {"a": [{"name": "alpha", "tags": ["a"]}], "<others>": [{"name": "beta", "other_fields": ["a"]}]}


def test_group_by_tags_fixed_query_named_field_binds_to_field_not_vararg(make_ctx, tmp_path):
    """--field=other_fields is detected as the `field` argument, not swallowed by the vararg."""
    ctx = make_ctx()
    qp = make_qp(ctx)
    register_tools_from_module(ctx, udan.plugins_tools_examples.plugins_json.__name__, verbose=False)
    register_tools_from_module(ctx, plugins_tags.__name__, verbose=False)

    data_file = tmp_path / "items.json"
    data_file.write_text(
        json.dumps(
            [
                {"name": "alpha", "tags": ["a"], "other_fields": ["x"]},
                {"name": "beta", "tags": ["z"], "other_fields": ["a"]},
            ]
        )
    )

    forest, _attrs, _render_specs, _out = qp.execute_query(
        f'read_json "{data_file}", group_by_tags_fixed "a" --field=other_fields'
    )

    members = _query_group_members(forest)
    assert members == {
        "a": [{"name": "beta", "tags": ["z"], "other_fields": ["a"]}],
        "<others>": [{"name": "alpha", "tags": ["a"], "other_fields": ["x"]}],
    }


# -- filter_tags ---------------------------------------------------------------


def test_filter_tags_include_only():
    """Without '-' prefixes the item must carry all listed tags."""
    assert filter_tags({"tags": ["a", "b"]}, ["a", "b"]) is True
    assert filter_tags({"tags": ["a"]}, ["a", "b"]) is False
    assert filter_tags({"tags": ["a", "b", "c"]}, ["a", "b"]) is True
    assert filter_tags({"tags": []}, ["a"]) is False


def test_filter_tags_exclude_only():
    """A '-tag' condition forbids the tag; other tags are irrelevant."""
    assert filter_tags({"tags": ["a"]}, ["-b"]) is True
    assert filter_tags({"tags": ["b"]}, ["-b"]) is False
    assert filter_tags({"tags": ["b", "c"]}, ["-b"]) is False
    assert filter_tags({"tags": []}, ["-b"]) is True


def test_filter_tags_include_and_exclude():
    """`a -b c` keeps items with a and c, without b."""
    assert filter_tags({"tags": ["a", "c"]}, ["a", "-b", "c"]) is True
    assert filter_tags({"tags": ["a", "b", "c"]}, ["a", "-b", "c"]) is False
    assert filter_tags({"tags": ["a"]}, ["a", "-b", "c"]) is False
    assert filter_tags({"tags": ["a", "c", "x", "y"]}, ["a", "-b", "c"]) is True


def test_filter_tags_extra_tags_do_not_matter():
    """Items may carry additional tags beyond the required ones."""
    assert filter_tags({"tags": ["a", "extra"]}, ["a"]) is True


def test_filter_tags_no_other_tags():
    """_no-other-tags requires the item tag set to be exactly the required set."""
    assert filter_tags({"tags": ["a", "b"]}, ["a", "b", "_no-other-tags"]) is True
    assert filter_tags({"tags": ["a", "b", "c"]}, ["a", "b", "_no-other-tags"]) is False
    assert filter_tags({"tags": ["a"]}, ["a", "b", "_no-other-tags"]) is False
    assert filter_tags({"tags": []}, ["_no-other-tags"]) is True
    assert filter_tags({"tags": ["a"]}, ["_no-other-tags"]) is False
    # Without the marker extra tags still do not matter.
    assert filter_tags({"tags": ["a", "b", "c"]}, ["a", "b"]) is True


def test_filter_tags_no_other_tags_with_exclusion():
    """_no-other-tags combines with exclusion conditions."""
    assert filter_tags({"tags": ["a", "b"]}, ["a", "-b", "_no-other-tags"]) is False
    assert filter_tags({"tags": ["a"]}, ["a", "-b", "_no-other-tags"]) is True


def test_filter_tags_dollar_no_other_tags():
    """$no-other-tags requires the item tag set to be exactly the required set."""
    assert filter_tags({"tags": ["alice"]}, ["alice", NO_OTHER_TAGS_TAG]) is True
    assert filter_tags({"tags": ["alice", "bob"]}, ["alice", NO_OTHER_TAGS_TAG]) is False
    assert filter_tags({"tags": ["alice"]}, ["alice", "bob", NO_OTHER_TAGS_TAG]) is False
    assert filter_tags({"tags": []}, [NO_OTHER_TAGS_TAG]) is True
    assert filter_tags({"tags": ["a"]}, [NO_OTHER_TAGS_TAG]) is False
    # Without the marker extra tags still do not matter.
    assert filter_tags({"tags": ["alice", "bob"]}, ["alice"]) is True


def test_filter_tags_no_other_tags_spellings_are_equivalent():
    """`$no-other-tags` and the older `_no-other-tags` mean the same condition."""
    for marker in (NO_OTHER_TAGS_TAG, "_no-other-tags"):
        assert filter_tags({"tags": ["a", "b"]}, ["a", "b", marker]) is True
        assert filter_tags({"tags": ["a", "b", "c"]}, ["a", "b", marker]) is False
        assert filter_tags({"tags": []}, [marker]) is True
        assert filter_tags({"tags": ["a"]}, [marker]) is False


def test_filter_tags_custom_field():
    """The field parameter selects which item field holds the tags."""
    assert filter_tags({"other_fields": ["a"]}, ["a"], field="other_fields") is True
    assert filter_tags({"other_fields": ["a"]}, ["-a"], field="other_fields") is False
    assert filter_tags({"tags": ["a"], "other_fields": ["x"]}, ["a"], field="other_fields") is False


def test_filter_tags_empty_conditions_keep_everything():
    """No conditions means every item passes (including untagged ones)."""
    assert filter_tags({"tags": ["a"]}, []) is True
    assert filter_tags({"tags": []}, []) is True


def test_filter_tags_query_include_and_exclude(make_ctx, tmp_path):
    """End-to-end query: read_json + vararg filter_tags with exclusion."""
    ctx = make_ctx()
    qp = make_qp(ctx)
    register_tools_from_module(ctx, udan.plugins_tools_examples.plugins_json.__name__, verbose=False)
    register_tools_from_module(ctx, plugins_tags.__name__, verbose=False)

    data_file = tmp_path / "items.json"
    data_file.write_text(
        json.dumps(
            [
                {"name": "alpha", "tags": ["a", "c"]},
                {"name": "beta", "tags": ["a", "b", "c"]},
                {"name": "gamma", "tags": ["a"]},
                {"name": "delta", "tags": ["c"]},
            ]
        )
    )

    forest, _attrs, _render_specs, _out = qp.execute_query(f'read_json "{data_file}", filter_tags a -b c')

    items = list(forest.items)
    assert items == [
        {"name": "alpha", "tags": ["a", "c"]},
    ]


def test_filter_tags_query_no_other_tags(make_ctx, tmp_path):
    """End-to-end: the quoted "$no-other-tags" marker reaches filter_tags as one argument."""
    ctx = make_ctx()
    qp = make_qp(ctx)
    register_tools_from_module(ctx, udan.plugins_tools_examples.plugins_json.__name__, verbose=False)
    register_tools_from_module(ctx, plugins_tags.__name__, verbose=False)

    data_file = tmp_path / "items.json"
    data_file.write_text(
        json.dumps(
            [
                {"name": "solo", "tags": ["alice"]},
                {"name": "extra", "tags": ["alice", "bob"]},
                {"name": "untagged", "tags": []},
                {"name": "other", "tags": ["bob"]},
            ]
        )
    )

    forest, _attrs, _render_specs, _out = qp.execute_query(
        f'read_json "{data_file}", filter_tags "alice" "$no-other-tags"'
    )
    assert list(forest.items) == [{"name": "solo", "tags": ["alice"]}]

    forest, _attrs, _render_specs, _out = qp.execute_query(f'read_json "{data_file}", filter_tags "$no-other-tags"')
    assert list(forest.items) == [{"name": "untagged", "tags": []}]


# -- has_tag ---------------------------------------------------------------


def test_has_tag_with_org_item():
    """has_tag works on OrgItem objects."""

    item = OrgItem(
        title="Test item",
        level=2,
        tags=["python", "test"],
        date="01.01.23-00:00:00",
        content="Test content",
    )

    assert has_tag(item, "python") is True
    assert has_tag(item, "test") is True

    assert has_tag(item, "other") is False
    assert has_tag(item, "python-test") is False


def test_has_tag_with_dict():
    """has_tag works on dict items."""

    assert has_tag({"title": "Test", "tags": ["python", "test"]}, "python") is True
    assert has_tag({"title": "Test", "tags": ["python", "test"]}, "other") is False

    assert has_tag({"title": "Test", "tags": []}, "python") is False
    assert has_tag({"title": "Test"}, "python") is False


def test_has_tag_with_object_attribute():
    """has_tag reads the tags attribute off any object, not just OrgItem."""
    item = SimpleNamespace(tags=["a", "b"])

    assert has_tag(item, "a") is True
    assert has_tag(item, "c") is False
    assert has_tag(SimpleNamespace(), "a") is False


def test_has_tag_custom_field():
    """The field parameter selects which item field holds the tags."""

    assert has_tag({"other_fields": ["a"]}, "a", field="other_fields") is True
    assert has_tag({"other_fields": ["a"]}, "b", field="other_fields") is False
    # When a custom field is given, the default "tags" field is ignored.
    assert has_tag({"tags": ["a"], "other_fields": ["b"]}, "a", field="other_fields") is False


def test_has_tag_query(make_ctx, tmp_path):
    """End-to-end query: has_tag filters items of any inserter."""
    ctx = make_ctx()
    qp = make_qp(ctx)
    register_tools_from_module(ctx, udan.plugins_tools_examples.plugins_json.__name__, verbose=False)
    register_tools_from_module(ctx, plugins_tags.__name__, verbose=False)

    data_file = tmp_path / "items.json"
    data_file.write_text(
        json.dumps(
            [
                {"name": "alpha", "tags": ["a", "b"]},
                {"name": "beta", "tags": ["b"]},
                {"name": "gamma", "tags": []},
            ]
        )
    )

    forest, _attrs, _render_specs, _out = qp.execute_query(f'read_json "{data_file}", has_tag a')

    assert list(forest.items) == [{"name": "alpha", "tags": ["a", "b"]}]


# -- show_tags_tree ------------------------------------------------------------


def test_tags_tree_item_render():

    assert tags_tree_item({"name": "fruit", "frequency": 6}) == "- fruit :: (6)"
    assert tags_tree_item({"name": "sweet", "frequency": 5}, indent="  ") == "  - sweet :: (5)"
    assert tags_tree_item({"name": "x"}) == "- x :: (0)"


def test_show_tags_tree_default_render_on_fruits_query(make_ctx):
    """The supported render shows tag names and frequencies, nested by depth."""
    ctx = make_ctx()
    qp = make_qp(ctx)
    register_tools_from_module(ctx, plugins_demo.__name__, verbose=False)
    register_tools_from_module(ctx, plugins_fruits.__name__, verbose=False)
    register_tools_from_module(ctx, plugins_tags.__name__, verbose=False)

    _forest, _attrs, _render_specs, out = qp.execute_query("fruits, show_tags_tree")

    lines = out.strip().split("\n")
    assert lines == [
        "- fruit :: (6)",
        "  - sweet :: (5)",
        "  - tropical :: (3)",
        "  - fresh :: (1)",
        "  - citrus :: (1)",
        "- sweet :: (6)",
        "  - fruit :: (5)",
        "  - fresh :: (2)",
        "  - tropical :: (2)",
        "  - citrus :: (1)",
        "  - berry :: (1)",
        "- fresh :: (4)",
        "  - berry :: (3)",
        "  - sweet :: (2)",
        "  - fruit :: (1)",
        "- tropical :: (3)",
        "  - fruit :: (3)",
        "  - sweet :: (2)",
        "- berry :: (3)",
        "  - fresh :: (3)",
        "  - sweet :: (1)",
        "- citrus :: (1)",
        "  - fruit :: (1)",
        "  - sweet :: (1)",
    ]


def test_show_tags_tree_example():
    """Level 0 holds all tags by frequency; level 1 holds co-occurring tags."""
    nodes = [
        _node(["a", "b"]),
        _node(["a", "b"]),
        _node(["c"]),
    ]
    # a=2, b=2, c=1; a co-occurs with b (2x); b co-occurs with a (2x); c alone.
    pairs = show_tags_tree(nodes)

    assert pairs == [
        (0, {"name": "a", "frequency": 2}),
        (1, {"name": "b", "frequency": 2}),
        (0, {"name": "b", "frequency": 2}),
        (1, {"name": "a", "frequency": 2}),
        (0, {"name": "c", "frequency": 1}),
    ]


def test_show_tags_tree_ordering_by_frequency():
    """Both levels are ordered by descending frequency (insertion order on ties)."""
    nodes = [
        _node(["x", "y"]),
        _node(["x"]),
        _node(["x"]),
        _node(["z"]),
        _node(["z"]),
    ]
    # x=3, y=1, z=2; x co-occurs with y (1x); y with x (1x); z alone.
    pairs = show_tags_tree(nodes)

    assert pairs == [
        (0, {"name": "x", "frequency": 3}),
        (1, {"name": "y", "frequency": 1}),
        (0, {"name": "z", "frequency": 2}),
        (0, {"name": "y", "frequency": 1}),
        (1, {"name": "x", "frequency": 1}),
    ]


def test_show_tags_tree_custom_field():
    """The field parameter selects which item field holds the tags."""
    nodes = [SimpleNamespace(item={"other_fields": ["a", "b"]})]
    pairs = show_tags_tree(nodes, field="other_fields")

    assert pairs == [
        (0, {"name": "a", "frequency": 1}),
        (1, {"name": "b", "frequency": 1}),
        (0, {"name": "b", "frequency": 1}),
        (1, {"name": "a", "frequency": 1}),
    ]


def test_show_tags_tree_untagged_items_produce_empty_tree():
    assert show_tags_tree([_node([]), _node([])]) == []


def test_show_tags_tree_on_fruits_query(make_ctx):
    """End-to-end query: fruits inserter + show_tags_tree builds the co-occurrence tree."""
    ctx = make_ctx()
    qp = make_qp(ctx)
    register_tools_from_module(ctx, plugins_demo.__name__, verbose=False)
    register_tools_from_module(ctx, plugins_fruits.__name__, verbose=False)
    register_tools_from_module(ctx, plugins_tags.__name__, verbose=False)

    forest, _attrs, _render_specs, _out = qp.execute_query("fruits, show_tags_tree")

    pairs = list(zip(forest.depths, forest.items))
    # fruit=6, sweet=6, fresh=4, tropical=3, berry=3, citrus=1 (ties keep first-seen order).
    assert pairs == [
        (0, {"name": "fruit", "frequency": 6}),
        (1, {"name": "sweet", "frequency": 5}),
        (1, {"name": "tropical", "frequency": 3}),
        (1, {"name": "fresh", "frequency": 1}),
        (1, {"name": "citrus", "frequency": 1}),
        (0, {"name": "sweet", "frequency": 6}),
        (1, {"name": "fruit", "frequency": 5}),
        (1, {"name": "fresh", "frequency": 2}),
        (1, {"name": "tropical", "frequency": 2}),
        (1, {"name": "citrus", "frequency": 1}),
        (1, {"name": "berry", "frequency": 1}),
        (0, {"name": "fresh", "frequency": 4}),
        (1, {"name": "berry", "frequency": 3}),
        (1, {"name": "sweet", "frequency": 2}),
        (1, {"name": "fruit", "frequency": 1}),
        (0, {"name": "tropical", "frequency": 3}),
        (1, {"name": "fruit", "frequency": 3}),
        (1, {"name": "sweet", "frequency": 2}),
        (0, {"name": "berry", "frequency": 3}),
        (1, {"name": "fresh", "frequency": 3}),
        (1, {"name": "sweet", "frequency": 1}),
        (0, {"name": "citrus", "frequency": 1}),
        (1, {"name": "fruit", "frequency": 1}),
        (1, {"name": "sweet", "frequency": 1}),
    ]
