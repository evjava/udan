"""Item-type contract on tool metadata.

`item_type` / `output_type` are promoted from meta to typed fields, validated against the
tool kind at load time, and exposed by `help_list`. The optional semantic
siblings (`output_semantic` for operators, `item_semantic` for renders) carry the domain
meaning the structural type does not state. Renders carry no promoted contract: their meta
`shape` is the render shape ("item"/"children"), and `item_type`/`item_semantic`
stay in meta.
"""

from pathlib import Path
from typing import Any

import pytest

from tests.plugins_test_kinds import CheckKindService
from udan.core.api_attributes import ATTRIBUTE, AttributeMetadata
from udan.core.api_item_types import declared_item_type, fits_chain
from udan.core.api_operators import OperatorMetadata
from udan.core_tools_loading.impl_tool_kinds import ToolKindsRegistry
from udan.core_tools_loading.impl_tools_loader import ToolsLoader
from udan.core_tools_loading.impl_utils_tools_loader import convert_tool_to_metadata
from udan.operator.plugins_operator_extender import EXTENDER
from udan.operator.plugins_operator_filter import FILTER
from udan.operator.plugins_operator_grouper import GROUPER
from udan.operator.plugins_operator_inserter import INSERTER
from udan.operator.plugins_operator_mapper import MAPPER
from udan.operator.plugins_operator_replacer import REPLACER
from udan.operator.plugins_operator_sorter import SORTER
from udan.plugins_tools_core import plugins_help
from udan.plugins_tools_demo import plugins_demo, plugins_fruits
from udan.renders import plugins_renders
from udan.renders.api_renders import RENDER

# The kinds the vocabulary holds: the core's (attribute, render), the test package's
# own, and the operator kinds - all of them plugin kinds, instantiated beside their
# packages. A conversion tests the rules kinds carry, so it needs a vocabulary holding
# them (the container's component in production, filled from the core services and the
# loaded plugins).
BUILTIN_KINDS: tuple = (
    ATTRIBUTE,
    RENDER,
    *CheckKindService.KINDS,
    INSERTER,
    FILTER,
    EXTENDER,
    GROUPER,
    SORTER,
    MAPPER,
    REPLACER,
)


def _builtin_kinds() -> ToolKindsRegistry:
    kinds = ToolKindsRegistry()
    for kind in BUILTIN_KINDS:
        kinds.register(kind)
    return kinds


def _op(item: int) -> int:
    """Operator used as the conversion target."""
    return item


def _convert_fn(fn, name: str, meta: dict):
    """Convert a hand-made tool schema for the given function with the given meta."""
    tool = {
        "name": name,
        "description": f"{name} description.",
        "meta": meta,
        "parameters": {"properties": {}, "required": [], "type": "object"},
        "output_schema": {"type": "object", "properties": {}},
    }
    return convert_tool_to_metadata(fn, tool, None, _builtin_kinds())


def _convert(name: str, meta: dict):
    """Convert a hand-made tool schema with the given meta to tool metadata."""
    return _convert_fn(_op, name, meta)


def _load_demo_metadatas() -> dict:
    loader = ToolsLoader(cache_dir=None, use_cache=False, kinds=_builtin_kinds())
    return {m.name: m for m, _ in loader.load_from_module(plugins_demo)}


def _load_fruits_metadatas() -> dict:
    loader = ToolsLoader(cache_dir=None, use_cache=False, kinds=_builtin_kinds())
    return {m.name: m for m, _ in loader.load_from_module(plugins_fruits)}


# ============ promotion to typed fields ============


def test_operator_item_types_promoted():
    metadata = _convert("demo_ext", {"tool_type": "extender", "item_type": "int", "output_type": "str"})

    assert isinstance(metadata, OperatorMetadata)
    assert metadata.item_type == "int"
    assert metadata.output_type == "str"
    # keys stay in meta as well, like the other promoted fields (is_nested)
    assert metadata.meta["item_type"] == "int"


def test_inserter_has_no_item_type():
    metadata = _convert("demo_ins", {"tool_type": "inserter", "output_type": "dict"})

    assert metadata.output_type == "dict"
    assert metadata.item_type is None


def test_attribute_item_type_promoted():
    metadata = _convert("calc_age", {"attribute_type": "simple", "item_type": "ast_chunk"})

    assert isinstance(metadata, AttributeMetadata)
    assert metadata.item_type == "ast_chunk"


def test_loaded_demo_operators_carry_item_types():
    metadatas = _load_demo_metadatas()

    fruits = _load_fruits_metadatas()["insert_fruits"]
    assert fruits.output_type == "dict"
    assert fruits.output_semantic == "fruit"
    assert fruits.item_type is None

    ext = metadatas["extend_multiply"]
    assert ext.item_type == "int"
    assert ext.output_type == "int"
    assert ext.output_semantic is None

    grp = metadatas["group_by_modulo"]
    assert grp.item_type == "int"
    assert grp.output_type is None
    assert grp.output_semantic is None


