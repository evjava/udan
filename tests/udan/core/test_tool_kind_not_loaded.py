"""A tool whose kind no loaded package owns fails at interpretation.

Interpreting such a tool must say what is missing (UDAN-422): not resolve a chain
item that the walk would silently drop into an empty output, and not fold the
chain into "no data source" for a render that was never the problem.

The scenario is a tool whose kind nothing declares (plugins_test_zombie_kind): the
loader builds a bare kind from the unknown tool_type, so the tool loads with no
rules and the routing has no handler for it. Every chain-forming kind's owner is
core-internal now - udan.attributes and udan.renders joined udan beside
udan.operator* - so a module list can no longer produce an unowned kind, and no
module list can drop the render either (the "the render is not the failure" variant
from when renders was a droppable package is gone with that premise; the message
below names the tool and the kind, nothing about output).
"""

import tests.plugins_test_zombie_kind as plugins_zombie
from tests.conftest import make_qp, register_tools_from_module
from udan.core.config import UdanConfig
from udan.core.impl_ioc import create_udan_container
from udan.core.impl_udan_context import UdanContext


def _qp(config: UdanConfig):
    container = create_udan_container(config)
    ctx = container.get(UdanContext).load_core()
    ctx.container = container
    register_tools_from_module(ctx, plugins_zombie.__name__, verbose=False)
    return make_qp(ctx)


def test_interpret_names_the_tool_and_the_missing_kind():
    """A chain item of an unowned kind reports the tool, the kind and the fix."""
    query = "range 2, zombie_inserter"
    forest, _, _, out = _qp(UdanConfig()).execute_query(query)

    assert forest is None
    assert "tool 'zombie_inserter' cannot be interpreted" in out
    assert "kind 'zombie'" in out
    assert "udan_plugin_modules" in out


def test_chain_applies_when_the_kind_is_owned():
    """With the owning kind present, the same chain applies and renders.

    The attribute here (demo's double) is core-internal since the demo package
    joined udan.
    """
    query = "range 2, double"
    forest, _, _, out = _qp(UdanConfig()).execute_query(query)

    assert forest is not None
    assert out == "- 0 :: 0\n- 1 :: 2"


def test_types_disabled_still_names_the_missing_kind():
    """The routing refuses the step with the type system disabled (it folds nothing).

    The fold defers to the routing for an unowned kind, so the verdict survives the
    dummy type system instead of degrading into the silent drop it was.
    """
    query = "range 2, zombie_inserter"
    config = UdanConfig(udan_types_enabled=False)
    forest, _, _, out = _qp(config).execute_query(query)

    assert forest is None
    assert "tool 'zombie_inserter' cannot be interpreted" in out
    assert "kind 'zombie'" in out
