"""Tests for attribute calculation and storage."""

import pytest

from tests import plugins_test
from tests.conftest import make_qp
from udan.attributes import plugins_operators_attribute
from udan.attributes.api_attribute_storage import AttributeStorageAPI
from udan.core.api_attributes import (
    ATTRIBUTE,
    ATTRIBUTE_TYPE_COLUMN,
    AttributeDescriptor,
    AttributeMetadata,
)
from udan.core_tools_loading.api_types import Group, TypeDescriptor
from udan.plugins_tools_core import plugins_system
from udan.plugins_tools_demo import plugins_demo, plugins_fruits
from udan.plugins_tools_examples import plugins_builtins
from udan.renders import plugins_renders

atd = AttributeDescriptor.create


def test_attributes_simple(make_ctx):
    """Test that simple attributes are calculated correctly.

    Uses internal API to check attribute storage state.
    """
    ctx = make_ctx(
        plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_system, plugins_test
    )
    qp = make_qp(ctx)
    af, *_ = qp.execute_query("insert_test_numbers, modulo --k=2")
    at_d = atd("modulo", {"k": 2})
    assert af.items == [0, 1, 2]
    # Filter out internal attributes (like 'origin') that are automatically
    # added
    storage = ctx.container.get(AttributeStorageAPI)
    filtered_attrs = {k: v for k, v in storage.attributes.items() if k.name not in ("origin", "render")}
    assert filtered_attrs == {at_d: {0: "0", 1: "1", 2: "0"}}


def test_group_by_attr(make_ctx):
    """Test grouping by attribute using execute_query.

    Uses modulo_2 attribute which doesn't require parameters,
    allowing query syntax usage.
    """
    # Import Group type for comparison
    ctx = make_ctx(
        plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_system, plugins_test
    )
    qp = make_qp(ctx)

    # Use execute_query with query syntax
    forest, attrs, render_specs, out = qp.execute_query("insert_test_numbers, group_by_attribute modulo_2")

    # Check the grouped result - should now have Group items instead of strings
    items = forest.items
    assert len(items) == 5  # 2 groups + 3 items

    # First item is a Group with key='0'
    assert isinstance(items[0], Group)
    assert items[0].key == "0"

    # Next are the grouped children
    assert items[1] == 0
    assert items[2] == 2

    # Second item is a Group with key='1'
    assert isinstance(items[3], Group)
    assert items[3].key == "1"

    # Last item is the grouped child
    assert items[4] == 1

    assert forest.depths == [0, 1, 1, 0, 1]


def test_pfc_attribute(make_ctx):
    """Test PFC attribute returns nutritional dict for fruits.

    Uses internal API to check attribute storage state.
    """
    ctx = make_ctx(
        plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_system, plugins_test
    )
    qp = make_qp(ctx)
    af, *_ = qp.execute_query("insert_fruits, pfc")
    at_d = atd("pfc", {})

    # Should have 10 fruits (9 regular + 1 mythical ambrosia)
    assert len(af.items) == 10

    # Check PFC attribute was calculated for all 10 fruits
    storage = ctx.container.get(AttributeStorageAPI)
    assert at_d in storage._unhashable
    pfc_values = storage._unhashable[at_d]
    # All fruits get PFC calculated (ambrosia gets None)
    assert len(pfc_values) == 10

    # Check apple PFC values
    apple = af.items[0]
    apple_pfc = storage.get_attr_value(at_d, apple)
    assert apple_pfc == {"proteins": 0.3, "fats": 0.2, "carbs": 14.0}

    # Check ambrosia (mythical fruit) has no PFC data
    ambrosia = af.items[9]
    ambrosia_pfc = storage.get_attr_value(at_d, ambrosia)
    assert ambrosia_pfc is None  # Mythical fruit not in PFC data


def test_composite_attribute_pfc_proteins(make_ctx):
    """Test composite attribute pfc.proteins extracts proteins field.

    Uses internal API to check attribute storage state.
    """
    ctx = make_ctx(
        plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_system, plugins_test
    )
    qp = make_qp(ctx)
    af, *_ = qp.execute_query("insert_fruits, pfc.proteins")
    # Create composite attribute descriptor for pfc.proteins
    at_d = atd("pfc.proteins", {})

    # Should have 10 fruits (9 regular + 1 mythical)
    assert len(af.items) == 10

    # Check composite attribute was calculated for all 10 fruits
    # Composite attributes are stored in unhashable dict
    storage = ctx.container.get(AttributeStorageAPI)
    assert at_d in storage._unhashable
    proteins_values = storage._unhashable[at_d]
    # All fruits get proteins calculated (ambrosia gets None)
    assert len(proteins_values) == 10

    # Check apple proteins value
    apple = af.items[0]
    apple_proteins = storage.get_attr_value(at_d, apple)
    assert apple_proteins == 0.3

    # Check orange proteins value
    orange = af.items[1]
    orange_proteins = storage.get_attr_value(at_d, orange)
    assert orange_proteins == 0.9

    # Check ambrosia (mythical fruit) has no proteins data
    ambrosia = af.items[9]
    ambrosia_proteins = storage.get_attr_value(at_d, ambrosia)
    assert ambrosia_proteins is None  # Mythical fruit not in PFC data


