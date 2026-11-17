"""Tests for attribute dependencies mechanism.

This test verifies that attributes can depend on other attributes using
the dependencies metadata field.
"""

from tests.conftest import make_qp
from udan.attributes.api_attribute_runtime import AttributeRuntimeAPI
from udan.attributes.api_attribute_storage import AttributeStorageAPI
from udan.core.api_attributes import AttributeDescriptor
from udan.plugins_tools_demo import plugins_demo, plugins_fruits
from udan.renders import plugins_renders


def test_translate_ru_upper_basic(make_ctx):
    """Test that translate_ru attribute works correctly."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_renders)
    qp = make_qp(ctx)

    # Query with translate operator adds translate_ru attribute
    forest, attrs, render_specs, out = qp.execute_query("fruits, translate, :attr translate_ru")

    # Should have Russian translations (lowercase)
    assert "яблоко" in out, "Should have Russian 'apple' (lowercase)"
    assert "ананас" in out, "Should have Russian 'pineapple' (lowercase)"


def test_translate_ru_upper_with_dependencies(make_ctx):
    """Test that translate_ru_upper attribute depends on translate_ru and uppercases it."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_renders)
    qp = make_qp(ctx)

    # Get forest with translate operator (adds translate_ru to attrs)
    forest, attrs, render_specs, out = qp.execute_query("fruits, translate")

    # Add translate_ru_upper attribute to request list
    translate_upper_at_d = AttributeDescriptor.create("translate_ru_upper", args={})
    attrs.append(translate_upper_at_d)

    # Calculate the new attribute
    ctx.container.get(AttributeRuntimeAPI).calculate_attributes_in_forest(forest, attrs, ctx.create_exec_context())

    # Check that translate_ru_upper values are calculated correctly
    # Get actual items from forest
    forest_items = list(forest.items)

    # Find apple and check its translate_ru_upper value
    apple_item = next((item for item in forest_items if item.get("name") == "apple"), None)
    assert apple_item is not None, "Should find apple in forest"

    apple_value = ctx.container.get(AttributeStorageAPI).get_attr_value(translate_upper_at_d, apple_item)
    assert apple_value == "ЯБЛОКО", f"Apple should have uppercase Russian, got {apple_value}"


def test_translate_ru_upper_metadata(make_ctx):
    """Test that translate_ru_upper metadata has dependencies set correctly."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_renders)

    # Check that translate_ru_upper is registered
    assert "translate_ru_upper" in ctx.registry.get_tools(), "translate_ru_upper should be registered"

    # Get metadata
    metadata = ctx.registry.get_metadata("translate_ru_upper")
    assert metadata is not None, "translate_ru_upper metadata should exist"

    # Verify dependencies is set to ["translate_ru"] (list)
    assert metadata.dependencies == {"translate_ru": "translate_ru"}, "translate_ru_upper should depend on translate_ru"


def test_dependencies_resolves_automatically(make_ctx):
    """Test that dependent attribute is resolved automatically."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_renders)

    # Create attribute descriptor for translate_ru_upper
    at_d = AttributeDescriptor.create("translate_ru_upper", args={})

    # Get the attribute
    translate_attr = ctx.container.get(AttributeRuntimeAPI)._resolve_attribute(at_d)
    assert translate_attr is not None, "Should resolve translate_ru_upper attribute"

    # Check metadata has dependencies as list
    assert translate_attr.metadata.dependencies == {"translate_ru": "translate_ru"}, (
        "Attribute should depend on translate_ru"
    )


def test_translate_ru_upper_multiple_items(make_ctx):
    """Test that dependencies works correctly with multiple items."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_renders)
    qp = make_qp(ctx)

    # Get forest
    forest, attrs, render_specs, out = qp.execute_query("fruits, translate")

    # Add translate_ru_upper attribute
    translate_upper_at_d = AttributeDescriptor.create("translate_ru_upper", args={})
    attrs.append(translate_upper_at_d)

    # Calculate attributes
    ctx.container.get(AttributeRuntimeAPI).calculate_attributes_in_forest(forest, attrs, ctx.create_exec_context())

    # Check multiple items
    forest_items = list(forest.items)

    # Check apple, orange, banana
    for item in forest_items[:3]:
        name = item.get("name")
        value = ctx.container.get(AttributeStorageAPI).get_attr_value(translate_upper_at_d, item)

        if name == "apple":
            assert value == "ЯБЛОКО", f"Apple should be ЯБЛОКО, got {value}"
        elif name == "orange":
            assert value == "АПЕЛЬСИН", f"Orange should be АПЕЛЬСИН, got {value}"
        elif name == "banana":
            assert value == "БАНАН", f"Banana should be БАНАН, got {value}"


def test_dependency_chain(make_ctx):
    """Test that dependency A -> B works correctly.

    This tests that translate_ru_upper (B) depends on translate_ru (A),
    and both are calculated correctly.
    """
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_renders)

    # Create descriptors
    translate_at_d = AttributeDescriptor.create("translate_ru", args={})
    upper_at_d = AttributeDescriptor.create("translate_ru_upper", args={})

    # Get attributes
    translate_attr = ctx.container.get(AttributeRuntimeAPI)._resolve_attribute(translate_at_d)
    upper_attr = ctx.container.get(AttributeRuntimeAPI)._resolve_attribute(upper_at_d)

    assert translate_attr is not None, "Should resolve translate_ru"
    assert upper_attr is not None, "Should resolve translate_ru_upper"

    # Verify dependency relationship
    assert upper_attr.metadata.dependencies == {"translate_ru": "translate_ru"}, (
        "translate_ru_upper should depend on translate_ru"
    )


def test_dependencies_with_filter(make_ctx):
    """Test that dependencies works with filtering."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_renders)
    qp = make_qp(ctx)

    # Get forest with translate operator
    forest, attrs, render_specs, out = qp.execute_query("fruits, translate")

    # Add translate_ru_upper attribute to the request list
    translate_upper_at_d = AttributeDescriptor.create("translate_ru_upper", args={})
    attrs.append(translate_upper_at_d)

    # Calculate attributes
    ctx.container.get(AttributeRuntimeAPI).calculate_attributes_in_forest(forest, attrs, ctx.create_exec_context())

    # Check that red fruits (apple, strawberry, raspberry) have uppercase
    # Russian
    forest_items = list(forest.items)

    red_fruits_found = {"apple": False, "strawberry": False, "raspberry": False}
    for item in forest_items:
        name = item.get("name")
        color = item.get("color")
        value = ctx.container.get(AttributeStorageAPI).get_attr_value(translate_upper_at_d, item)

        if color == "red":
            if name == "apple":
                assert value == "ЯБЛОКО", "Apple should be ЯБЛОКО"
                red_fruits_found["apple"] = True
            elif name == "strawberry":
                assert value == "КЛУБНИКА", "Strawberry should be КЛУБНИКА"
                red_fruits_found["strawberry"] = True
            elif name == "raspberry":
                assert value == "МАЛИНА", "Raspberry should be МАЛИНА"
                red_fruits_found["raspberry"] = True

    # Verify we found all three red fruits
    assert all(red_fruits_found.values()), f"Should find all red fruits, found {red_fruits_found}"


