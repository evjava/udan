"""Tests for the tools registry.

The registry accepts registrations at any time (plugins are loaded dynamically),
so its list getters must reflect every registration, including ones made after
the first read.
"""

import pytest

from tests.conftest import register_tools_from_module
from udan.core.api_attributes import ATTRIBUTE, AttributeMetadata
from udan.core_tools_loading.api_tools import ToolDescriptor
from udan.plugins_tools_core import plugins_help, plugins_system
from udan.plugins_tools_examples import plugins_json
from udan.renders import plugins_renders
from udan.renders.api_renders import RENDER

# Every kind object core publishes: the registry accepts any of them as a `kind` argument.
# Core declares no operator kind any more, so these are the attribute and the render.
ALL_CORE_KINDS = (ATTRIBUTE, RENDER)


def test_get_tools_sees_registration_after_first_read(make_ctx):
    ctx = make_ctx(plugins_renders)
    registry = ctx.registry
    registry.get_tools()

    register_tools_from_module(ctx, plugins_help.__name__)
    register_tools_from_module(ctx, plugins_system.__name__)

    names = registry.get_tools()
    assert "vars" in names
    assert "help" in names
    assert len(names) == len(registry.get_metadatas())


def test_get_tools_of_renders_sees_registration_after_first_read(make_ctx):
    ctx = make_ctx(plugins_renders)
    registry = ctx.registry
    registry.get_tools(kind=RENDER)

    register_tools_from_module(ctx, plugins_json.__name__)

    renders = registry.get_tools(kind=RENDER)
    assert "render_json" in renders
    assert "json" in renders


def test_get_tools_of_renders_stays_correct_after_non_render_registration(make_ctx):
    """A non-render registration drops the memoized name list, so renders stay accurate."""
    ctx = make_ctx(plugins_renders)
    registry = ctx.registry
    registry.get_tools(kind=RENDER)

    register_tools_from_module(ctx, plugins_system.__name__)

    renders = registry.get_tools(kind=RENDER)
    expected = sorted(key for key, m in registry.get_metadatas().items() if m.tool_type == "render")
    assert sorted(renders) == expected


def test_get_tools_filters_by_kind(make_ctx):
    registry = make_ctx(plugins_renders).registry

    renders = registry.get_tools(kind="render")

    expected = sorted(key for key, m in registry.get_metadatas().items() if m.tool_type == "render")
    assert sorted(renders) == expected


def test_get_tools_unknown_kind_raises(make_ctx):
    registry = make_ctx(plugins_renders).registry

    with pytest.raises(ValueError, match="Unknown tool kind: 'no-such-kind'"):
        registry.get_tools(kind="no-such-kind")


def test_get_tools_accepts_every_allowed_kind(make_ctx):
    registry = make_ctx(plugins_renders).registry

    for kind in ALL_CORE_KINDS:
        assert isinstance(registry.get_tools(kind.name), list)


def test_get_tools_returns_fresh_list(make_ctx):
    registry = make_ctx(plugins_renders).registry
    first = registry.get_tools()
    second = registry.get_tools()

    assert first == second
    assert first is not second

    first.append("mutated")
    assert "mutated" not in registry.get_tools()


def test_get_metadatas_filters_by_kind(make_ctx):
    registry = make_ctx(plugins_renders).registry

    render_metadatas = registry.get_metadatas(kind=RENDER)

    assert render_metadatas
    assert all(m.tool_type == RENDER for m in render_metadatas.values())
    assert set(render_metadatas) == set(registry.get_tools(kind=RENDER))


def test_get_metadatas_unknown_kind_returns_empty(make_ctx):
    """get_metadatas filters rather than validating, unlike get_tools."""
    registry = make_ctx(plugins_renders).registry

    assert registry.get_metadatas(kind="no-such-kind") == {}


# --- resolve: by descriptor, by name, and as a relation ---


def test_resolve_by_descriptor_returns_metadata_and_fn(make_ctx):
    registry = make_ctx(plugins_renders, plugins_system).registry
    op_d = ToolDescriptor.create("vars")

    binding = registry.resolve(op_d)

    assert binding.metadata.name == "vars"
    assert callable(binding.fn)


def test_resolve_by_name(make_ctx):
    registry = make_ctx(plugins_renders, plugins_system).registry

    binding = registry.resolve("vars")

    assert binding.metadata.name == "vars"
    assert callable(binding.fn)


def test_resolve_kind_mismatch_raises(make_ctx):
    """vars is an inserter, so asking for it as a parser fails on the kind check."""
    registry = make_ctx(plugins_renders, plugins_system).registry

    with pytest.raises(ValueError, match="is 'inserter', not 'parser'"):
        registry.resolve("vars", kind="parser")


def test_resolve_unknown_name_raises(make_ctx):
    registry = make_ctx(plugins_renders).registry

    with pytest.raises(ValueError, match="Not found tool"):
        registry.resolve("no_such_tool_xyz")


def test_resolve_render_falls_back_to_text_frontend(make_ctx):
    """A render without an html variant resolves to its text variant for html frontend."""
    registry = make_ctx(plugins_renders).registry

    fn_text = registry.resolve("raw", kind=RENDER, frontend="text").fn
    fn_html = registry.resolve("raw", kind=RENDER, frontend="html").fn

    assert fn_text is fn_html


def test_resolve_render_unknown_raises(make_ctx):
    registry = make_ctx(plugins_renders).registry

    with pytest.raises(ValueError, match="Not found tool"):
        registry.resolve("no_such_render_xyz", kind=RENDER)


def test_resolve_without_key_or_options_raises(make_ctx):
    registry = make_ctx(plugins_renders).registry

    with pytest.raises(ValueError, match="needs a name or a descriptor"):
        registry.resolve()


# --- the register-time signature rule ---
# The rule lives in the private _validate_signature, so these exercise it through
# the public register(), which is the only caller.


def _attribute_metadata(name: str) -> AttributeMetadata:
    return AttributeMetadata(
        name=name,
        description="",
        tags=[],
        meta={"attribute_type": "simple"},
        parameters={"properties": {}, "required": [], "type": "object"},
        output_schema={},
        tool_type=ATTRIBUTE,
        fn_path=f"tests.test_impl_tools_registry.{name}",
        attribute_type="simple",
    )


def test_register_accepts_attribute_with_item_parameter(make_ctx):
    registry = make_ctx(plugins_renders).registry

    def attr_with_item(item):
        return item

    registry._register(_attribute_metadata("attr_with_item"), attr_with_item)


def test_register_rejects_attribute_without_item(make_ctx):
    """The rule runs at register time, so a violating attribute fails to load."""
    registry = make_ctx(plugins_renders).registry

    with pytest.raises(ValueError, match="must have an 'item' parameter"):
        registry._register(_attribute_metadata("attr_no_item"), lambda values: values)


def test_register_skips_signature_rule_for_external_tools(make_ctx):
    """Tools registered without a source module have empty fn_path and a **kwargs signature, so are exempt."""
    registry = make_ctx(plugins_renders, plugins_system).registry
    external_metadata = registry.get_metadata("vars").model_copy(update={"fn_path": ""})

    registry._register(external_metadata, lambda **kwargs: None)