def test_composite_attribute_pfc_carbs(make_ctx):
    """Test composite attribute pfc.carbs extracts carbs field.

    Uses internal API to check attribute storage state.
    """
    ctx = make_ctx(
        plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_system, plugins_test
    )
    qp = make_qp(ctx)
    af, *_ = qp.execute_query("insert_fruits, pfc.carbs")
    at_d = atd("pfc.carbs", {})

    # Should have 10 fruits
    assert len(af.items) == 10

    # Check banana carbs value
    storage = ctx.container.get(AttributeStorageAPI)
    banana = af.items[2]
    banana_carbs = storage.get_attr_value(at_d, banana)
    assert banana_carbs == 23.0

    # Check ambrosia (mythical fruit) has no carbs data
    ambrosia = af.items[9]
    ambrosia_carbs = storage.get_attr_value(at_d, ambrosia)
    assert ambrosia_carbs is None  # Mythical fruit not in PFC data


def test_attribute_without_item_parameter_raises_error(make_ctx):
    """Test that attributes without 'item' parameter raise error during registration.

    This tests the registration API directly and cannot use execute_query.
    """
    # Create metadata for an invalid attribute (missing 'item' parameter)
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_system)
    invalid_attr_metadata = AttributeMetadata(
        name="invalid_attr_no_item",
        description="Invalid attribute without item parameter",
        tags=[],
        meta={"attribute_type": "simple"},
        parameters={"properties": {"wrong_param": {"type": "string"}}, "required": [], "type": "object"},
        output_schema={"properties": {"result": {"type": "string"}}, "required": ["result"], "type": "object"},
        fn_path="test_module.invalid_attr",
        attribute_type="simple",
    )

    # Mock function (won't be called, just needed for registration)
    # Invalid attribute - missing 'item' parameter
    def invalid_attr_fn(wrong_param: str) -> str:
        return wrong_param

    # Should raise ValueError when trying to register
    with pytest.raises(ValueError, match=r"invalid_attr_no_item.*\(attribute\) must have an 'item' parameter"):
        ctx._register_metadata(invalid_attr_metadata, invalid_attr_fn)


def test_group_by_attribute_introspection(make_ctx):
    """Test that `group_by_attribute ?` shows at_d parameter correctly.

    This test uses execute_query as required.
    """
    # Execute introspection query for group_by_attribute
    ctx = make_ctx(
        plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_system, plugins_test
    )
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query("group_by_attribute ?")

    # Should show pretty formatted nested forest structure
    lines = out.strip().split("\n")

    # Level 0: tool name and type with source reference (line number may shift)
    assert lines[0].startswith("- attributes_ops.group_by_attribute (grouper) ["), f"Unexpected intro line: {lines[0]}"

    # Level 1: should show the at_d parameter
    assert lines[1] == "  - at_d: any", "Should show at_d parameter"
    assert lines[2] == "  - value: string", "Should show value parameter"


