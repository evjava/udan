"""Attribute caching infrastructure using joblib."""

import shutil
from hashlib import md5
from pathlib import Path
from typing import Any

from joblib import dump, load  # type: ignore[import-untyped]

from udan.attributes.api_attribute_cache import AttributeCacheAPI
from udan.core.api_attributes import AttributeValue
from udan.core.api_exec_context import ExecContextAPI
from udan.core.api_logger import LoggerAPI
from udan.core.utils_collections import ilen


class AttributeCache(AttributeCacheAPI):
    """Cache for attribute values to avoid recalculating unchanged items.

    Uses joblib for efficient storage with separate cache files per attribute.
    Each attribute identity gets its own subdirectory.
    The cache works with string keys - the caller is responsible for
    serializing attribute descriptors to strings.
    """

    def __init__(self, cache_path: str | None, logger: LoggerAPI | None) -> None:
        """Initialize cache.

        Args:
            cache_path: Base path for persistent cache directory. If None, caching is disabled.
                        Supports ~ for home directory expansion.
            logger: Logger instance for debug logging about cache errors.
        """
        self._cache_path = Path(cache_path).expanduser() if cache_path else None
        self._logger = logger

    def _get_cache_dir(self, attr_identity: str) -> Path | None:
        """Get cache directory for a specific attribute identity.

        Each attribute identity gets its own subdirectory.

        Args:
            attr_identity: Attribute identity string (e.g., "file_created")

        Returns:
            Path to cache directory, or None if cache_path is not configured
        """
        if not self._cache_path:
            return None
        attr_cache_dir = self._cache_path / attr_identity
        attr_cache_dir.mkdir(parents=True, exist_ok=True)
        return attr_cache_dir

    def _get_cache_file_path(self, attr_identity: str, attr_key: str, cache_key_value: str) -> Path | None:
        """Get the path to a cache file for a specific cache key.

        Args:
            attr_identity: Attribute identity for directory name
            attr_key: Full attribute key including name and args (for hashing)
            cache_key_value: Cache key value from the cache attribute

        Returns:
            Path to cache file, or None if cache_path is not configured
        """
        cache_dir = self._get_cache_dir(attr_identity)
        if cache_dir is None:
            return None

        # Create a hash of both the attr_key and cache_key_value for unique filename
        key_hash = md5(f"{attr_key}:{cache_key_value}".encode()).hexdigest()
        return cache_dir / f"{key_hash}.pkl"

    def _load_from_cache_file(self, cache_file: Path, ctx: ExecContextAPI) -> Any | None:
        """Load value from a cache file using joblib.

        Args:
            cache_file: Path to cache file
            ctx: Execution context for query-time logging

        Returns:
            Cached value, or None if file doesn't exist or load fails
        """
        try:
            if cache_file.exists():
                return load(cache_file)
        except Exception as e:
            ctx.debug(f"Failed to load from cache file {cache_file}: {e}")
        return None

    def _save_to_cache_file(self, cache_file: Path, value: AttributeValue, ctx: ExecContextAPI) -> None:
        """Save value to a cache file using joblib.

        Args:
            cache_file: Path to cache file
            value: Value to save
            ctx: Execution context for query-time logging
        """
        try:
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            dump(value, cache_file)
        except Exception as e:
            ctx.debug(f"Failed to save to cache file {cache_file}: {e}")

    def get_value(self, attr_identity: str, attr_key: str, cache_key_value: str, ctx: ExecContextAPI) -> Any | None:
        """Get cached value for an attribute.

        Args:
            attr_identity: Attribute identity for directory name
            attr_key: Full attribute key including name and args (serialized by caller)
            cache_key_value: Value from the cache attribute to look up
            ctx: Execution context for query-time logging

        Returns:
            Cached value if found, None otherwise
        """
        cache_file = self._get_cache_file_path(attr_identity, attr_key, cache_key_value)
        if cache_file is None:
            return None

        return self._load_from_cache_file(cache_file, ctx)

    def set_value(
        self, attr_identity: str, attr_key: str, cache_key_value: str, value: AttributeValue, ctx: ExecContextAPI
    ) -> None:
        """Store attribute value in cache.

        Args:
            attr_identity: Attribute identity for directory name
            attr_key: Full attribute key including name and args (serialized by caller)
            cache_key_value: Value from the cache attribute
            value: Attribute value to cache
            ctx: Execution context for query-time logging
        """
        cache_file = self._get_cache_file_path(attr_identity, attr_key, cache_key_value)
        if cache_file is not None:
            self._save_to_cache_file(cache_file, value, ctx)

    def clear_cache(self) -> None:
        """Clear all cached values."""
        if self._cache_path:
            try:
                cache_dir = Path(self._cache_path)
                if cache_dir.exists():
                    shutil.rmtree(cache_dir)
                    if self._logger:
                        self._logger.debug("Cleared attribute cache")
            except Exception as e:
                if self._logger:
                    self._logger.debug(f"Failed to clear cache directory {cache_dir}: {e}")

    def _size(self) -> int:
        """Return number of cached entries.

        Returns:
            Number of cached entries across all attributes
        """
        if not self._cache_path:
            return 0

        try:
            cache_dir = Path(self._cache_path)
            if not cache_dir.exists():
                return 0
            # Count cache files across all attribute subdirectories
            return sum(ilen(attr_dir.glob("*.pkl")) for attr_dir in cache_dir.iterdir() if attr_dir.is_dir())
        except Exception as e:
            if self._logger:
                self._logger.debug(f"Failed to calculate cache size for {cache_dir}: {e}")
            return 0