# ============ kind <-> key validation ============


def test_inserter_rejects_item_type():
    with pytest.raises(ValueError, match="item_type"):
        _convert("bad_ins", {"tool_type": "inserter", "item_type": "int", "output_type": "int"})


def test_consumer_rejects_output_type():
    for tool_type in ("filter", "sorter", "grouper"):
        with pytest.raises(ValueError, match="output_type"):
            _convert(
                f"bad_{tool_type}",
                {"tool_type": tool_type, "item_type": "dict", "output_type": "dict"},
            )


def test_extender_requires_output_type():
    with pytest.raises(ValueError, match="output_type"):
        _convert("bad_ext", {"tool_type": "extender", "item_type": "int"})


def test_extender_output_semantic_without_output_type_rejected():
    with pytest.raises(ValueError, match="output_type"):
        _convert("bad_ext", {"tool_type": "extender", "item_type": "int", "output_semantic": "fruit"})


# ============ output semantic ============


def test_operator_output_semantic_promoted():
    metadata = _convert("demo_ins", {"tool_type": "inserter", "output_type": "dict", "output_semantic": "fruit"})

    assert metadata.output_type == "dict"
    assert metadata.output_semantic == "fruit"
    assert metadata.meta["output_semantic"] == "fruit"


def test_output_semantic_optional():
    metadata = _convert("demo_ins", {"tool_type": "inserter", "output_type": "dict"})

    assert metadata.output_semantic is None
    assert "output_semantic" not in metadata.meta


def test_output_semantic_allowed_where_output_type_is():
    for tool_type in ("inserter", "extender", "mapper", "replacer"):
        meta = {"tool_type": tool_type, "output_semantic": "fruit"}
        # extenders must declare output_type, the semantic rides on it
        if tool_type == "extender":
            meta["output_type"] = "dict"
        metadata = _convert(f"demo_{tool_type}", meta)

        assert metadata.output_semantic == "fruit"


def test_consumer_rejects_output_semantic():
    for tool_type in ("filter", "sorter", "grouper"):
        with pytest.raises(ValueError, match="output_semantic"):
            _convert(
                f"bad_{tool_type}",
                {"tool_type": tool_type, "item_type": "dict", "output_semantic": "fruit"},
            )


def test_render_item_semantic_stays_in_meta():
    metadata = _convert("render_demo", {"tool_type": "render", "item_type": "dict", "item_semantic": "CommitInfo"})

    assert metadata.meta["item_type"] == "dict"
    assert metadata.meta["item_semantic"] == "CommitInfo"
    assert metadata.item_type is None
    assert metadata.output_type is None
    assert metadata.output_semantic is None


def test_render_has_no_promoted_item_contract():
    metadata = _convert("render_demo", {"tool_type": "render", "item_type": "dict", "shape": "children"})

    # the shape stays in meta `shape`; the contract is meta `item_type`, never
    # promoted (renders are OperatorMetadata instances, but the promotion is for the
    # item-consuming kinds)
    assert metadata.item_type is None
    assert metadata.meta["shape"] == "children"
    assert metadata.meta["item_type"] == "dict"


# ============ item type derived from the 'item' parameter ============


def _render_dict(item: dict, indent: str = "") -> str:
    """Render whose item parameter declares dict."""
    return str(item)


def _render_union(item: str | Path) -> str:
    """Render whose item parameter declares a union."""
    return str(item)


def _render_any(item: Any) -> str:
    """Render whose item parameter declares Any (the Item alias)."""
    return str(item)


def _render_unannotated(item) -> str:
    """Render whose item parameter has no annotation."""
    return str(item)


def test_render_item_type_derived_from_annotation():
    metadata = _convert_fn(_render_dict, "render_derived", {"tool_type": "render"})

    assert metadata.meta["item_type"] == "dict"
    assert metadata.item_type is None


def test_render_item_type_derived_from_union_annotation():
    metadata = _convert_fn(_render_union, "render_union", {"tool_type": "render"})

    assert metadata.meta["item_type"] == "str|Path"


def test_render_any_item_type_derived_as_any():
    metadata = _convert_fn(_render_any, "render_any", {"tool_type": "render"})

    assert metadata.meta["item_type"] == "any"


def test_render_without_annotation_stays_undeclared():
    metadata = _convert_fn(_render_unannotated, "render_unannotated", {"tool_type": "render"})

    assert "item_type" not in metadata.meta


def test_render_declared_item_type_wins_over_annotation():
    metadata = _convert_fn(_render_dict, "render_declared", {"tool_type": "render", "item_type": "OrgNote"})

    assert metadata.meta["item_type"] == "OrgNote"