def test_attribute_descriptor_as_dict_key():
    """Test that AttributeDescriptor works as dictionary key via __hash__ and __eq__.

    This tests the __hash__ and __eq__ methods that were added to support
    using AttributeDescriptor instances as dictionary keys for attribute storage.
    """
    # Create descriptors with same identity and args
    desc1 = atd("modulo", {"k": 2})
    desc2 = atd("modulo", {"k": 2})
    desc3 = atd("modulo", {"k": 3})
    desc4 = atd("pfc", {})

    # Test equality: same identity and args should be equal
    assert desc1 == desc2, "Descriptors with same identity and args should be equal"
    assert desc1 != desc3, "Descriptors with different args should not be equal"
    assert desc1 != desc4, "Descriptors with different identity should not be equal"

    # Test hash: equal descriptors should have same hash
    assert hash(desc1) == hash(desc2), "Equal descriptors should have same hash"
    assert hash(desc1) != hash(desc3), "Different descriptors should (likely) have different hashes"

    # Test usage as dictionary key
    storage = {}
    storage[desc1] = "value1"
    storage[desc3] = "value3"
    storage[desc4] = "value4"

    # desc2 should be able to retrieve the value set by desc1 (they're equal)
    assert storage[desc2] == "value1", "Equal descriptor should retrieve same value"
    assert storage[desc3] == "value3"
    assert storage[desc4] == "value4"

    # Test cache_key method
    # cache_key() uses dict string representation, not tuple
    assert desc1.cache_key() == "modulo:{'k': 2}", "cache_key should serialize identity and sorted args"
    assert desc2.cache_key() == desc1.cache_key(), "Equal descriptors should have same cache_key"
    assert desc3.cache_key() == "modulo:{'k': 3}"
    assert desc4.cache_key() == "pfc:", "Empty args produce empty string after colon"

    # Test that descriptors with same args in different order are equal
    desc5 = atd("multi", {"a": 1, "b": 2})
    desc6 = atd("multi", {"b": 2, "a": 1})
    assert desc5 == desc6, "Descriptors with same args in different order should be equal"
    assert hash(desc5) == hash(desc6), "Descriptors with same args in different order should have same hash"
    assert desc5.cache_key() == desc6.cache_key(), "cache_key should be order-independent"


def test_double_attr_with_fruit_cost(make_ctx):
    """Test double(fruit_cost): passes fruit_cost attribute value to double."""
    ctx = make_ctx(
        plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_system, plugins_test
    )
    qp = make_qp(ctx)
    af, *_ = qp.execute_query("insert_fruits, double(fruit_cost)")
    at_d = atd("double", {"value": atd("fruit_cost", {})})

    storage = ctx.container.get(AttributeStorageAPI)
    apple = af.items[0]  # fruit_cost=1.20
    assert storage.get_attr_value(at_d, apple) == pytest.approx(1.20 * 2)

    strawberry = af.items[3]  # fruit_cost=3.50
    assert storage.get_attr_value(at_d, strawberry) == pytest.approx(3.50 * 2)


def test_double_attr_with_div_3(make_ctx):
    """Test double(div_3): passes div_3 attribute value to double on numbers."""
    ctx = make_ctx(
        plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_system, plugins_test
    )
    qp = make_qp(ctx)
    af, *_ = qp.execute_query("insert_test_numbers, double(div_3)")
    at_d = atd("double", {"value": atd("div_3", {})})

    storage = ctx.container.get(AttributeStorageAPI)
    # div_3 for 0->0, 1->1, 2->2; double -> 0, 2, 4
    assert storage.get_attr_value(at_d, 0) == 0
    assert storage.get_attr_value(at_d, 1) == 2
    assert storage.get_attr_value(at_d, 2) == 4


def test_double_attr_with_is_even(make_ctx):
    """Test double(is_even): passes is_even (bool) attribute value to double."""
    ctx = make_ctx(
        plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_system, plugins_test
    )
    qp = make_qp(ctx)
    af, *_ = qp.execute_query("insert_test_numbers, double(is_even)")
    at_d = atd("double", {"value": atd("is_even", {})})

    storage = ctx.container.get(AttributeStorageAPI)
    # is_even for 0->True(1), 1->False(0), 2->True(1); double -> 2, 0, 2
    assert storage.get_attr_value(at_d, 0) == 2
    assert storage.get_attr_value(at_d, 1) == 0
    assert storage.get_attr_value(at_d, 2) == 2


def test_double_without_argument_doubles_item(make_ctx):
    """Test double with no argument: doubles the numeric item itself.

    Used to return None (the item parameter was ignored), so the attribute
    produced no values at all.
    """
    ctx = make_ctx(
        plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_system, plugins_test
    )
    qp = make_qp(ctx)
    af, *_ = qp.execute_query("range 3, extend_by_attribute double")
    at_d = atd("double", {})

    storage = ctx.container.get(AttributeStorageAPI)
    # 0, 1, 2 doubled -> 0, 2, 4
    assert storage.get_attr_value(at_d, 0) == 0
    assert storage.get_attr_value(at_d, 1) == 2
    assert storage.get_attr_value(at_d, 2) == 4
    assert [item for _, item in af.as_pairs()] == [0, 0, 1, 2, 2, 4]


def test_double_with_literal_argument_forbidden(make_ctx):
    """Test double 2 / double(2): bare literals are rejected, not silently used.

    A literal used to be bound as the string "2" and doubled as text
    ("2" * 2 -> "22"); ints crashed in tool resolution.
    """
    ctx = make_ctx(
        plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_system, plugins_test
    )
    qp = make_qp(ctx)

    _, _, _, out = qp.execute_query("range 3, double 2")
    assert "double expects an attribute name, got unresolvable literal '2'" in out

    _, _, _, out = qp.execute_query("range 3, double(2)")
    assert "Expected argument with name=value to be string, found: 2" in out


