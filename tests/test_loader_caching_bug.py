"""Test to reproduce ACTUAL caching bug.

The bug: When file content changes BUT mtime stays same (e.g., git checkout),
the cache is NOT invalidated.
"""

import importlib
import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from udan.core_tools_loading.impl_tools_loader import ToolsLoader


def test_cache_bug_when_mtime_unchanged():
    """Cache not invalidated when content changes but mtime stays same.

    This simulates git checkout behavior:
    1. Load plugin (populates cache with v1 metadata)
    2. Modify file BUT reset mtime to original value (git checkout preserves mtime)
    3. Load again - cache should be invalidated but WON'T BE because mtime unchanged
    """
    with TemporaryDirectory() as tmpdir:
        cache_dir = Path(tmpdir) / "cache"
        cache_dir.mkdir()

        plugin_dir = Path(tmpdir) / "test_cache_bug"
        plugin_dir.mkdir()
        plugin_file = plugin_dir / "plugin.py"

        # Version 1: simple operator
        plugin_file.write_text('''
from udan.core_tools_loading.api_annotated import annotated

@annotated
def test_operator(item: str) -> str:
    """Test operator v1."""
    return f"v1: {item}"

DOMAIN = "test"
''')

        sys.path.insert(0, str(plugin_dir))
        try:
            plugin = importlib.import_module("plugin")

            loader = ToolsLoader(cache_dir=str(cache_dir), use_cache=True)

            # Step 1: Initial load - populate cache
            loader.load_from_module(plugin)
            mtime_v1 = plugin_file.stat().st_mtime

            # Step 2: Modify file BUT preserve mtime (git checkout simulation)
            plugin_file.write_text('''
from udan.core_tools_loading.api_annotated import annotated

@annotated
def test_operator(item: str, new_param: str = "added") -> str:
    """Test operator v2 with new param."""
    return f"v2: {item}, new={new_param}"

DOMAIN = "test"
''')
            os.utime(plugin_file, (mtime_v1, mtime_v1))  # Reset mtime
            importlib.reload(plugin)

            # Step 3: Load again - cache NOT invalidated (BUG!)
            metadata_fns_v2 = loader.load_from_module(plugin)
            v2_props = set(metadata_fns_v2[0][0].parameters.get("properties", {}).keys())

            # Cache should be invalidated even when mtime unchanged
            # This assertion FAILS with current buggy code, will PASS after fix
            assert "new_param" in v2_props, (
                f"Cache NOT invalidated when mtime unchanged! Expected {{'item', 'new_param'}}, got {v2_props}"
            )

        finally:
            sys.path.remove(str(plugin_dir))
            sys.modules.pop("plugin", None)
