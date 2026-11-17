"""Tag grouping plugins for udan.

Provides operators that organize items into groups based on the global
frequency of tags found on the items themselves.
"""

from collections import Counter, defaultdict
from typing import Annotated, Any

from udan.core.api_forests import Item
from udan.core_tools_loading.api_annotated import annotated
from udan.core_tools_loading.api_types import Group

DOMAIN = "tags"

# Synthetic filter_tags marker: with it, the item must carry no tags besides the required ones.
NO_OTHER_TAGS_TAG = "$no-other-tags"
# Underscore spelling kept working: it predates the "$" form and needs no query quoting.
_NO_OTHER_TAGS_TAG_LEGACY = "_no-other-tags"
_NO_OTHER_TAGS_TAGS = (NO_OTHER_TAGS_TAG, _NO_OTHER_TAGS_TAG_LEGACY)


def _normalize_tag(tag: object) -> str:
    """Normalize a tag to a stable string key."""
    return str(tag).strip()


def _get_tags(item: Item, field: str) -> list[str]:
    """Extract the normalized, non-empty list of tags from an item.

    Supports both dict items (``item[field]``) and objects (``item.<field>``).
    Items with no tags (or a non-list tags value) produce an empty list.
    """
    if isinstance(item, dict):
        if "item" in item and isinstance(item["item"], dict):
            item = item["item"]
        raw = item.get(field, [])
    else:
        raw = getattr(item, field, [])

    if not isinstance(raw, (list, tuple, set)):
        return []

    tags: list[str] = []
    for tag in raw:
        normalized = _normalize_tag(tag)
        if normalized and normalized not in tags:
            tags.append(normalized)
    return tags


@annotated(
    meta={
        "tool_type": "replacer",
        "is_nested": True,
        "output_type": "any",
        "aliases": ["group_by_tags_max"],
    }
)
def group_by_tags_max(
    nodes: list[Any],
    field: str = "tags",
    collapse_on: int = 1,
) -> list[tuple[int, Item]]:
    """Group items by their most-popular tag, collapsing small groups into "others".

    Tags are counted across all items with a global :class:`Counter`. The tags
    are then ordered from most to least frequent (ties broken alphabetically).
    Each item is assigned to the most frequent tag it carries; any tag whose
    total frequency is ``<= collapse_on`` (and items with no tags) are collapsed
    into a single ``"others"`` group.

    The result is a list of ``(depth, Group)`` pairs: each kept tag becomes a
    :class:`~udan.core_tools_loading.api_types.Group` (ordered by descending frequency) and, when
    present, the collapsed items form a final ``Group(key="others")``.

    The original items are kept as children of their group node, so this
    operator behaves like a grouper (``group_by_field``) in queries, while
    requiring access to all items at once to compute global tag frequencies.

    Args:
        nodes: Input item nodes (e.g. from any inserter producing tagged items).
        field: Name of the field/attribute holding the tags list (default "tags").
        collapse_on: Frequency threshold. Tags appearing more than this many
            times form their own group; the rest collapse into "others"
            (default 1).

    Returns:
        List of ``(depth, item)`` pairs where each ``item`` is a ``Group``.

    Examples:
        Items with tags ``(a, b)``, ``(b, c)``, ``(d)`` (Counter: b=2, a/c/d=1)
        with ``collapse_on=1`` produce groups ``(b)`` and ``(others)``.
    """
    items: list[Item] = []
    for node in nodes:
        items.append(node.item if hasattr(node, "item") else node)

    counter: Counter = Counter()
    tagged: list[tuple[Item, list[str]]] = []
    for item in items:
        tags = _get_tags(item, field)
        counter.update(tags)
        tagged.append((item, tags))

    def _key(tag: str) -> tuple[int, str]:
        # Most frequent first; ties broken alphabetically for stable ordering.
        return (-counter[tag], tag)

    ordered_tags = sorted(counter, key=_key)

    # Index of each tag in the global frequency ordering (ties alphabetical).
    rank = {tag: i for i, tag in enumerate(ordered_tags)}

    def _primary_tag(tags: list[str]) -> str | None:
        """Return the tag that ranks earliest in the global frequency order."""
        if not tags:
            return None
        return min(tags, key=lambda t: rank[t])

    # Partition items into kept groups (freq > collapse_on) and "others".
    kept: list[str] = [tag for tag in ordered_tags if counter[tag] > collapse_on]
    kept_set = set(kept)

    groups: dict[str, list[Item]] = {tag: [] for tag in kept}
    others: list[Item] = []

    for item, tags in tagged:
        primary = _primary_tag(tags)
        if primary is not None and primary in kept_set:
            groups[primary].append(item)
        else:
            others.append(item)

    result: list[tuple[int, Item]] = []
    for order, tag in enumerate(kept):
        result.append((0, Group(key=tag, order=order)))
        for item in groups[tag]:
            result.append((1, item))
    if others:
        result.append((0, Group(key="others", order=len(kept))))
        for item in others:
            result.append((1, item))

    return result


