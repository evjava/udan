"""Tests for udan configuration system."""

import os

from tests.conftest import make_qp, register_tools_from_module
from udan.core.config import UdanConfig
from udan.core.impl_ioc import create_udan_container
from udan.core.impl_udan_context import UdanContext
from udan.plugins_tools_demo.plugins_fruits import insert_fruits


def create_ctx_with_config(config):
    """Helper to create UdanContext with config and register plugins.

    This is the only place in tests where UdanContext is created directly,
    which is necessary for testing config functionality.
    """

    container = create_udan_container(config)
    ctx = container.get(UdanContext)._with_plugins()
    ctx.container = container
    register_tools_from_module(ctx, insert_fruits.__module__)
    # Register renders for the default org-item(id, name) format
    register_tools_from_module(ctx, "udan.plugins_tools_examples.plugins_org")
    return ctx


def test_config_basic():
    """Test basic config functionality."""
    config = UdanConfig()
    config.udan_tools_variables_defaults["insert_fruits"] = {"pattern": "apple"}

    assert "pattern" in config.udan_tools_variables_defaults.get("insert_fruits", {})
    assert config.udan_tools_variables_defaults["insert_fruits"]["pattern"] == "apple"
    assert config.udan_tools_variables_defaults.get("nonexistent", {}).get("pattern") is None
    assert "pattern" not in config.udan_tools_variables_defaults.get("nonexistent", {})


def test_config_clear():
    """Test clearing config."""
    config = UdanConfig()
    config.udan_tools_variables_defaults["insert_fruits"] = {"pattern": "apple"}
    config.udan_tools_variables_defaults["org.cur"] = {"dir": "~/org"}

    assert "insert_fruits" in config.udan_tools_variables_defaults
    assert "org.cur" in config.udan_tools_variables_defaults

    del config.udan_tools_variables_defaults["insert_fruits"]
    assert "insert_fruits" not in config.udan_tools_variables_defaults
    assert "org.cur" in config.udan_tools_variables_defaults

    config.udan_tools_variables_defaults.clear()
    assert "org.cur" not in config.udan_tools_variables_defaults


def test_insert_fruits_with_config_default():
    """Test insert_fruits uses config default for pattern."""
    config = UdanConfig()
    config.udan_tools_variables_defaults["insert_fruits"] = {"pattern": "apple"}

    # Create exec context with config
    ctx = create_ctx_with_config(config)
    qp = make_qp(ctx)

    # Execute query without specifying pattern - should use config default
    forest, attrs, render_specs, out = qp.execute_query("insert_fruits")

    # Should only show fruits matching "apple" (filtered by config default
    # pattern)
    lines = out.strip().split("\n")
    assert len(lines) == 2
    assert lines[0] == "- 1 :: apple"
    assert lines[1] == "- 8 :: pineapple"
    assert "orange" not in out
    assert "banana" not in out


def test_insert_fruits_with_explicit_empty_pattern():
    """Test that explicit --pattern='' overrides config default."""
    config = UdanConfig()
    config.udan_tools_variables_defaults["insert_fruits"] = {"pattern": "apple"}

    # Create exec context with config
    ctx = create_ctx_with_config(config)
    qp = make_qp(ctx)

    # Execute query with explicit empty pattern - should override config
    forest, attrs, render_specs, out = qp.execute_query("insert_fruits --pattern=''")

    # Should show all fruits (empty pattern means no filtering)
    lines = out.strip().split("\n")
    assert len(lines) == 10  # 9 regular fruits + 1 mythical ambrosia
    assert lines[0] == "- 1 :: apple"
    assert lines[1] == "- 2 :: orange"
    assert lines[2] == "- 3 :: banana"


def test_insert_fruits_with_explicit_pattern():
    """Test that explicit pattern value overrides config default."""
    config = UdanConfig()
    config.udan_tools_variables_defaults["insert_fruits"] = {"pattern": "apple"}

    # Create exec context with config
    ctx = create_ctx_with_config(config)
    qp = make_qp(ctx)

    # Execute query with explicit pattern "berry" - should override config
    forest, attrs, render_specs, out = qp.execute_query("insert_fruits --pattern=berry")

    # Should show only berries (not apple from config)
    lines = out.strip().split("\n")
    assert len(lines) == 3
    assert lines[0] == "- 4 :: strawberry"
    assert lines[1] == "- 5 :: blueberry"
    assert lines[2] == "- 6 :: raspberry"
    assert "apple" not in out


