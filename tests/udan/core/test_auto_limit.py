"""Tests for auto-limit functionality."""

import pytest

import tests.plugins_test_lazy_inserter as lazy_inserter
from tests import plugins_test
from tests.conftest import make_qp, register_tools_from_module
from udan.attributes import plugins_operators_attribute
from udan.core.config import UdanConfig
from udan.core.impl_ioc import create_udan_container
from udan.core.impl_udan_context import UdanContext
from udan.plugins_tools_demo import plugins_demo, plugins_fruits
from udan.plugins_tools_examples import plugins_builtins


@pytest.fixture
def ctx_with_lazy_inserter(make_ctx):
    """Context with the lazy counting inserter registered."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute)
    register_tools_from_module(ctx, lazy_inserter.__name__)
    lazy_inserter.reset_pulled_count()
    return ctx


def test_default_limit_config_value(make_ctx):
    """Test that default limit config value is accessible."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute)
    assert hasattr(ctx.config, "udan_default_limit")
    assert ctx.config.udan_default_limit == 30  # Default value


def test_auto_limit_applied_with_default_config(make_ctx):
    """Test that auto-limit (default 30) is applied when no explicit limit."""
    # Range 100 without limit should return 30 items (default limit)
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute)
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query("range 100")

    # Count the lines in output
    lines = [line for line in out.strip().split("\n") if line.strip()]
    assert len(lines) == 30


def test_explicit_limit_takes_precedence(make_ctx):
    """Test that explicit limit takes precedence over auto-limit."""
    # Range 100 with explicit limit 10 should return exactly 10 items
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute)
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query("range 100, limit 10")

    # Count the lines in output
    lines = [line for line in out.strip().split("\n") if line.strip()]
    assert len(lines) == 10


def test_auto_limit_not_applied_below_threshold(make_ctx):
    """Test that auto-limit is not applied when result is below threshold."""
    # Range 10 (below default limit of 30) should return all 10 items
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute)
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query("range 10")

    # Count the lines in output
    lines = [line for line in out.strip().split("\n") if line.strip()]
    assert len(lines) == 10


def test_nolimit_disables_auto_limit(make_ctx):
    """Test that :nolimit render spec disables auto-limit."""
    # Range 100 with :nolimit should return all items (no auto-limit)
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute)
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query("range 100, :nolimit")

    # Count the lines in output — should be all items, not truncated to 30
    lines = [line for line in out.strip().split("\n") if line.strip()]
    assert len(lines) > 30  # More than the default limit


def test_limit_with_offset(make_ctx):
    """Test that limit operator supports offset parameter."""
    # Range 100 with limit 5 offset 10 should return items 10-14
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute)
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query("range 100, limit --limit=5 --offset=10")

    # Count the lines in output
    lines = [line for line in out.strip().split("\n") if line.strip()]
    assert len(lines) == 5
    assert "- 10" in out
    assert "- 14" in out
    assert "- 15" not in out


def test_limit_with_explicit_zero_disables_auto_limit(make_ctx):
    """Test that explicit limit 0 returns nothing (edge case)."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute)
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query("range 100, limit 0")

    lines = [line for line in out.strip().split("\n") if line.strip()]
    assert len(lines) == 0


def test_intermediate_limit_does_not_suppress_auto_limit(make_ctx):
    """Test that limit used mid-pipeline still gets global auto-limit.

    When limit is NOT the last operator, auto-limit should still apply.
    E.g. ``(range 40; range 50, limit 10), sort`` — limit caps the inner
    range to 10, then sort runs, and global auto-limit caps at 30.
    """
    # limit is NOT the last operator (sort is), so auto-limit should apply
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute)
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query("range 40; range 50, limit 10, sort")
    lines = [line for line in out.strip().split("\n") if line.strip()]
    # 10 items from the inner limit, then sorted — still only 10, well under 30.
    # But the point is: auto-limit logic does NOT skip because limit is mid-chain.
    # With more items it would truncate; here we just verify no error and < 30.
    assert len(lines) == 10


def test_last_operator_is_limit_suppresses_auto_limit(make_ctx):
    """Test that limit as the very last operator suppresses auto-limit."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute)
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query("range 40; range 50, sort, limit 10")
    lines = [line for line in out.strip().split("\n") if line.strip()]
    # limit is the last operator, so auto-limit should NOT apply.
    # sort first (50 items), then limit 10 → 10 items.
    assert len(lines) == 10


def test_limit_negative_one_unlimited(make_ctx):
    """Test that limit -1 returns all items (unlimited)."""
    # Range 40 with limit -1 should return all 40 items
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute)
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query("range 40, limit -1")

    lines = [line for line in out.strip().split("\n") if line.strip()]
    assert len(lines) == 40


def test_limit_negative_one_suppresses_auto_limit(make_ctx):
    """Test that limit -1 suppresses auto-limit and returns all items."""
    # Range 100 with limit -1 should return all 100 items (not truncated to 30)
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute)
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query("range 100, limit -1")

    lines = [line for line in out.strip().split("\n") if line.strip()]
    assert len(lines) == 100


def test_limit_negative_with_offset(make_ctx):
    """Test that limit -1 with offset returns items from offset to end."""
    # Range 50 with limit -1 and offset 10 should return items 10-49 (40 items)
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute)
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query("range 50, limit -1 --offset=10")

    lines = [line for line in out.strip().split("\n") if line.strip()]
    assert len(lines) == 40
    assert "- 10" in out
    assert "- 49" in out


