"""Tests for the chain walk over loaded tool metadata.

The walk (udan.core.utils_chain) answers whether any descriptor of a resolved
chain belongs to a tool that declares a meta key. It takes the metadatas as data,
so these tests build the mapping and the node tree directly.
"""

from udan.core.api_constants import NODE_ROOT_ITEM, OVERRIDES_OUTPUT
from udan.core.api_forests import Node
from udan.core.utils_chain import chain_declares_meta
from udan.core_tools_loading.api_tools import ToolDescriptor, ToolMetadata


def _metadata(name: str, meta: dict | None = None) -> ToolMetadata:
    return ToolMetadata(
        name=name,
        meta=meta or {},
        parameters={"properties": {}},
        output_schema={},
        fn_path=f"tests.plugins_test.{name}",
    )


def test_declares_at_the_first_step():
    metadatas = {"help": _metadata("help", {OVERRIDES_OUTPUT: True})}
    chain = Node(item=NODE_ROOT_ITEM, children=[Node.leaf(ToolDescriptor(name="help"))])

    assert chain_declares_meta(metadatas, chain, OVERRIDES_OUTPUT) is True


def test_declares_deep_in_the_chain():
    metadatas = {"introspect_tool": _metadata("introspect_tool", {OVERRIDES_OUTPUT: True})}
    chain = Node(
        item=NODE_ROOT_ITEM,
        children=[
            Node.leaf(ToolDescriptor(name="range")),
            Node(
                item=ToolDescriptor(name="map"),
                children=[Node.leaf(ToolDescriptor(name="introspect_tool"))],
            ),
        ],
    )

    assert chain_declares_meta(metadatas, chain, OVERRIDES_OUTPUT) is True


def test_data_items_contribute_nothing():
    metadatas = {"help": _metadata("help")}
    chain = Node(item=NODE_ROOT_ITEM, children=[Node.leaf("3"), Node.leaf("literal")])

    assert chain_declares_meta(metadatas, chain, OVERRIDES_OUTPUT) is False


def test_unregistered_name_declares_nothing():
    metadatas = {"range": _metadata("range")}
    chain = Node(item=NODE_ROOT_ITEM, children=[Node.leaf(ToolDescriptor(name="no_such_tool"))])

    assert chain_declares_meta(metadatas, chain, OVERRIDES_OUTPUT) is False


def test_declared_falsy_value_declares_nothing():
    metadatas = {"map": _metadata("map", {OVERRIDES_OUTPUT: False})}
    chain = Node(item=NODE_ROOT_ITEM, children=[Node.leaf(ToolDescriptor(name="map"))])

    assert chain_declares_meta(metadatas, chain, OVERRIDES_OUTPUT) is False
