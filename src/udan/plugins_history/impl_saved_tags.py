"""Tag normalization for saved queries.

Tags travel as a normalized space-separated string in storage and as a
bracketed comma-separated group in renders; these two helpers are the
single conversion point, so "[a, b]", "a b" and ["a", "b"] all mean the
same two tags.
"""


def split_tags(tags: str | None) -> list[str]:
    """Split a stored/rendered tags string into a normalized tag list.

    Accepts whitespace- and comma-separated tags, optionally wrapped in
    brackets; duplicates are dropped, order is preserved.

    Args:
        tags: Raw tags string (None or "" -> no tags)

    Returns:
        Normalized tag list
    """
    if not tags:
        return []
    normalized: list[str] = []
    for tag in tags.replace(",", " ").replace("[", " ").replace("]", " ").split():
        if tag not in normalized:
            normalized.append(tag)
    return normalized


def join_tags(tags: str | list[str] | None) -> str:
    """Normalize tags into the stored space-separated string.

    Args:
        tags: Tag list or raw string (None, "" or [] -> "")

    Returns:
        Normalized space-separated tags string
    """
    if not tags:
        return ""
    if isinstance(tags, str):
        return " ".join(split_tags(tags))
    return " ".join(split_tags(" ".join(tags)))
