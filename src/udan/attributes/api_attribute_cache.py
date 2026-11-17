"""Public API for attribute caching.

This module defines the public API interface for attribute caching.
"""

from __future__ import annotations

from typing import Any

from udan.core.api_exec_context import ExecContextAPI


class AttributeCacheAPI:
    """API interface for attribute caching.

    This class defines the public API for caching attribute values to avoid
    recalculating unchanged items. The cache uses joblib for efficient storage
    with separate cache files per attribute.

    Each attribute identity gets its own subdirectory. The cache works with
    string keys - the caller is responsible for serializing attribute descriptors
    to strings.
    """

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
        raise NotImplementedError

    def set_value(
        self, attr_identity: str, attr_key: str, cache_key_value: str, value: Any, ctx: ExecContextAPI
    ) -> None:
        """Store attribute value in cache.

        Args:
            attr_identity: Attribute identity for directory name
            attr_key: Full attribute key including name and args (serialized by caller)
            cache_key_value: Value from the cache attribute
            value: Attribute value to cache
            ctx: Execution context for query-time logging
        """
        raise NotImplementedError

    def clear_cache(self) -> None:
        """Clear all cached values."""
        raise NotImplementedError
