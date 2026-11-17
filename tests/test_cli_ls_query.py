"""Test that 'ls' query works in CLI mode.

This test reproduces the issue where 'ls' query fails because
ToolsRegistryAPI dependency cannot be injected when exec_ctx is None.
"""

from src.udan.core.config import UdanConfig
from tests.conftest import make_qp
from udan.core.impl_ioc import create_udan_container
from udan.core.impl_udan_context import UdanContext
from udan.core_tools_loading.api_tools_registry import ToolsRegistryAPI


def test_ls_query_cli_mode():
    """Test that 'ls' query works in CLI mode.

    The 'ls' query is expanded to 'help ls' by the query parser.
    The help function requires ToolsRegistryAPI dependency,
    which the injector resolves from the container even when exec_ctx is None.
    """

    container = create_udan_container(UdanConfig())
    ctx_obj = container.get(UdanContext).load_core()
    ctx_obj.container = container
    ctx_obj.container = container
    ctx = ctx_obj
    qp = make_qp(ctx)

    # Verify that ToolsRegistryAPI is a key the container serves
    assert ToolsRegistryAPI in ctx.container.provided_keys()

    # Execute 'ls' query - this should not raise an error
    result = qp.execute_query("ls")
    forest, attrs, render_specs, out = result

    # Verify that the query succeeded
    assert forest is not None, f"Query failed with output: {out[:200]}"
    assert forest.depths
    assert "RuntimeError" not in out, f"Query raised RuntimeError: {out[:200]}"


def test_help_query_cli_mode():
    """Test that 'help' query works in CLI mode."""

    container = create_udan_container(UdanConfig())
    ctx_obj = container.get(UdanContext).load_core()
    ctx_obj.container = container
    ctx_obj.container = container
    ctx = ctx_obj
    qp = make_qp(ctx)

    # Execute 'help' query - this should not raise an error
    forest, attrs, render_specs, out = qp.execute_query("help")

    # Verify that the query succeeded
    assert forest is not None, f"Query failed with output: {out[:200]}"
    assert forest.depths
    assert "RuntimeError" not in out, f"Query raised RuntimeError: {out[:200]}"