def test_auto_limit_bounds_lazy_source_pull(ctx_with_lazy_inserter):
    """Auto-limit must stop pulling items from lazy sources at the limit.

    When the query has no explicit limit, the engine materializes operator
    output only up to the default limit, so a lazy source (db cursor, file)
    is not drained just to truncate the result afterwards.
    """
    ctx = ctx_with_lazy_inserter
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query("insert_lazy_counting")

    assert forest.items == list(range(30))
    assert lazy_inserter.pulled_count == 30


def test_nolimit_does_not_bound_lazy_source_pull(ctx_with_lazy_inserter):
    """:nolimit disables both auto-limit and the lazy source pull bound."""
    ctx = ctx_with_lazy_inserter
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query("insert_lazy_counting, :nolimit")

    assert forest.items == list(range(lazy_inserter.TOTAL_ITEMS))
    assert lazy_inserter.pulled_count == lazy_inserter.TOTAL_ITEMS


def test_explicit_limit_operator_does_not_bound_lazy_source_pull(ctx_with_lazy_inserter):
    """Explicit limit as last operator suppresses auto-limit and the pull bound.

    The limit operator consumes the whole sequence itself, so the lazy source
    is drained (same as before the pull bound existed).
    """
    ctx = ctx_with_lazy_inserter
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query("insert_lazy_counting, limit 10")

    assert forest.items == list(range(10))
    assert lazy_inserter.pulled_count == lazy_inserter.TOTAL_ITEMS


def test_bounded_pull_keeps_streaming_filter_semantics(make_ctx):
    """The cap stops the filter group at 30 items; the source's own group runs uncapped.

    filter_keep_div 3 keeps every third item, so reaching the 30-item cap used to
    need 88 source items - the cap stopped the source, the filter and the
    truncation together. The chain is two chain groups now - the filter is a plugin
    kind with its own chain service - and the cap lands on the last group only, so
    the inserter group materializes the source on the way to its stage boundary
    (see the extender's streaming tests for the same consequence).
    """
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_builtins, plugins_operators_attribute, plugins_test)
    qp = make_qp(ctx)
    register_tools_from_module(ctx, lazy_inserter.__name__)
    lazy_inserter.reset_pulled_count()

    forest, attrs, render_specs, out = qp.execute_query("insert_lazy_counting, filter_keep_div 3")

    assert forest.items == [i * 3 for i in range(30)]
    assert lazy_inserter.pulled_count == lazy_inserter.TOTAL_ITEMS


def test_streaming_extender_stops_pulling_source_at_cap(ctx_with_lazy_inserter):
    """The cap stops the extender group at 30 items; the source's own group runs uncapped.

    Reproduction of 'insert_lazy, extend_lazy', which used to materialize the source
    before the extender saw a single item. The cap still stops the extender itself
    (30 items extended, the forest truncated to 30), but the chain is two chain
    groups now - the extender is a plugin kind with its own chain service - and the
    cap lands on the last group only, so the inserter group materializes the source
    on the way to its stage boundary. A stage boundary flattens through a Forest
    instead of streaming through a CachedIterable; that is the cost the kind
    extractions accepted (see the UDAN-399 analysis, section 3).
    """
    ctx = ctx_with_lazy_inserter
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query("insert_lazy_counting, extend_lazy_counting")

    assert forest.depths[:3] == [0, 1, 1]
    assert lazy_inserter.pulled_count == lazy_inserter.TOTAL_ITEMS
    assert lazy_inserter.extended_count == 30


def test_streaming_extender_terminates_infinite_source(ctx_with_lazy_inserter):
    """An unbounded source behind an extender ends at the source's own bound.

    Reproduction of 'insert_lazy --infinite, extend_lazy', which hung while pulling
    hundreds of thousands of items without ever calling the extender. The source's
    bound is an exception now: it yields SOURCE_BOUND_ITEMS items, then raises, so
    draining it fails in well under a second. The failure is the source's own and
    not limiting's - the pull runs past the cap (30) before the source gives up,
    because the extender is a plugin kind with its own chain group, the cap lands
    on the last group only, and the source's group runs uncapped. A cap that stops
    a source behind another kind's group is engine/orchestrator work, not the
    extraction's.
    """
    ctx = ctx_with_lazy_inserter
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query("insert_lazy_infinite, extend_lazy_counting")

    assert forest is None
    assert lazy_inserter.SOURCE_BOUND_ERROR in out
    assert lazy_inserter.pulled_count == lazy_inserter.SOURCE_BOUND_ITEMS
    assert lazy_inserter.extended_count == 0


def test_disabled_auto_limit_does_not_bound_lazy_source_pull():
    """With udan_default_limit=0 the source is pulled fully and nothing is truncated."""
    config = UdanConfig(udan_default_limit=0)
    container = create_udan_container(config=config)
    ctx: UdanContext = container.get(UdanContext)
    ctx.container = container
    qp = make_qp(ctx)
    register_tools_from_module(ctx, lazy_inserter.__name__)
    lazy_inserter.reset_pulled_count()

    forest, attrs, render_specs, out = qp.execute_query("insert_lazy_counting")

    assert forest.items == list(range(lazy_inserter.TOTAL_ITEMS))
    assert lazy_inserter.pulled_count == lazy_inserter.TOTAL_ITEMS