def test_cattr_dict_field_times_attr(make_ctx):
    """Test cattr with dict field * registered attribute."""
    ctx = make_ctx(
        plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_system, plugins_test
    )
    qp = make_qp(ctx)
    af, *_ = qp.execute_query("insert_fruits, cattr 'calories * fruit_cost'")
    at_d = atd("calories * fruit_cost", {})

    storage = ctx.container.get(AttributeStorageAPI)
    apple = af.items[0]  # calories=52, fruit_cost=1.20
    assert storage.get_attr_value(at_d, apple) == pytest.approx(52 * 1.20)

    strawberry = af.items[3]  # calories=32, fruit_cost=3.50
    assert storage.get_attr_value(at_d, strawberry) == pytest.approx(32 * 3.50)


def test_cattr_dict_field_plus_dict_field(make_ctx):
    """Test cattr with dict field + dict field."""
    ctx = make_ctx(
        plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_system, plugins_test
    )
    qp = make_qp(ctx)
    af, *_ = qp.execute_query("insert_fruits, cattr 'calories + calories'")
    at_d = atd("calories + calories", {})

    storage = ctx.container.get(AttributeStorageAPI)
    apple = af.items[0]  # calories=52
    assert storage.get_attr_value(at_d, apple) == 104


def test_cattr_attr_times_attr(make_ctx):
    """Test cattr with registered attribute * registered attribute."""
    ctx = make_ctx(
        plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_system, plugins_test
    )
    qp = make_qp(ctx)
    af, *_ = qp.execute_query("insert_fruits, fruit_cost, cattr 'fruit_cost * fruit_cost'")
    at_d = atd("fruit_cost * fruit_cost", {})

    storage = ctx.container.get(AttributeStorageAPI)
    apple = af.items[0]  # fruit_cost=1.20
    assert storage.get_attr_value(at_d, apple) == pytest.approx(1.20 * 1.20)


def test_cattr_with_name(make_ctx):
    """Test cattr with --name parameter for custom attribute name."""
    ctx = make_ctx(
        plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_system, plugins_test
    )
    qp = make_qp(ctx)
    af, *_ = qp.execute_query("insert_fruits, cattr 'calories * fruit_cost' --name=total")
    at_d = atd("total", {})

    storage = ctx.container.get(AttributeStorageAPI)
    apple = af.items[0]  # calories=52, fruit_cost=1.20
    assert storage.get_attr_value(at_d, apple) == pytest.approx(52 * 1.20)


def test_cattr_it_token(make_ctx):
    """Test cattr `it` token: expressions can reference the item itself."""
    ctx = make_ctx(
        plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_system, plugins_test
    )
    qp = make_qp(ctx)
    af, *_ = qp.execute_query("range 6, cattr '(it + 1) % 2 == 1' --name=next_is_odd")
    at_d = atd("next_is_odd", {})

    storage = ctx.container.get(AttributeStorageAPI)
    # is_odd of it + 1: 0->True, 1->False, 2->True, ...
    assert af.items == [0, 1, 2, 3, 4, 5]
    assert [storage.get_attr_value(at_d, item) for item in af.items] == [True, False, True, False, True, False]


def test_cattr_is_a_column_defining_attribute(make_ctx):
    """cattr is an attribute whose chain items define columns - not an operator.

    It used to be an extender operator returning [] whose only effect was side
    effects on the attribute context; the model is now a column factory resolved
    at query resolution into the column's own AttributeDescriptor. The column
    capability is the attribute type, not a cattr-specific flag.
    """
    ctx = make_ctx(
        plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_system, plugins_test
    )
    metadata = ctx.registry.get_metadata("cattr")

    assert isinstance(metadata, AttributeMetadata)
    assert metadata.tool_type == ATTRIBUTE
    assert metadata.attribute_type == ATTRIBUTE_TYPE_COLUMN


def test_cattr_column_resolves_to_named_descriptor(make_ctx):
    """A cattr chain item resolves to the column's own descriptor, not an operator."""
    ctx = make_ctx(
        plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_system, plugins_test
    )
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query("range 3, cattr 'is_odd(it + 1)' --name=n1")

    assert attrs == [atd("n1", {})]
    assert forest.types.depths == [TypeDescriptor(name="int", requested=[atd("n1", {})])]
    assert forest.types.flattened_requested() == [atd("n1", {})]


