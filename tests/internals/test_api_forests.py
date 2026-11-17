from udan.core.api_forests import Forest, Node
from udan.core.api_type_system import ForestTypeDescriptor
from udan.core_tools_loading.api_types import TypeDescriptor

FOREST = Forest(
    depths=[0, 1, 1, 0, 1, 2],
    items=["a", "b1", "b2", "c", "d", "e"],
)
NODE = Node(
    item="forest",
    children=[
        Node(item="a", children=[Node(item="b1"), Node(item="b2")]),
        Node(item="c", children=[Node(item="d", children=[Node(item="e")])]),
    ],
)
TYPED_FOREST = Forest(
    depths=[0, 1],
    items=["a", "b"],
    types=ForestTypeDescriptor(depths=[TypeDescriptor(name="int"), TypeDescriptor(name="str")]),
)
TYPED_NODE = Node(
    item="forest",
    children=[Node(item="a"), Node(item="b")],
    types=TYPED_FOREST.types,
)


def test_simple():
    forest = NODE.convert_to_forest()
    assert forest == FOREST

    node = forest.convert_to_node()
    assert node == NODE


def test_convert_forest_to_node_carries_types():
    node = TYPED_FOREST.convert_to_node()

    assert node.types == TYPED_FOREST.types


def test_convert_forest_to_node_empty_forest_keeps_types():
    forest = Forest(depths=[], items=[], types=TYPED_FOREST.types)

    assert forest.convert_to_node().types == TYPED_FOREST.types


def test_convert_node_to_forest_carries_types():
    forest = TYPED_NODE.convert_to_forest()

    assert forest.types == TYPED_NODE.types


def test_types_survive_the_round_trip():
    assert TYPED_FOREST.convert_to_node().convert_to_forest() == TYPED_FOREST
    assert TYPED_NODE.convert_to_forest().convert_to_node() == TYPED_NODE
