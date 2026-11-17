"""Demo test for .udan/vars.env file variable support.

This test verifies that variables can be loaded from .udan/vars.env file and referenced
via $var syntax in queries.
"""

import os

import udan.plugins_tools_demo.plugins_demo
import udan.plugins_tools_demo.plugins_fruits
from tests.conftest import make_qp
from udan.attributes import plugins_operators_attribute
from udan.core.config import UdanConfig
from udan.core.impl_ioc import create_udan_container
from udan.core.impl_udan_context import UdanContext
from udan.plugins_tools_examples import plugins_builtins, plugins_fs


def test_env_variables_basic(tmp_path):
    """Test that variables can be loaded from .udan/vars.env file."""
    # Create .udan directory and vars.env file
    udan_dir = tmp_path / ".udan"
    udan_dir.mkdir()
    env_path = udan_dir / "vars.env"
    env_content = """# Test variables
udan_src=src/udan
test_dir=tests/resources
"""
    env_path.write_text(env_content)

    original_cwd = os.getcwd()
    try:
        os.chdir(tmp_path)

        # Create UdanContext after chdir so it loads .udan/vars.env from tmp_path

        container = create_udan_container(UdanConfig())
        ctx_obj = container.get(UdanContext)._with_plugins(udan.plugins_tools_demo.plugins_demo, plugins_builtins)
        ctx_obj.container = container
        ctx_obj.container = container
        ctx = ctx_obj

        # Check that variable was loaded from .udan/vars.env
        assert ctx.has_variable("udan_src"), "udan_src variable should be loaded from .udan/vars.env"
        var_value = ctx._get_variable("udan_src")
        # Variable should contain the path
        output = str(var_value)
        assert "src/udan" in output, f"Variable should contain path, got: {output}"
    finally:
        os.chdir(original_cwd)


def test_env_variable_in_query(tmp_path):
    """Test that .udan/vars.env variables can be used in queries."""
    # Store original values
    original_cwd = os.getcwd()

    # Create .udan directory and vars.env file with absolute path
    udan_dir = tmp_path / ".udan"
    udan_dir.mkdir()
    env_path = udan_dir / "vars.env"
    env_content = f"""# Test variables
udan_src={original_cwd}/src/udan
"""
    env_path.write_text(env_content)

    # Change to tmp_path so ExecContext will find our .udan/vars.env file
    try:
        os.chdir(tmp_path)

        # Create UdanContext after chdir so it loads .udan/vars.env from tmp_path
        # Include plugins_fs for ls_files command
        container = create_udan_container(UdanConfig())
        ctx = container.get(UdanContext)._with_plugins(
            udan.plugins_tools_demo.plugins_demo, plugins_builtins, plugins_operators_attribute, plugins_fs
        )
        ctx.container = container
        qp = make_qp(ctx)

        # Use variable in query: ls_files $udan_src
        # Should list Python files in src/udan
        forest, attrs, render_specs, out = qp.execute_query("ls_files $udan_src")

        # Should show .py files
        assert ".py" in out, "Output should contain .py files"
    finally:
        os.chdir(original_cwd)
