"""Tests for attribute caching using cache_attribute."""

import shutil
from pathlib import Path

import pytest

import tests.plugins_test_impl_attribute_cache
from tests.conftest import kinds_vocabulary, register_tools_from_module
from udan.attributes.api_attribute_cache import AttributeCacheAPI
from udan.attributes.api_attribute_runtime import AttributeRuntimeAPI
from udan.attributes.api_attribute_storage import AttributeStorageAPI
from udan.attributes.impl_attribute_runtime import AttributesContext
from udan.attributes.impl_attribute_storage import AttributeStorage
from udan.core.api_attributes import AttributeDescriptor
from udan.core.api_forests import Forest
from udan.core.api_operators import OperatorDescriptor
from udan.core.impl_debug_logger import DebugLogger
from udan.core.impl_exec_context import ExecContext
from udan.core.impl_ioc import create_udan_container
from udan.core.impl_udan_context import UdanContext
from udan.core_tools_loading.api_annotated import annotated
from udan.core_tools_loading.impl_tools_loader import _load_tool_metadata
from udan.operator.api_operator_engine import OperatorsEngineAPI

# Count calls to attribute functions
call_count = {"cache_key_attr": 0, "expensive_attr": 0, "simple_attr": 0, "slow_attr": 0, "node_attr": 0}


@pytest.fixture(autouse=True)
def reset_call_count():
    call_count["cache_key_attr"] = 0
    call_count["expensive_attr"] = 0
    call_count["simple_attr"] = 0
    call_count["slow_attr"] = 0
    call_count["node_attr"] = 0
    # Sync call_count to plugin module
    tests.plugins_test_impl_attribute_cache.call_count = call_count
    yield


def apply_and_calculate(ctx: UdanContext, items: list, attr_d: AttributeDescriptor) -> tuple[Forest, AttributeStorage]:
    """Helper to apply operators and calculate attributes."""
    if isinstance(items[0], int):
        opds = [OperatorDescriptor.create("insert_test_numbers")]
    else:
        raise ValueError("Only test numbers supported")

    forest = Forest.from_items(opds)
    exec_ctx = ExecContext(logger=DebugLogger(log_time=False))

    # Create attribute storage and context for operator application
    attribute_storage = AttributeStorage(attributes={})
    attr_context = AttributesContext(
        attribute_runtime=ctx.container.get(AttributeRuntimeAPI),
        attribute_storage=attribute_storage,
        requested_attributes=forest.types.flattened_requested(),
        ctx=exec_ctx,
    )

    forest_ext = _engine(ctx)._apply_operators_in_forest(forest, exec_ctx, attr_context)
    ctx.container.get(AttributeRuntimeAPI).calculate_attributes_in_forest(forest_ext, [attr_d], exec_ctx)
    return forest_ext, attribute_storage


def create_ctx_with_cache_dir(ctx: UdanContext, udan_cache_dir: Path) -> UdanContext:
    """Create a test UdanContext whose cache directory is udan_cache_dir.

    The fresh container brings a fresh AttributeStorage, so attribute values
    calculated by an earlier context are not visible to it. The attribute cache
    on disk is shared, which is what makes cached attributes serve their values
    from a previous context.

    Args:
        ctx: Base UdanContext to copy config from
        udan_cache_dir: Directory to use as udan_cache_dir

    Returns:
        New UdanContext sharing that cache directory
    """
    config = ctx.config.model_copy(
        update={
            "udan_cache_dir": str(udan_cache_dir),
        }
    )

    container = create_udan_container(config=config)
    ctx_obj = container.get(UdanContext)._with_plugins()
    ctx_obj.container = container
    return ctx_obj


def create_test_ctx(ctx: UdanContext, cache_path: str) -> UdanContext:
    """Create a test UdanContext with a temporary cache path.

    Args:
        ctx: Base UdanContext to copy config from
        cache_path: Cache path to use

    Returns:
        New UdanContext with isolated cache
    """
    # Use directory from cache_path as udan_cache_dir
    udan_cache_dir = Path(cache_path).parent
    # Clean the cache directory to ensure isolated cache
    cache_attrs_dir = udan_cache_dir / "attrs"
    if cache_attrs_dir.exists():
        shutil.rmtree(cache_attrs_dir)
    return create_ctx_with_cache_dir(ctx, udan_cache_dir)