def test_insert_fruits_without_config():
    """Test insert_fruits works normally without config."""
    # Create exec context with empty config (no defaults)
    config = UdanConfig()
    ctx = create_ctx_with_config(config)
    qp = make_qp(ctx)

    # Execute query without specifying pattern
    forest, attrs, render_specs, out = qp.execute_query("insert_fruits")

    # Should show all fruits (no config, no pattern = default behavior)
    lines = out.strip().split("\n")
    assert len(lines) == 10  # 9 regular fruits + 1 mythical ambrosia
    assert lines[0] == "- 1 :: apple"
    assert lines[1] == "- 2 :: orange"
    assert lines[2] == "- 3 :: banana"


def test_env_file_override(tmp_path):
    """Test that ENV_FILE environment variable overrides default .env location."""
    # Create a custom .env file with test variables
    custom_env_path = tmp_path / "custom.env"
    custom_env_path.write_text("UDAN_VARS_PATH=/custom/path/vars.env\nUDAN_CACHE_DIR=/custom/cache\n")

    # Set ENV_FILE environment variable
    os.environ["ENV_FILE"] = str(custom_env_path)

    try:
        # Create config - should load from custom_env_path
        config = UdanConfig()

        # Verify that values from custom .env file were loaded
        assert str(config.udan_vars_path) == "/custom/path/vars.env"
        assert str(config.udan_cache_dir) == "/custom/cache"

    finally:
        # Clean up environment variable
        del os.environ["ENV_FILE"]


def test_env_file_without_override():
    """Test that without ENV_FILE, config uses default .env file location."""
    # Ensure ENV_FILE is not set
    env_file = os.environ.pop("ENV_FILE", None)

    try:
        # Create config - should use default .env file (which may not exist)
        config = UdanConfig()

        # Should have default values since no .env file exists
        # Note: paths are normalized, so "./" prefix may be removed
        assert str(config.udan_vars_path) == ".udan/vars.env"
        # Cache dir defaults to ~/.local/share/udan (with ~ expanded)
        assert str(config.udan_cache_dir).endswith(".local/share/udan")

    finally:
        # Restore ENV_FILE if it was set
        if env_file is not None:
            os.environ["ENV_FILE"] = env_file


def test_env_file_with_tools_defaults(tmp_path):
    """Test that ENV_FILE can load udan_tools_variables_defaults."""
    # Create a custom .env file with JSON-encoded defaults
    custom_env_path = tmp_path / "custom.env"
    custom_env_path.write_text('UDAN_TOOLS_VARIABLES_DEFAULTS={"insert_fruits": {"pattern": "berry"}}\n')

    # Set ENV_FILE environment variable
    os.environ["ENV_FILE"] = str(custom_env_path)

    try:
        # Create config - should load from custom_env_path
        config = UdanConfig()

        # Verify that udan_tools_variables_defaults was loaded
        assert "insert_fruits" in config.udan_tools_variables_defaults
        assert config.udan_tools_variables_defaults["insert_fruits"]["pattern"] == "berry"

        # Create exec context with config
        ctx = create_ctx_with_config(config)
        qp = make_qp(ctx)

        # Execute query without specifying pattern - should use config default
        # from ENV_FILE
        forest, attrs, render_specs, out = qp.execute_query("insert_fruits")

        # Should only show berries (from ENV_FILE config)
        lines = out.strip().split("\n")
        assert len(lines) == 3
        assert lines[0] == "- 4 :: strawberry"
        assert lines[1] == "- 5 :: blueberry"
        assert lines[2] == "- 6 :: raspberry"

    finally:
        # Clean up environment variable
        del os.environ["ENV_FILE"]


