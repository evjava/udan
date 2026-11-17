"""Utility classes for collection and iteration behavior.

Reusable iterable/collection helpers shared across the core and the packages:
the operators engine replays one-shot sources with CachedIterable, the attribute
cache counts with ilen.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator


class CachedIterable[T]:
    """Iterable over a one-shot source: every pass replays a shared cache.

    Items are pulled from the source once and only as far as the furthest pass
    needs, so a consumer that stops early (islice cap) stops the source as well.
    This keeps the applicator contract "input may be iterated more than once"
    valid for lazy stages, and lets per-item tools stream instead of being
    materialized between chain steps.

    Note:
        not thread-safe: passes must not be iterated concurrently.
    """

    def __init__(self, source: Iterable[T]) -> None:
        self._source = iter(source)
        self._cache: list[T] = []
        self._exhausted = False

    def __iter__(self) -> Iterator[T]:
        index = 0
        while True:
            if index < len(self._cache):
                yield self._cache[index]
            elif self._exhausted:
                return
            else:
                try:
                    item = next(self._source)
                except StopIteration:
                    self._exhausted = True
                    return
                self._cache.append(item)
                yield item
            index += 1


def ilen[T](iterable: Iterable[T]) -> int:
    """Return the number of items in an iterable, consuming it.

    Backport of more_itertools.ilen.

    Args:
        iterable: Iterable to count, may be a one-shot iterator.

    Returns:
        Number of items produced by the iterable.
    """
    return sum(1 for _ in iterable)
