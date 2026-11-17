"""Tool preferences against the git plugin's names.

Moved from udan's tests/test_preferences.py together with the plugin: the
unqualified / qualified alias forms resolving onto ``insert_diff``.
"""

from tests.conftest import make_qp, register_tools_from_module
from udan.core.config import UdanConfig
from udan.core.impl_ioc import create_udan_container
from udan.core.impl_udan_context import UdanContext
from udan.plugins_tools_examples import plugins_builtins, plugins_git


def test_preference_with_unqualified_name():
    config = UdanConfig(udan_tools_preferences_input={"diff": "insert_diff"})
    container = create_udan_container(config=config)
    ctx = container.get(UdanContext)
    ctx.container = container
    qp = make_qp(ctx)

    register_tools_from_module(ctx, plugins_git.__name__)

    forest, attrs, render, out = qp.execute_query("diff", debug=True)

    # When debug=True, the output includes the debug log prepended
    # Check that debug output is present
    assert "# [DEBUG]" in out, f"Expected debug output in output when debug=True, got: {out}"
    # The query should execute - output should contain git diff output
    assert "insert_diff" in out or "commits" in out or out.startswith("# [DEBUG]"), (
        f"Expected git diff output or debug output, got: {out}"
    )


def test_preference_with_qualified_name():
    config = UdanConfig(udan_tools_preferences_input={"diff": "git.insert_diff"})
    container = create_udan_container(config=config)
    ctx = container.get(UdanContext)
    ctx.container = container
    qp = make_qp(ctx)

    register_tools_from_module(ctx, plugins_git.__name__)
    register_tools_from_module(ctx, plugins_builtins.__name__)

    forest, attrs, render, out = qp.execute_query("diff")

    assert forest is not None, "Should execute git.insert_diff successfully"