@annotated(
    meta={
        "tool_type": "replacer",
        "is_nested": True,
        "output_type": "any",
        "supported_renders": ["tags_tree_item"],
    }
)
def show_tags_tree(
    nodes: list[Any],
    field: str = "tags",
) -> list[tuple[int, dict]]:
    """Show a hierarchical tag tree where tags are nested under co-occurring tags.

    Tags are counted across all input items with a global :class:`Counter`.
    The first level contains all tags ordered by frequency. The second level
    under each tag contains other tags that co-occur in items with that tag,
    ordered by co-occurrence frequency.

    Args:
        nodes: Input item nodes (e.g. from any inserter producing tagged items).
        field: Name of the field/attribute holding the tags list (default "tags").

    Returns:
        List of ``(depth, item)`` pairs where ``item`` is
        ``{"name": <tag>, "frequency": <count>}``.
        Depth 0 = top level tags, Depth 1 = co-occurring tags under each tag.

    Examples:
        Items with tags ``(a, b)``, ``(a, b)``, ``(c)`` produce level 0
        ``a (2)``, ``b (2)``, ``c (1)`` with ``b (2)`` nested under ``a``,
        ``a (2)`` under ``b``, and nothing under ``c``.
    """
    items: list[Item] = []
    for node in nodes:
        items.append(node.item if hasattr(node, "item") else node)

    counter: Counter = Counter()
    cooccurrences: defaultdict[str, Counter] = defaultdict(Counter)

    for item in items:
        item_tags = _get_tags(item, field)
        counter.update(item_tags)
        for tag in item_tags:
            cooccurrences[tag].update(t for t in item_tags if t != tag)

    result: list[tuple[int, dict]] = []
    for tag, freq in counter.most_common():
        result.append((0, {"name": tag, "frequency": freq}))
        for co_tag, co_freq in cooccurrences[tag].most_common():
            result.append((1, {"name": co_tag, "frequency": co_freq}))

    return result


@annotated(meta={"item_type": "dict", "tool_type": "render"})
def tags_tree_item(item: dict, indent: str = "") -> str:
    """Render a tag node as an org list line with its frequency.

    Format: ``- name :: (frequency)``.

    Args:
        item: Dict with ``name`` and ``frequency`` keys (from :func:`show_tags_tree`).
        indent: Indentation string reflecting tree depth (default: "").

    Returns:
        Formatted string, e.g. ``- fruit :: (6)``.
    """
    if isinstance(item, dict):
        return f"{indent}- {item.get('name', '')} :: ({item.get('frequency', 0)})"
    return f"{indent}- {item}"


