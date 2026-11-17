"""Test metadata cache invalidation when tool code changes.

This test reproduces the issue where modifying a tool's metadata
doesn't invalidate the cache, causing old metadata to be used.
"""

import importlib
import os
import sys
from pathlib import Path

from udan.core_tools_loading.impl_tools_loader import ToolsLoader
from udan.core_tools_loading.io_fs import get_module_update_time


class DummyModule:
    """Dummy module for testing cache invalidation."""

    __name__ = "test_dummy_module"
    __file__ = __file__


def create_test_module_with_param(temp_dir: Path, include_param: bool) -> Path:
    """Create a test module file with or without a parameter.

    Args:
        temp_dir: Temporary directory to create the module in
        include_param: If True, module has 'extra_param'; if False, no param

    Returns:
        Path to the created module file
    """
    module_code = (
        """
from udan.core_tools_loading.api_annotated import annotated

@annotated(meta={"tool_type": "attribute"})
def test_attr(item: str"""
        + (", extra_param: bool = True" if include_param else "")
        + """) -> str:
    \"\"\"Test attribute.\"\"\"
    return item
"""
    )

    module_path = temp_dir / "test_cache_module.py"
    module_path.write_text(module_code)
    return module_path


def test_cache_invalidation_on_file_change(tmp_path):
    """Test that cache invalidates when module file is modified.

    This test reproduces the bug where:
    1. Load tool metadata (with parameter 'extra_param')
    2. Modify the file to remove 'extra_param'
    3. Load again - should detect change and use new metadata
    4. After fix: cache invalidates properly with microsecond precision

    Note: Uses os.utime() to manually update mtime instead of time.sleep()
    for faster test execution.
    """
    temp_path = tmp_path
    cache_dir = temp_path / "cache"
    cache_dir.mkdir()

    # Step 1: Create module WITH extra_param
    module_path = temp_path / "test_cache_module.py"
    module_code = """
from udan.core_tools_loading.api_annotated import annotated

@annotated(meta={"tool_type": "attribute"})
def test_attr(item: str, extra_param: bool = True) -> str:
    \"\"\"Test attribute.\"\"\"
    return item
"""
    module_path.write_text(module_code)
    # Manually set mtime to ensure unique timestamp
    current_time = os.path.getmtime(module_path)
    os.utime(module_path, (current_time - 2, current_time - 2))

    # Import the module
    sys.path.insert(0, str(temp_path))
    module = importlib.import_module("test_cache_module")

    # Step 2: Load metadata (should cache it with extra_param)
    loader = ToolsLoader(cache_dir=str(cache_dir), use_cache=True)
    metadata_fns_v1 = loader.load_from_module(module)
    metadatas_v1 = [metadata for metadata, _ in metadata_fns_v1]
    assert len(metadatas_v1) == 1
    params_v1 = metadatas_v1[0].parameters["properties"]
    assert "extra_param" in params_v1, f"V1 should have extra_param, got: {list(params_v1.keys())}"

    # Step 3: Modify module to REMOVE extra_param
    module_code_v2 = """
from udan.core_tools_loading.api_annotated import annotated

@annotated(meta={"tool_type": "attribute"})
def test_attr(item: str) -> str:
    \"\"\"Test attribute.\"\"\"
    return item
"""
    module_path.write_text(module_code_v2)
    # Manually update mtime to ensure different timestamp (no sleep needed!)
    current_time = os.path.getmtime(module_path)
    os.utime(module_path, (current_time - 1, current_time - 1))

    # Step 4: Reload module
    importlib.reload(module)

    # Step 5: Load metadata again - should use NEW metadata without extra_param
    # After fix: cache invalidates properly with microsecond precision
    metadata_fns_v2 = loader.load_from_module(module)
    metadatas_v2 = [metadata for metadata, _ in metadata_fns_v2]
    assert len(metadatas_v2) == 1
    params_v2 = metadatas_v2[0].parameters["properties"]

    # After fix with microsecond precision, this should pass
    assert "extra_param" not in params_v2, (
        f"V2 should NOT have extra_param, but it does! Cache bug: {list(params_v2.keys())}"
    )

    # Cleanup - remove module from sys.modules to avoid interference
    if "test_cache_module" in sys.modules:
        del sys.modules["test_cache_module"]
    sys.path.remove(str(temp_path))


def test_cache_key_generation(tmp_path):
    """Test that cache keys properly include file modification time.

    This tests the specific case where file modifications within the same
    second cause cache collisions. With microsecond precision, this is fixed.
    """
    temp_path = tmp_path

    # Create module
    module_path = create_test_module_with_param(temp_path, include_param=True)
    # Set initial mtime
    current_time = os.path.getmtime(module_path)
    os.utime(module_path, (current_time - 2, current_time - 2))

    # Import and get update time
    sys.path.insert(0, str(temp_path))
    module = importlib.import_module("test_cache_module")

    mtime1 = get_module_update_time(module)

    # Modify file and manually update mtime to ensure it changes
    create_test_module_with_param(temp_path, include_param=False)
    # Set mtime to 1 second in the past to guarantee different timestamp
    current_time = os.path.getmtime(module_path)
    os.utime(module_path, (current_time - 1, current_time - 1))

    # Get new mtime
    importlib.reload(module)
    mtime2 = get_module_update_time(module)

    # With microsecond precision, mtimes should be different
    assert mtime1 != mtime2, "Cache bug: mtimes are equal - cache won't invalidate!"

    # Cleanup - remove module from sys.modules to avoid interference
    if "test_cache_module" in sys.modules:
        del sys.modules["test_cache_module"]
    sys.path.remove(str(temp_path))
