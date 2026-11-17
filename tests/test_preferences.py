"""Tests for tool preferences configuration."""

import pytest

import tests.plugins_test_preferences
import udan.plugins_tools_core.plugins_help
import udan.plugins_tools_core.plugins_system
import udan.plugins_tools_demo.plugins_demo
import udan.plugins_tools_demo.plugins_fruits
from tests.conftest import make_qp, register_tools_from_module
from udan.core.config import UdanConfig
from udan.core.impl_ioc import create_udan_container
from udan.core.impl_udan_context import UdanContext


def register_tange(ctx) -> None:
    register_tools_from_module(ctx, tests.plugins_test_preferences.__name__)


@pytest.fixture
def ctx_with_demo(make_ctx):
    ctx = make_ctx()
    register_tools_from_module(ctx, udan.plugins_tools_demo.plugins_demo.__name__)
    register_tools_from_module(ctx, udan.plugins_tools_demo.plugins_fruits.__name__)
    register_tange(ctx)
    return ctx


def test_default_diff_preference(ctx_with_demo):
    default_prefs = {"diff": "git.insert_diff"}
    merged_prefs = {**default_prefs, **ctx_with_demo.config.udan_tools_preferences_input}
    assert merged_prefs["diff"] == "git.insert_diff"


def test_range_preference_over_tange(ctx_with_demo):
    config = UdanConfig(udan_tools_preferences_input={"range": "demo.range"})
    container = create_udan_container(config=config)
    ctx = container.get(UdanContext)
    ctx.container = container
    qp = make_qp(ctx)
    register_tools_from_module(ctx, udan.plugins_tools_demo.plugins_demo.__name__)
    register_tools_from_module(ctx, udan.plugins_tools_demo.plugins_fruits.__name__)
    register_tange(ctx)

    forest, attrs, render, out = qp.execute_query("range 3")
    lines = out.strip().split("\n")
    assert len(lines) == 3
    assert lines[0] == "- 0"

    forest, attrs, render, out = qp.execute_query("tange 3")
    lines = out.strip().split("\n")
    assert len(lines) == 3
    assert lines[0] == "- 5"


def test_ambiguous_query_with_preference(ctx_with_demo):
    config = UdanConfig(udan_tools_preferences_input={"ange": "demo.range"})
    container = create_udan_container(config=config)
    ctx = container.get(UdanContext)
    ctx.container = container
    qp = make_qp(ctx)
    register_tools_from_module(ctx, udan.plugins_tools_demo.plugins_demo.__name__)
    register_tools_from_module(ctx, udan.plugins_tools_demo.plugins_fruits.__name__)
    register_tange(ctx)

    forest, attrs, render, out = qp.execute_query("range 2")
    lines = out.strip().split("\n")
    assert len(lines) == 2
    assert lines[0] == "- 0"
    assert lines[1] == "- 1"


def test_no_preference_raises_error(ctx_with_demo, make_ctx):
    ctx = make_ctx()
    qp = make_qp(ctx)
    register_tools_from_module(ctx, udan.plugins_tools_demo.plugins_demo.__name__)
    register_tools_from_module(ctx, udan.plugins_tools_demo.plugins_fruits.__name__)
    register_tools_from_module(ctx, udan.plugins_tools_core.plugins_help.__name__)
    register_tools_from_module(ctx, udan.plugins_tools_core.plugins_system.__name__)
    register_tange(ctx)

    forest, attrs, render, out = qp.execute_query("ange 3")

    # No preference: the ambiguity is answered with the listing of the matches
    assert forest is not None, "the listing rides the override forest"
    assert "demo.range" in out
    assert "test_preferences.tange" in out


def test_preference_dict_format(ctx_with_demo):
    config = UdanConfig(
        udan_tools_preferences_input={
            "ange": "test_preferences.tange",
            "range": "demo.range",
        }
    )
    container = create_udan_container(config=config)
    ctx = container.get(UdanContext)
    ctx.container = container
    register_tools_from_module(ctx, udan.plugins_tools_demo.plugins_demo.__name__)
    register_tools_from_module(ctx, udan.plugins_tools_demo.plugins_fruits.__name__)
    register_tange(ctx)

    default_prefs = {"diff": "insert_diff"}
    merged_prefs = {**default_prefs, **ctx.config.udan_tools_preferences_input}

    assert merged_prefs["ange"] == "test_preferences.tange"
    assert merged_prefs["range"] == "demo.range"
    assert merged_prefs["diff"] == "insert_diff"


def test_ambiguous_resolved_by_preference(ctx_with_demo):
    config = UdanConfig(udan_tools_preferences_input={"ange": "demo.range"})
    container = create_udan_container(config=config)
    ctx = container.get(UdanContext)
    ctx.container = container
    qp = make_qp(ctx)
    register_tools_from_module(ctx, udan.plugins_tools_demo.plugins_demo.__name__)
    register_tools_from_module(ctx, udan.plugins_tools_demo.plugins_fruits.__name__)
    register_tange(ctx)

    forest, attrs, render, out = qp.execute_query("ange 3")
    lines = out.strip().split("\n")
    assert len(lines) == 3
    assert lines[0] == "- 0"
    assert lines[1] == "- 1"
    assert lines[2] == "- 2"