def test_operator_declared_item_type_is_promoted_and_kept_in_meta():
    """A declared item contract is promoted to the field and stays in meta."""
    metadata = _convert("demo_filter", {"tool_type": "filter", "item_type": "int"})

    assert metadata.item_type == "int"
    assert metadata.meta["item_type"] == "int"


# ============ item type derived from the 'item' parameter ============


def _attr_str(item: str) -> str:
    """Attribute whose item parameter declares str."""
    return item


def test_attribute_item_type_derived_from_annotation():
    metadata = _convert_fn(_attr_str, "attr_derived", {"attribute_type": "simple"})

    assert isinstance(metadata, AttributeMetadata)
    assert metadata.item_type == "str"
    assert metadata.meta["item_type"] == "str"


def test_attribute_declared_item_type_wins_over_annotation():
    metadata = _convert_fn(_attr_str, "attr_declared", {"attribute_type": "simple", "item_type": "ast_chunk"})

    assert isinstance(metadata, AttributeMetadata)
    assert metadata.item_type == "ast_chunk"


def test_attribute_any_item_derived_as_any():
    metadata = _convert_fn(_render_any, "attr_any", {"attribute_type": "simple"})

    assert isinstance(metadata, AttributeMetadata)
    assert metadata.item_type == "any"


def test_kind_item_type_derived_from_annotation():
    """Kinds with item_type keys get their item contract from the annotation too."""
    metadata = _convert_fn(_attr_str, "validator_derived", {"tool_type": "test_validator"})

    assert metadata.meta["item_type"] == "str"


def test_kind_declared_item_type_wins_over_annotation():
    metadata = _convert_fn(
        _attr_str,
        "validator_declared",
        {"tool_type": "test_validator", "item_type": "CsvRow"},
    )

    assert metadata.meta["item_type"] == "CsvRow"


def test_operator_item_type_derived_from_annotation():
    metadata = _convert_fn(_attr_str, "filter_derived", {"tool_type": "filter"})

    assert metadata.item_type == "str"


def test_operator_any_meta_yields_to_annotation():
    """meta item_type "any" says nothing: the annotation decides (git.untracked case)."""
    metadata = _convert_fn(
        _render_union, "ext_derived", {"tool_type": "extender", "item_type": "any", "output_type": "str|Path"}
    )

    assert metadata.item_type == "str|Path"


def test_operator_declared_item_type_wins_over_annotation():
    metadata = _convert_fn(_attr_str, "filter_declared", {"tool_type": "filter", "item_type": "int"})

    assert metadata.item_type == "int"


def test_inserter_item_annotation_not_derived():
    """Inserters consume no items: no item_type, even with an annotated item parameter."""
    metadata = _convert_fn(_attr_str, "ins_derived", {"tool_type": "inserter", "output_type": "int"})

    assert metadata.item_type is None
    assert "item_type" not in metadata.meta


def test_kind_without_item_contract_declares_its_derived_type_in_meta():
    """A kind the vocabulary holds no contract for still reports its item type.

    A tool declared under a kind name nothing registered (a plugin naming a
    kind that lives in another package) builds as a bare kind: no contract keys, so
    nothing is promoted and the metadata is a default OperatorMetadata. The type its
    `item` annotation carries is in meta then, and that is what fits_chain reads -
    a bare kind is not a kind with no opinion about items.
    """
    metadata = _convert_fn(_attr_str, "bare_kind", {"tool_type": "sample", "sample_type": "simple"})

    assert metadata.tool_type.item_type_keys == ()
    assert metadata.item_type is None
    assert declared_item_type(metadata) == "str"
    assert not fits_chain(metadata, ["int"])


# ============ help listing ============


def test_help_list_shows_item_types(make_ctx):
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_help, plugins_renders)
    rows = {row["name"]: row for row in plugins_help.help_list(registry=ctx.registry)}

    fruits = rows["fruits.insert_fruits"]
    assert fruits["output_type"] == "dict"
    assert "item_type" not in fruits
    assert "item_type" not in fruits

    ext = rows["demo.extend_multiply"]
    assert ext["item_type"] == "int"
    assert ext["output_type"] == "int"

    grp = rows["demo.group_by_modulo"]
    assert grp["item_type"] == "int"
    assert "output_type" not in grp


def test_help_list_render_has_no_item_type(make_ctx):
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_help, plugins_renders)
    rows = plugins_help.help_list(registry=ctx.registry)

    render_rows = [row for row in rows if row["type"] == "render"]
    assert render_rows, "expected renders in the unfiltered listing"
    # renders carry no promoted item contract, so their rows show none
    assert all("item_type" not in row for row in render_rows)
    # the kinds that do consume items declare it
    assert any("item_type" in row for row in rows)