def test_extra_positional_arg_raises(make_ctx):
    """Test that a positional argument with no parameter to bind to raises a clear error.

    Previously the extra argument was silently dropped by zip in
    DescriptorFactory._bind_with_schema_ext and the attribute was calculated
    as if the argument wasn't there.
    """
    ctx = make_ctx(
        plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_system, plugins_test
    )
    qp = make_qp(ctx)
    forest, _, _, out = qp.execute_query("insert_test_numbers, is_odd(5)")

    assert forest is None, "Query with an unbindable positional argument must fail"
    assert "no parameter to bind" in out
    assert "'is_odd' takes 0 positional argument(s)" in out


def test_named_arg_in_parens(make_ctx):
    """Test key=value named-argument syntax inside parentheses: modulo(k=3).

    Previously 'k=3' was bound as the literal string value 'k=3' of k.
    """
    ctx = make_ctx(
        plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_system, plugins_test
    )
    qp = make_qp(ctx)
    af, *_ = qp.execute_query("insert_test_numbers, modulo(k=3)")
    at_d = atd("modulo", {"k": 3})

    storage = ctx.container.get(AttributeStorageAPI)
    assert af.items == [0, 1, 2]
    assert storage.get_attr_value(at_d, 0) == "0"
    assert storage.get_attr_value(at_d, 2) == "2"


def test_cattr_call_registered_attribute(make_ctx):
    """Test cattr calling a registered attribute: 'double(div_3)' applies the function.

    Previously the call target was token-substituted by its value and the
    expression degenerated to None.
    """
    ctx = make_ctx(
        plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_system, plugins_test
    )
    qp = make_qp(ctx)
    af, *_ = qp.execute_query("insert_test_numbers, cattr 'double(div_3)' --name=d6")
    at_d = atd("d6", {})

    storage = ctx.container.get(AttributeStorageAPI)
    # div_3 for 0,1,2 -> 0,1,2; doubled -> 0,2,4 (same as the double(div_3) attribute form)
    assert [storage.get_attr_value(at_d, item) for item in af.items] == [0, 2, 4]


def test_cattr_call_with_it_transform(make_ctx):
    """Test cattr call with a single leftover argument overriding item.

    'is_odd(it + 1)' applies the is_odd attribute to a transform of the item.
    """
    ctx = make_ctx(
        plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_system, plugins_test
    )
    qp = make_qp(ctx)
    af, *_ = qp.execute_query("range 6, cattr 'is_odd(it + 1)' --name=next_is_odd")
    at_d = atd("next_is_odd", {})

    storage = ctx.container.get(AttributeStorageAPI)
    assert [storage.get_attr_value(at_d, item) for item in af.items] == [True, False, True, False, True, False]


def test_cattr_unknown_function_fails_loudly(make_ctx):
    """Test that calling a name that is not a registered attribute raises.

    Previously the NameError was swallowed and the column silently stored None,
    so a formula referencing an attribute missing from the environment rendered
    an empty column.
    """
    ctx = make_ctx(plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_system)  # no is_odd here
    qp = make_qp(ctx)
    forest, _, _, out = qp.execute_query("insert_fruits, cattr 'is_odd(calories)' --name=odd_cal")

    assert forest is None
    assert "cattr: unknown function 'is_odd'" in out
    assert "not a registered attribute" in out


def test_cattr_named_column_renders_in_table(make_ctx):
    """The documented column example renders through :table without test plugins.

    Regression: in the CLI environment (no plugins_test) the column was silently
    empty; is_odd lives in plugins_demo.
    """
    ctx = make_ctx(plugins_demo, plugins_builtins, plugins_operators_attribute, plugins_renders, plugins_system)
    qp = make_qp(ctx)
    _, _, _, out = qp.execute_query("range 3, cattr 'is_odd(it + 1)' --name=n1, :table item n1")

    expected_lines = [
        "| item | n1    |",
        "|------+-------|",
        "|    0 | True  |",
        "|    1 | False |",
        "|    2 | True  |",
    ]
    assert "\n".join(expected_lines) == out


def test_value_attr_composition_target(make_ctx):
    """Test a value-shaped attribute (no `item` param) as a composition target.

    extract_tags(text: str) receives the text_label output as its `text`
    argument; values are still stored per item.
    """
    ctx = make_ctx(
        plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_system, plugins_test
    )
    qp = make_qp(ctx)
    af, *_ = qp.execute_query("insert_test_numbers, extract_tags(text_label)")
    at_d = atd("extract_tags", {"text": atd("text_label", {})})

    storage = ctx.container.get(AttributeStorageAPI)
    assert af.items == [0, 1, 2]
    assert [storage.get_attr_value(at_d, item) for item in af.items] == [
        ["aa", "0", "bb"],
        ["aa", "1", "bb"],
        ["aa", "2", "bb"],
    ]