@annotated(meta={"tool_type": "grouper", "item_type": "any"})
def group_by_tags_fixed(
    item: Item,
    tags_lists: Annotated[list[str], "vararg"],
    field: str = "tags",
) -> Group:
    """Group items into user-specified fixed tag groups, with a fallback "others".

    This is a per-item grouper (unlike :func:`group_by_tags_max`): each item is
    assigned to the first group, in the order the groups are given, whose tags
    are all present on the item. Tags are read from the item's ``field``
    field/attribute (``"tags"`` by default, see ``--field``).

    Args:
        item: The item to assign to a group.
        tags_lists: Group definitions passed as positional strings, each
            listing one or more tags separated by commas (e.g. ``"a,b"``).
            An item belongs to a group when it carries ALL of that group's tags.
        field: Name of the field/attribute holding the tags list (default "tags").

    Returns:
        A :class:`~udan.core_tools_loading.api_types.Group` whose key is the normalized
        comma-joined label (or ``"<others>"``) and whose ``order`` reflects
        the position of the matching group spec in ``tags_lists`` (the
        fallback sorts last).

    Examples:
        ``group_by_tags_fixed "a,b" "b,c" "d"`` groups an item tagged ``[a, b]``
        into ``"a,b"``, an item tagged ``[d]`` into ``"d"``, and everything else
        into ``"<others>"``. Pass ``--field=other_fields`` to read the tags from
        a different field.
    """
    tags = set(_get_tags(item, field))
    for order, group_spec in enumerate(tags_lists):
        wanted = [w for w in (t.strip() for t in group_spec.split(",")) if w]
        if wanted and all(tag in tags for tag in wanted):
            return Group(key=",".join(wanted), order=order)
    return Group(key="<others>", order=len(tags_lists))


@annotated(meta={"tool_type": "filter", "item_type": "any"})
def filter_tags(
    item: Item,
    tags: Annotated[list[str], "vararg"],
    field: str = "tags",
) -> bool:
    """Keep only items whose tags satisfy all include/exclude conditions.

    Each positional tag argument is a single tag name. A tag prefixed with
    ``-`` is an exclusion: the item must NOT carry it. Without the prefix the
    item must carry the tag. All conditions must hold for the item to pass.

    The synthetic tag ``$no-other-tags`` adds a strictness condition: the item
    must carry no tags other than the required ones (its tag set must be
    exactly the required set). With it as the only condition, only untagged
    items pass. Because ``$`` starts a variable reference in queries, spell it
    ``"$no-other-tags"`` (quoted) there; the older ``_no-other-tags`` spelling
    is still accepted and needs no quotes.

    Args:
        item: The item to check.
        tags: Tag conditions (vararg), e.g. ``"a"`` requires ``a`` and
            ``"-b"`` forbids ``b``.
        field: Name of the field/attribute holding the tags list (default "tags").

    Returns:
        True if the item has all required tags and none of the excluded ones
        (and, with ``$no-other-tags``, no other tags besides the required ones).

    Examples:
        ``filter_tags a -b c`` keeps only items tagged ``a`` and ``c``
        (in any combination with other tags) that are NOT tagged ``b``.
        ``filter_tags a b $no-other-tags`` matches an item tagged ``[a, b]``
        but NOT an item tagged ``[a, b, c]``.
    """
    item_tags = set(_get_tags(item, field))
    required = []
    excluded = []
    no_other_tags = False
    for spec in tags:
        normalized = spec.strip()
        if not normalized:
            continue
        if normalized in _NO_OTHER_TAGS_TAGS:
            no_other_tags = True
        elif normalized.startswith("-"):
            excluded.append(normalized[1:].strip())
        else:
            required.append(normalized)
    return (
        all(tag in item_tags for tag in required)
        and not any(tag in item_tags for tag in excluded)
        and (not no_other_tags or item_tags <= set(required))
    )


@annotated(meta={"tool_type": "filter", "item_type": "any"})
def has_tag(item: Item, tag: str, field: str = "tags") -> bool:
    """Keep the item when it carries the given tag.

    Works with any item shape: dicts (``item[field]``) and objects
    (``item.<field>``, e.g. an org item's ``tags``). Items with no tags
    (or a non-list tags value) never match.

    Args:
        item: The item to check.
        tag: Tag to look for.
        field: Name of the field/attribute holding the tags list (default "tags").

    Returns:
        True if the item has the specified tag.

    Examples:
        ``has_tag python`` keeps only items tagged ``python``, whatever the
        inserter that produced them. Pass ``--field=other_fields`` to read
        the tags from a different field.
    """
    return _normalize_tag(tag) in _get_tags(item, field)
