from collections.abc import Iterable
from typing import TypeVar

T = TypeVar("T")


def flatten(xss: Iterable[Iterable[T]]) -> list[T]:
    return [x for xs in xss for x in xs]


def normalize_fexpr(fexpr):
    res = fexpr.strip().lower()
    return res


def split_by(text, separator) -> list[str]:
    return text.split(separator) if text else []


def split_and_normalize(text) -> list[str]:
    text = text.strip()
    return list(map(normalize_fexpr, split_by(text, ",")))


def cut_if_needed(text: str, max_length: int) -> str:
    """Cut text to max_length if it exceeds that length, adding '...' suffix.

    The returned string will be at most max_length characters (including the '...'
    suffix if truncation occurs).

    Args:
        text: The text to potentially cut
        max_length: Maximum total length (including '...' suffix if added)

    Returns:
        Original text if len(text) <= max_length, otherwise text[:max_length - 3] + "..."
    """
    if len(text) <= max_length:
        return text
    return text[: max_length - 3] + "..."