def test_value_attr_composition_chain(make_ctx):
    """Test a chain of value-shaped attributes: count_tags(extract_tags(text_label))."""
    ctx = make_ctx(
        plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_system, plugins_test
    )
    qp = make_qp(ctx)
    af, *_ = qp.execute_query("insert_test_numbers, count_tags(extract_tags(text_label))")
    at_d = atd("count_tags", {"tags": atd("extract_tags", {"text": atd("text_label", {})})})

    storage = ctx.container.get(AttributeStorageAPI)
    assert [storage.get_attr_value(at_d, item) for item in af.items] == [3, 3, 3]


def test_cattr_value_attr_chain(make_ctx):
    """Test cattr resolving a value-shaped attribute chain with a list argument.

    The inner call returns a list whose repr contains commas; the argument
    splitter must not split inside it.
    """
    ctx = make_ctx(
        plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_system, plugins_test
    )
    qp = make_qp(ctx)
    af, *_ = qp.execute_query("insert_test_numbers, cattr 'count_tags(extract_tags(text_label))'")
    at_d = atd("count_tags(extract_tags(text_label))", {})

    storage = ctx.container.get(AttributeStorageAPI)
    assert [storage.get_attr_value(at_d, item) for item in af.items] == [3, 3, 3]


def test_cattr_builtin_call_in_formula(make_ctx):
    """Test whitelisted builtin calls (str, len, ...) inside a formula."""
    ctx = make_ctx(
        plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_system, plugins_test
    )
    qp = make_qp(ctx)
    af, *_ = qp.execute_query("insert_fruits, cattr 'str(calories) + \"_\" + name' --name=label")
    at_d = atd("label", {})

    storage = ctx.container.get(AttributeStorageAPI)
    assert storage.get_attr_value(at_d, af.items[0]) == "52_apple"


def test_cattr_builtin_as_call_argument(make_ctx):
    """Test a builtin call as a composition argument: double(len(name))."""
    ctx = make_ctx(
        plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_system, plugins_test
    )
    qp = make_qp(ctx)
    af, *_ = qp.execute_query("insert_fruits, cattr 'double(len(name))' --name=x2")
    at_d = atd("x2", {})

    storage = ctx.container.get(AttributeStorageAPI)
    assert storage.get_attr_value(at_d, af.items[0]) == len(af.items[0]["name"]) * 2


def test_cattr_string_literals_and_word_boundaries(make_ctx):
    """Test that literals holding field names stay literals, not substitutions."""
    ctx = make_ctx(
        plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_system, plugins_test
    )
    qp = make_qp(ctx)
    af, *_ = qp.execute_query("insert_fruits, cattr '\"calories\" + name' --name=concat")
    at_d = atd("concat", {})

    storage = ctx.container.get(AttributeStorageAPI)
    assert storage.get_attr_value(at_d, af.items[0]) == "caloriesapple"


def test_cattr_missing_field_falls_back_to_zero(make_ctx):
    """Test that a missing field resolves to 0 instead of breaking the expression."""
    ctx = make_ctx(
        plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_system, plugins_test
    )
    qp = make_qp(ctx)
    af, *_ = qp.execute_query("insert_fruits, cattr 'calories + missing_field' --name=plus_missing")
    at_d = atd("plus_missing", {})

    storage = ctx.container.get(AttributeStorageAPI)
    assert storage.get_attr_value(at_d, af.items[0]) == 52


def test_cattr_malformed_expression_stores_none(make_ctx):
    """Test that a malformed expression stores None instead of failing the query."""
    ctx = make_ctx(
        plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_system, plugins_test
    )
    qp = make_qp(ctx)
    af, *_ = qp.execute_query("insert_fruits, cattr 'calories +' --name=broken")
    at_d = atd("broken", {})

    storage = ctx.container.get(AttributeStorageAPI)
    assert storage.get_attr_value(at_d, af.items[0]) is None


def test_cattr_unbindable_positional_fails_loudly(make_ctx):
    """Test that a call with more arguments than parameters to bind raises."""
    ctx = make_ctx(
        plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_system, plugins_test
    )
    qp = make_qp(ctx)
    forest, _, _, out = qp.execute_query("insert_test_numbers, cattr 'is_odd(it + 1, 2)'")

    assert forest is None
    assert "cannot bind" in out