def test_cacheable_attribute_uses_cache_key_attribute(make_ctx, tmp_path):
    """Test that cacheable attributes use cache_attribute for caching."""
    ctx = make_ctx()
    cache_path = str(tmp_path / "cache.json")
    test_ctx = create_test_ctx(ctx, cache_path)
    register_tools_from_module(test_ctx, tests.plugins_test_impl_attribute_cache.__name__)

    at_d = AttributeDescriptor.create("expensive_attr", args={})

    # First calculation: cache miss for all items
    apply_and_calculate(test_ctx, [1, 2, 3], at_d)
    storage = test_ctx.container.get(AttributeStorageAPI)
    assert storage.attributes[at_d][1] == "expensive_1"
    assert storage.attributes[at_d][2] == "expensive_2"
    assert storage.attributes[at_d][3] == "expensive_3"
    # Cache key attribute is calculated once per unique item
    assert call_count["cache_key_attr"] == 3
    # Expensive attr called once per unique item: the second pass over the
    # duplicated items is served by the entry the first pass stored
    assert call_count["expensive_attr"] == 3

    # Second calculation in a fresh context: same cache directory on disk, but
    # a fresh AttributeStorage, so the cache key attribute is recalculated while
    # the expensive attribute is served from the cache
    call_count["cache_key_attr"] = 0
    call_count["expensive_attr"] = 0
    test_ctx2 = create_ctx_with_cache_dir(ctx, Path(cache_path).parent)
    register_tools_from_module(test_ctx2, tests.plugins_test_impl_attribute_cache.__name__)
    apply_and_calculate(test_ctx2, [1, 2, 3], at_d)
    storage2 = test_ctx2.container.get(AttributeRuntimeAPI).attribute_storage
    assert storage2.attributes[at_d][1] == "expensive_1"
    assert storage2.attributes[at_d][2] == "expensive_2"
    assert storage2.attributes[at_d][3] == "expensive_3"
    assert call_count["cache_key_attr"] == 3  # Recalculated for the new storage
    assert call_count["expensive_attr"] == 0  # Served by the cache of the first calculation


def test_cacheable_attribute_with_node_argument(make_ctx, tmp_path):
    """A cached attribute whose function takes `node` computes on a cache miss.

    The miss is the attribute's own calculate, so a cached attribute receives
    everything a non-cached one receives - the node argument included.
    """
    ctx = make_ctx()
    cache_path = str(tmp_path / "cache.json")
    test_ctx = create_test_ctx(ctx, cache_path)
    register_tools_from_module(test_ctx, tests.plugins_test_impl_attribute_cache.__name__)

    at_d = AttributeDescriptor.create("node_attr", args={"node": None})

    # Cold cache: calculated, node argument included
    apply_and_calculate(test_ctx, [1, 2, 3], at_d)
    storage = test_ctx.container.get(AttributeStorageAPI)
    assert storage.attributes[at_d][1] == "node_1_Node"
    assert storage.attributes[at_d][2] == "node_2_Node"
    assert storage.attributes[at_d][3] == "node_3_Node"
    assert call_count["node_attr"] == 3

    # Warm cache: served from the cache, not recomputed
    call_count["node_attr"] = 0
    apply_and_calculate(test_ctx, [1, 2, 3], at_d)
    assert test_ctx.container.get(AttributeStorageAPI).attributes[at_d][1] == "node_1_Node"
    assert call_count["node_attr"] == 0


def test_non_cacheable_attribute_always_calculates(make_ctx, tmp_path):
    """Test that non-cacheable attributes always calculate."""
    ctx = make_ctx()
    cache_path = str(tmp_path / "cache.json")
    test_ctx = create_test_ctx(ctx, cache_path)
    register_tools_from_module(test_ctx, tests.plugins_test_impl_attribute_cache.__name__)

    at_d = AttributeDescriptor.create("simple_attr", args={})

    # First calculation (inserter returns [1,2,3,1,2,3], so 6 items)
    af1, _ = apply_and_calculate(test_ctx, [1, 2, 3], at_d)
    # Attributes are stored in the global attribute_storage
    storage = test_ctx.container.get(AttributeStorageAPI)
    assert storage.attributes[at_d][1] == "value_1"
    # Called for all 6 items (including duplicates)
    assert call_count["simple_attr"] == 6

    # Second calculation: should recalculate (no cache)
    af2, _ = apply_and_calculate(test_ctx, [1, 2, 3], at_d)
    assert storage.attributes[at_d][1] == "value_1"
    assert call_count["simple_attr"] == 12  # Called again for all 6 items!


