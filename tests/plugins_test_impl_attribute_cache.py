from udan.core_tools_loading.api_annotated import annotated

DOMAIN = "test_impl_attribute_cache"


# This will be set by the test module
call_count = {"cache_key_attr": 0, "expensive_attr": 0, "simple_attr": 0, "slow_attr": 0, "node_attr": 0}


@annotated(meta={"tool_type": "inserter"})
def insert_test_numbers() -> list[int]:
    return [1, 2, 3, 1, 2, 3]


@annotated(meta={"attribute_type": "simple"})
def cache_key_attr(item: int) -> str:
    call_count["cache_key_attr"] += 1
    return f"key_{item}"


@annotated(meta={"attribute_type": "simple", "cache_attribute": "cache_key_attr"})
def expensive_attr(item: int) -> str:
    call_count["expensive_attr"] += 1
    return f"expensive_{item}"


@annotated(meta={"attribute_type": "simple"})
def simple_attr(item: int) -> str:
    call_count["simple_attr"] += 1
    return f"value_{item}"


@annotated(meta={"attribute_type": "simple", "cache_attribute": "cache_key_attr", "args": (("node", None),)})
def node_attr(item: int, node) -> str:
    call_count["node_attr"] += 1
    # The node type is part of the value: a cache miss that drops the node argument
    # would produce "NoneType" here instead of "Node"
    return f"node_{item}_{type(node).__name__}"