def test_cattr_call_failure_fails_loudly(make_ctx):
    """Test that a failing attribute call raises with the call text in the message."""
    ctx = make_ctx(
        plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_system, plugins_test
    )
    qp = make_qp(ctx)
    forest, _, _, out = qp.execute_query("insert_test_numbers, cattr \"is_odd('not-a-number')\"")

    assert forest is None
    assert "cattr: call" in out


def test_cattr_nested_chain_with_arithmetic(make_ctx):
    """Test a composition chain nested inside an arithmetic expression."""
    ctx = make_ctx(
        plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_system, plugins_test
    )
    qp = make_qp(ctx)
    af, *_ = qp.execute_query("insert_test_numbers, cattr 'count_tags(extract_tags(text_label)) * 10' --name=score")
    at_d = atd("score", {})

    storage = ctx.container.get(AttributeStorageAPI)
    assert [storage.get_attr_value(at_d, item) for item in af.items] == [30, 30, 30]


# --- Named cattr columns (spreadsheet-style references) ---


def test_cattr_named_column_reference_in_second_cattr(make_ctx):
    """A named column resolves in later formulas of the same query.

    Previously 'n1' in the second formula folded silently to 0 and n2 was all False.
    """
    ctx = make_ctx(
        plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_system, plugins_test
    )
    qp = make_qp(ctx)
    af, *_ = qp.execute_query("range 6, cattr 'is_odd(it + 1)' --name=n1, cattr 'n1 == True' --name=n2")

    storage = ctx.container.get(AttributeStorageAPI)
    expected = [True, False, True, False, True, False]
    assert [storage.get_attr_value(atd("n1", {}), item) for item in af.items] == expected
    assert [storage.get_attr_value(atd("n2", {}), item) for item in af.items] == expected


def test_cattr_named_column_registered_with_formula(make_ctx):
    """A named column becomes a registry member carrying its formula in metadata."""
    ctx = make_ctx(
        plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_system, plugins_test
    )
    qp = make_qp(ctx)
    qp.execute_query("range 6, cattr 'is_odd(it + 1)' --name=n1")

    metadata = ctx.registry.get_metadata("n1")
    assert isinstance(metadata, AttributeMetadata)
    assert metadata.meta.get("cattr_expr") == "is_odd(it + 1)"


def test_cattr_named_column_lazy_in_fresh_query(make_ctx):
    """A named column re-evaluates lazily for items another query materialized later.

    Query 1 materializes n1 for items 0-5; query 2 references n1 over 0-9, so
    items 6-9 must be computed through the registered lazy evaluator.
    """
    ctx = make_ctx(
        plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_system, plugins_test
    )
    qp = make_qp(ctx)
    qp.execute_query("range 6, cattr 'is_odd(it + 1)' --name=n1")

    storage = ctx.container.get(AttributeStorageAPI)
    assert storage.get_attr_value(atd("n1", {}), 8) is None  # not materialized yet

    af, *_ = qp.execute_query("range 10, cattr 'n1' --name=copy")
    expected = [True, False, True, False, True, False, True, False, True, False]
    assert [storage.get_attr_value(atd("copy", {}), item) for item in af.items] == expected
    # The lazy evaluation materialized the missing items
    assert storage.get_attr_value(atd("n1", {}), 8) is True


def test_cattr_named_column_chain(make_ctx):
    """Columns compose: each column may reference the previous ones."""
    ctx = make_ctx(
        plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_system, plugins_test
    )
    qp = make_qp(ctx)
    af, *_ = qp.execute_query(
        "range 6, cattr 'is_odd(it)' --name=a, cattr 'a and it > 2' --name=b, cattr 'not b' --name=c"
    )

    storage = ctx.container.get(AttributeStorageAPI)
    # a: odd items; b: odd and > 2; c: not b
    assert [storage.get_attr_value(atd("c", {}), item) for item in af.items] == [True, True, True, False, True, False]


def test_cattr_named_column_duplicate_in_same_query_raises(make_ctx):
    """Two different formulas for one name within a query is a conflict."""
    ctx = make_ctx(
        plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_system, plugins_test
    )
    qp = make_qp(ctx)

    forest, _, _, out = qp.execute_query("range 6, cattr 'it * 2' --name=n1, cattr 'it * 3' --name=n1")
    assert forest is None
    assert "already taken" in out
    assert "it * 2" in out  # the conflicting formula is named in the error
    assert "Choose a different name" in out