def test_cache_clear(make_ctx, tmp_path):
    """Test that clearing cache forces recalculation."""
    ctx = make_ctx()
    cache_path = str(tmp_path / "cache.json")
    test_ctx = create_test_ctx(ctx, cache_path)
    register_tools_from_module(test_ctx, tests.plugins_test_impl_attribute_cache.__name__)

    at_d = AttributeDescriptor.create("expensive_attr", args={})

    # First calculation
    apply_and_calculate(test_ctx, [1, 2, 3], at_d)
    count1 = call_count["expensive_attr"]

    # Second calculation: should hit cache
    apply_and_calculate(test_ctx, [1, 2, 3], at_d)
    count2 = call_count["expensive_attr"]
    assert count2 == count1  # No new calculations

    # Clear cache
    test_ctx.container.get(AttributeCacheAPI).clear_cache()

    # Third calculation: should recalculate
    apply_and_calculate(test_ctx, [1, 2, 3], at_d)
    count3 = call_count["expensive_attr"]
    assert count3 > count2  # Called again!


def test_cache_size_tracking(make_ctx, tmp_path):
    """Test that cache size is tracked correctly."""
    ctx = make_ctx()
    cache_path = str(tmp_path / "cache.json")
    test_ctx = create_test_ctx(ctx, cache_path)
    register_tools_from_module(test_ctx, tests.plugins_test_impl_attribute_cache.__name__)

    at_d = AttributeDescriptor.create("expensive_attr", args={})

    # Before calculation: empty cache
    assert test_ctx.container.get(AttributeCacheAPI)._size() == 0

    # After calculation: cache has entries
    apply_and_calculate(test_ctx, [1, 2, 3], at_d)
    assert test_ctx.container.get(AttributeCacheAPI)._size() == 3  # One per unique cache key

    # After clear: empty cache
    test_ctx.container.get(AttributeCacheAPI).clear_cache()
    assert test_ctx.container.get(AttributeCacheAPI)._size() == 0


def test_cache_key_can_be_any_attribute(make_ctx, tmp_path):
    """Test that any attribute can be used as cache key."""
    ctx = make_ctx()
    cache_path = str(tmp_path / "cache.json")
    test_ctx = create_test_ctx(ctx, cache_path)
    register_tools_from_module(test_ctx, tests.plugins_test_impl_attribute_cache.__name__)

    # cache_key_attr returns "key_1", "key_2", "key_3" for items 1, 2, 3
    at_d = AttributeDescriptor.create("expensive_attr", args={})

    af, _ = apply_and_calculate(test_ctx, [1, 2, 3], at_d)
    storage = test_ctx.container.get(AttributeStorageAPI)
    assert storage.attributes[at_d][1] == "expensive_1"
    assert storage.attributes[at_d][2] == "expensive_2"
    assert storage.attributes[at_d][3] == "expensive_3"

    # Check cache contains the right keys
    assert test_ctx.container.get(AttributeCacheAPI)._size() == 3


def test_cache_with_different_cache_keys(make_ctx, tmp_path):
    """Test that different cache keys result in different cache entries."""
    ctx = make_ctx()
    cache_path = str(tmp_path / "cache.json")
    test_ctx = create_test_ctx(ctx, cache_path)
    register_tools_from_module(test_ctx, tests.plugins_test_impl_attribute_cache.__name__)

    at_d = AttributeDescriptor.create("expensive_attr", args={})

    # First calculation
    apply_and_calculate(test_ctx, [1, 2, 3], at_d)
    count1 = call_count["expensive_attr"]

    # Second calculation with same items (should hit cache)
    apply_and_calculate(test_ctx, [1, 2, 3], at_d)
    count2 = call_count["expensive_attr"]
    assert count2 == count1  # Cache hit, no new calls


def test_cache_key_attribute_must_exist(make_ctx):
    """Test that cache_attribute must reference a valid attribute."""
    ctx = make_ctx()
    register_tools_from_module(ctx, tests.plugins_test_impl_attribute_cache.__name__)

    # Verify expensive_attr has cache_attribute set correctly
    metadata = ctx.registry.get_metadata("expensive_attr")
    assert metadata.cache_attribute == "cache_key_attr"

    # Verify cache_key_attr exists
    cache_key_metadata = ctx.registry.get_metadata("cache_key_attr")
    assert cache_key_metadata is not None