def test_env_file_with_preferences(tmp_path):
    """Test that ENV_FILE can load udan_tools_preferences_input."""
    # Create a custom .env file with preferences
    # Note: env var name must match field name
    # (udan_tools_preferences_input)
    custom_env_path = tmp_path / "custom.env"
    custom_env_path.write_text('UDAN_TOOLS_PREFERENCES_INPUT={"test": "fruits.insert_fruits"}\n')

    # Set ENV_FILE environment variable
    os.environ["ENV_FILE"] = str(custom_env_path)

    try:
        # Create config - should load from custom_env_path
        config = UdanConfig()

        # Verify that udan_tools_preferences_input was loaded
        assert "test" in config.udan_tools_preferences_input
        assert config.udan_tools_preferences_input["test"] == "fruits.insert_fruits"

    finally:
        # Clean up environment variable
        del os.environ["ENV_FILE"]


def test_plugin_modules_env_comma_separated():
    """Test that UDAN_PLUGIN_MODULES accepts comma-separated module names."""
    os.environ["UDAN_PLUGIN_MODULES"] = "udan_plugins_example, udan.plugins_history"

    try:
        config = UdanConfig()
        assert config.udan_plugin_modules == ["udan_plugins_example", "udan.plugins_history"]

    finally:
        del os.environ["UDAN_PLUGIN_MODULES"]


def test_plugin_modules_env_single_module():
    """Test that UDAN_PLUGIN_MODULES accepts one module name without commas."""
    os.environ["UDAN_PLUGIN_MODULES"] = "udan_plugins_example"

    try:
        config = UdanConfig()
        assert config.udan_plugin_modules == ["udan_plugins_example"]

    finally:
        del os.environ["UDAN_PLUGIN_MODULES"]


def test_plugin_modules_env_json_list():
    """Test that UDAN_PLUGIN_MODULES still accepts a JSON list."""
    os.environ["UDAN_PLUGIN_MODULES"] = '["udan_plugins_example", "udan.plugins_history"]'

    try:
        config = UdanConfig()
        assert config.udan_plugin_modules == ["udan_plugins_example", "udan.plugins_history"]

    finally:
        del os.environ["UDAN_PLUGIN_MODULES"]


def test_plugin_modules_env_empty_disables_all():
    """Test that an empty UDAN_PLUGIN_MODULES disables all plugin modules."""
    os.environ["UDAN_PLUGIN_MODULES"] = ""

    try:
        config = UdanConfig()
        assert config.udan_plugin_modules == []

    finally:
        del os.environ["UDAN_PLUGIN_MODULES"]


def test_plugin_modules_default_discovers_installed_packages(monkeypatch, tmp_path):
    """Test that without UDAN_PLUGIN_MODULES, installed plugin packages are discovered.

    The core's own plugin subpackages (udan.parsing, udan.plugins_history, udan.attributes,
    udan.renders, udan.plugins_tools_examples*) are scanned with udan itself and are not on the list:
    discovery is by the udan_plugins_ prefix, so only external packages land here.
    Discovery reads sys.path, so a package dir planted there stands in for an
    installed one - udan ships no top-level udan_plugins_* package of its own.
    """
    pkg_dir = tmp_path / "udan_plugins_fake"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text("")
    monkeypatch.syspath_prepend(str(tmp_path))
    os.environ.pop("UDAN_PLUGIN_MODULES", None)

    config = UdanConfig()
    assert "udan_plugins_fake" in config.udan_plugin_modules
    assert config.udan_plugin_modules == sorted(config.udan_plugin_modules)


def test_env_file_with_plugin_modules_comma_separated(tmp_path):
    """Test that a comma-separated UDAN_PLUGIN_MODULES loads from a .env file."""
    custom_env_path = tmp_path / "custom.env"
    custom_env_path.write_text("UDAN_PLUGIN_MODULES=udan_plugins_example,udan.plugins_history\n")

    os.environ["ENV_FILE"] = str(custom_env_path)

    try:
        config = UdanConfig()
        assert config.udan_plugin_modules == ["udan_plugins_example", "udan.plugins_history"]

    finally:
        del os.environ["ENV_FILE"]