def test_dependencies_none_handling(make_ctx):
    """Test that translate_ru_upper handles None from dependency gracefully."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_renders)
    qp = make_qp(ctx)

    # Get forest
    forest, attrs, render_specs, out = qp.execute_query("fruits")

    # Add translate_ru_upper attribute
    translate_upper_at_d = AttributeDescriptor.create("translate_ru_upper", args={})
    attrs.append(translate_upper_at_d)

    # Calculate attributes
    ctx.container.get(AttributeRuntimeAPI).calculate_attributes_in_forest(forest, attrs, ctx.create_exec_context())

    # Check ambrosia (no translation, should return None)
    forest_items = list(forest.items)
    ambrosia_item = next((item for item in forest_items if item.get("name") == "ambrosia"), None)

    if ambrosia_item:
        # ambrosia has no translation, so translate_ru returns None
        # translate_ru_upper should handle None gracefully and return None
        value = ctx.container.get(AttributeStorageAPI).get_attr_value(translate_upper_at_d, ambrosia_item)
        assert value is None, "Ambrosia should return None (no translation available)"


def test_both_attributes_together(make_ctx):
    """Test that both translate_ru and translate_ru_upper can be used together."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_renders)
    qp = make_qp(ctx)

    # Get forest with translate
    forest, attrs, render_specs, out = qp.execute_query("fruits, translate")

    # Both translate_ru and translate_ru_upper should be in attrs
    translate_at_d = AttributeDescriptor.create("translate_ru", args={})
    translate_upper_at_d = AttributeDescriptor.create("translate_ru_upper", args={})

    # Check that translate_ru is already in attrs (added by translate operator)
    assert any(attr.name == "translate_ru" for attr in attrs), "translate_ru should be in attrs"

    # Add translate_ru_upper
    attrs.append(translate_upper_at_d)

    # Calculate
    ctx.container.get(AttributeRuntimeAPI).calculate_attributes_in_forest(forest, attrs, ctx.create_exec_context())

    # Check that both attributes work
    forest_items = list(forest.items)
    apple_item = next((item for item in forest_items if item.get("name") == "apple"), None)

    assert apple_item is not None, "Should find apple"

    translate_value = ctx.container.get(AttributeStorageAPI).get_attr_value(translate_at_d, apple_item)
    upper_value = ctx.container.get(AttributeStorageAPI).get_attr_value(translate_upper_at_d, apple_item)

    assert translate_value == "яблоко", f"translate_ru should be lowercase, got {translate_value}"
    assert upper_value == "ЯБЛОКО", f"translate_ru_upper should be uppercase, got {upper_value}"


def test_dependencies_parameter_passed_correctly(make_ctx):
    """Test that dependency value is passed as parameter correctly."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_renders)
    qp = make_qp(ctx)

    # The translate_ru_upper function signature expects:
    # def translate_ru_upper(item: dict, translate_ru: str | None = None) ->
    # str | None

    # When calculated, it should receive translate_ru value as the
    # translate_ru parameter

    # Get forest
    forest, attrs, render_specs, out = qp.execute_query("fruits, translate")

    # Add translate_ru_upper attribute
    translate_upper_at_d = AttributeDescriptor.create("translate_ru_upper", args={})
    attrs.append(translate_upper_at_d)

    # Calculate
    ctx.container.get(AttributeRuntimeAPI).calculate_attributes_in_forest(forest, attrs, ctx.create_exec_context())

    # Verify the dependency was passed correctly by checking the value
    forest_items = list(forest.items)
    apple_item = next((item for item in forest_items if item.get("name") == "apple"), None)

    value = ctx.container.get(AttributeStorageAPI).get_attr_value(translate_upper_at_d, apple_item)
    assert value == "ЯБЛОКО", f"Dependency value should be passed and uppercased, got {value}"