def test_cache_persistence_across_sessions(make_ctx, tmp_path):
    """Test that cache persists across different UdanContext instances.

    This test verifies that:
    1. First UdanContext calculates an attribute
    2. Second UdanContext with same udan_cache_dir retrieves from cache (no recalculation)
    """

    # Define cacheable attribute
    ctx = make_ctx()

    @annotated(meta={"attribute_type": "simple"})
    def slow_cache_key(item: int) -> str:
        """Cheap cache key for slow attribute."""
        return f"key_{item}"

    @annotated(meta={"attribute_type": "simple", "cache_attribute": "slow_cache_key"})
    def slow_attr(item: int) -> str:
        """Expensive attribute."""
        global call_count
        call_count["slow_attr"] += 1
        return f"slow_{item}"

    @annotated(meta={"tool_type": "inserter"})
    def insert_numbers() -> list[int]:
        """Insert test numbers."""
        return [1, 2, 3]

    # First UdanContext: calculate attribute
    call_count["slow_attr"] = 0
    # Set udan_cache_dir to tmp_path so both UdanContexts
    # share the same cache
    tmpdir = str(tmp_path)
    config1 = ctx.config.model_copy(update={"udan_cache_dir": tmpdir})
    container1 = create_udan_container(config=config1)
    ctx1 = container1.get(UdanContext)._with_plugins()
    ctx1.container = container1

    # Register tools
    slow_cache_key_m = _load_tool_metadata(slow_cache_key, None, kinds_by_name=kinds_vocabulary())
    ctx1._register_metadata(slow_cache_key_m, slow_cache_key)

    slow_attr_m = _load_tool_metadata(slow_attr, None, kinds_by_name=kinds_vocabulary())
    ctx1._register_metadata(slow_attr_m, slow_attr)

    insert_m = _load_tool_metadata(insert_numbers, None, kinds_by_name=kinds_vocabulary())
    ctx1._register_metadata(insert_m, insert_numbers)

    # Calculate attribute
    at_d = AttributeDescriptor.create("slow_attr", args={})
    opds = [OperatorDescriptor.create("insert_numbers")]
    forest = Forest.from_items(opds)
    exec_ctx1 = ExecContext(logger=DebugLogger(log_time=False))

    # Create attribute storage and context for operator application
    attribute_storage1 = AttributeStorage(attributes={})
    attr_context1 = AttributesContext(
        attribute_runtime=ctx1.container.get(AttributeRuntimeAPI),
        attribute_storage=attribute_storage1,
        requested_attributes=forest.types.flattened_requested(),
        ctx=exec_ctx1,
    )

    forest_ext = _engine(ctx1)._apply_operators_in_forest(forest, exec_ctx1, attr_context1)
    ctx1.container.get(AttributeRuntimeAPI).calculate_attributes_in_forest(forest_ext, [at_d], exec_ctx1)

    # Verify calculation happened
    assert call_count["slow_attr"] == 3
    # Attributes are stored in the global attribute_storage
    storage = ctx1.container.get(AttributeRuntimeAPI).attribute_storage
    assert storage.attributes[at_d][1] == "slow_1"

    # Second UdanContext: should retrieve from cache
    call_count["slow_attr"] = 0
    # Use same udan_cache_dir to share cache
    config2 = ctx.config.model_copy(update={"udan_cache_dir": tmpdir})
    container2 = create_udan_container(config=config2)
    ctx2 = container2.get(UdanContext)._with_plugins()
    ctx2.container = container2

    # Register tools again
    ctx2._register_metadata(slow_cache_key_m, slow_cache_key)
    ctx2._register_metadata(slow_attr_m, slow_attr)
    ctx2._register_metadata(insert_m, insert_numbers)

    # Calculate attribute again (should use cache)
    forest2 = forest
    exec_ctx2 = ExecContext(logger=DebugLogger(log_time=False))

    # Create attribute storage and context for operator application
    attribute_storage2 = AttributeStorage(attributes={})
    attr_context2 = AttributesContext(
        attribute_runtime=ctx2.container.get(AttributeRuntimeAPI),
        attribute_storage=attribute_storage2,
        requested_attributes=forest2.types.flattened_requested(),
        ctx=exec_ctx2,
    )

    forest2_ext = _engine(ctx2)._apply_operators_in_forest(forest2, exec_ctx2, attr_context2)
    ctx2.container.get(AttributeRuntimeAPI).calculate_attributes_in_forest(forest2_ext, [at_d], exec_ctx2)

    # Verify cache was used (function not called again)
    assert call_count["slow_attr"] == 0  # Not called, used cache
    storage2 = ctx2.container.get(AttributeRuntimeAPI).attribute_storage
    assert storage2.attributes[at_d][1] == "slow_1"


def _engine(ctx):
    """The operators engine, resolved from the container the fixture built."""
    return ctx.container.get(OperatorsEngineAPI)
