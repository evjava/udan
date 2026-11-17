"""Utility functions for filesystem operations."""

import hashlib
import os
from datetime import datetime
from importlib import import_module
from pathlib import Path


def calc_file_hash_blake2s(path: Path) -> str:
    """Fast file hash using blake2s with 64-bit digest.

    Args:
        path: Path to file to hash

    Returns:
        Hex digest of file hash
    """
    h = hashlib.blake2s(digest_size=8)
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


def get_module_update_time(module) -> str:
    """Get the modification time of a module as a string.

    Args:
        module: Module object to get time for

    Returns:
        String representation of modification time in format yy-mm-dd--HH-MM-SS-ffffff
    """
    module_path = module.__file__
    module_time = os.path.getmtime(module_path)
    module_dt = datetime.fromtimestamp(module_time)
    # Use microsecond precision to avoid cache collisions when file is modified rapidly
    module_dt_fmt = datetime.strftime(module_dt, "%y-%m-%d--%H-%M-%S-%f")
    return module_dt_fmt


def get_module_name_update_time(module_name: str) -> str:
    """Get the modification time of a module by its name.

    Args:
        module_name: Module name (e.g., 'udan.core_tools_loading.impl_utils_tools_loader')

    Returns:
        String representation of modification time in format yy-mm-dd--HH-MM-SS-ffffff
    """
    module = import_module(module_name)
    return get_module_update_time(module)