def test_cattr_named_column_redefined_in_next_query(make_ctx):
    """A name claimed by an earlier query is free to redefine: names are query-local.

    Previously the redefinition failed with 'already taken', forcing a new column
    name for every formula iteration.
    """
    ctx = make_ctx(
        plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_system, plugins_test
    )
    qp = make_qp(ctx)
    qp.execute_query("range 6, cattr 'is_odd(it + 1)' --name=n1, cattr 'n1 == True' --name=n2")

    af, *_ = qp.execute_query("range 6, cattr 'is_odd(it + 1)' --name=n1, cattr 'n1 == False' --name=n2")

    storage = ctx.container.get(AttributeStorageAPI)
    # n2 flips: True where n1 is False
    assert [storage.get_attr_value(atd("n2", {}), item) for item in af.items] == [
        False,
        True,
        False,
        True,
        False,
        True,
    ]
    metadata = ctx.registry.get_metadata("n2")
    assert metadata.meta.get("cattr_expr") == "n1 == False"


def test_cattr_named_column_redefinition_drops_stale_values(make_ctx):
    """Redefining a column drops the previous formula's stored values.

    Items 3-5 are not recomputed by the redefining query; their old values must
    not be served for the new definition.
    """
    ctx = make_ctx(
        plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_system, plugins_test
    )
    qp = make_qp(ctx)
    qp.execute_query("range 6, cattr 'it * 2' --name=d")
    qp.execute_query("range 3, cattr 'it * 3' --name=d")

    storage = ctx.container.get(AttributeStorageAPI)
    at_d = atd("d", {})
    assert [storage.get_attr_value(at_d, item) for item in range(6)] == [0, 3, 6, None, None, None]


def test_cattr_named_column_same_formula_idempotent(make_ctx):
    """Re-running the identical definition is allowed (query re-runs must not break)."""
    ctx = make_ctx(
        plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_system, plugins_test
    )
    qp = make_qp(ctx)
    af1, *_ = qp.execute_query("range 6, cattr 'is_odd(it + 1)' --name=n1")
    af2, *_ = qp.execute_query("range 6, cattr 'is_odd(it + 1)' --name=n1")

    assert af2.items == af1.items
    storage = ctx.container.get(AttributeStorageAPI)
    assert [storage.get_attr_value(atd("n1", {}), item) for item in af2.items] == [
        True,
        False,
        True,
        False,
        True,
        False,
    ]


def test_cattr_named_column_collides_with_registered_raises(make_ctx):
    """A named column may not shadow an existing tool."""
    ctx = make_ctx(
        plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_system, plugins_test
    )
    qp = make_qp(ctx)
    forest, _, _, out = qp.execute_query("range 6, cattr 'it' --name=is_odd")

    assert forest is None
    assert "already taken" in out


def test_cattr_named_column_circular_reference_raises(make_ctx):
    """Mutually referencing columns fail loudly instead of hanging or folding to 0."""
    ctx = make_ctx(
        plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_system, plugins_test
    )
    qp = make_qp(ctx)
    forest, _, _, out = qp.execute_query(
        "range 6, cattr 'not y' --name=x, cattr 'not x' --name=y, cattr 'x and y' --name=z"
    )

    assert forest is None
    assert "circular reference" in out


def test_cattr_named_column_as_dependency_target(make_ctx):
    """A registered attribute can declare a dependency on a named cattr column."""
    ctx = make_ctx(
        plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_system, plugins_test
    )
    qp = make_qp(ctx)

    def get_flag(items):
        # The parser bakes dependency-parameter defaults into descriptor args
        # (AttrD[uses_n1_flag]{'n1_flag': None}), so look the value up by name
        storage = ctx.container.get(AttributeStorageAPI)
        return [
            next((vals.get(item) for at_d, vals in storage.attributes.items() if at_d.name == "uses_n1_flag"), None)
            for item in items
        ]

    af, *_ = qp.execute_query("range 6, cattr 'is_odd(it + 1)' --name=n1, uses_n1_flag")
    expected = [True, False, True, False, True, False]
    assert get_flag(af.items) == expected

    # Fresh query: the dependency resolves lazily through the registered evaluator
    af2, *_ = qp.execute_query("range 6, uses_n1_flag")
    assert get_flag(af2.items) == expected


def test_mutual_attribute_dependencies_raise(make_ctx):
    """Mutually dependent attributes fail loudly instead of recursing forever.

    The cycle guard lives inside the attribute runtime: a -> b -> a re-enters the
    same (attribute, item) pair and is rejected there.
    """
    ctx = make_ctx(
        plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_system, plugins_test
    )
    qp = make_qp(ctx)
    forest, _, _, out = qp.execute_query("range 6, mutual_a")

    assert forest is None
    assert "circular reference" in out
