"""Demo plugin with vegetable data stored as pydantic models: inserters, attributes, extenders, and a render.

Unlike plugins_fruits, which stores plain dicts, vegetables are instances of
Vegetable(BaseModel), so universal tools (sort_by_field, filter_field,
group_by_field, map_field) must work on objects as well as on dicts.
"""

import zlib
from typing import Any

from pydantic import BaseModel, ConfigDict

from udan.core_tools_loading.api_annotated import annotated
from udan.renders.api_renders import SHAPE_ITEM

DOMAIN = "vegetables"


class Vegetable(BaseModel):
    """A vegetable item.

    Attributes:
        id: Numeric identifier
        name: Vegetable name
        calories: Calories per 100 g, None when unknown
        color: Vegetable color, None when unknown
        ftype: Vegetable kind (tuber, root, cruciferous, leafy)
        tags: Descriptive tags
        quantity: Eaten quantity, set only on menu entries
    """

    model_config = ConfigDict(frozen=True)

    id: int = 0
    name: str = ""
    calories: int | None = None
    color: str | None = None
    ftype: str = "vegetable"
    tags: list[str] = []
    quantity: int | None = None


ALL_VEGETABLES: list[Vegetable] = [
    Vegetable(id=1, name="potato", calories=77, color="brown", ftype="tuber", tags=["vegetable", "starchy"]),
    Vegetable(id=2, name="carrot", calories=41, color="orange", ftype="root", tags=["vegetable", "sweet", "crunchy"]),
    Vegetable(
        id=3, name="broccoli", calories=34, color="green", ftype="cruciferous", tags=["vegetable", "green", "fresh"]
    ),
    Vegetable(id=4, name="spinach", calories=23, color="green", ftype="leafy", tags=["vegetable", "green", "leafy"]),
    # mandrake is the mythical screaming root: intentionally untagged, like
    # ambrosia in plugins_fruits
    Vegetable(id=5, name="mandrake", calories=None, color=None, ftype="vegetable", tags=[]),
]

VEGETABLE_TRANSLATIONS_RU = {
    "potato": "картофель",
    "carrot": "морковь",
    "broccoli": "брокколи",
    "spinach": "шпинат",
}

VEGETABLE_NUTRITION_DATA = {
    "potato": {"proteins": 2.0, "fats": 0.1, "carbs": 17.0},
    "carrot": {"proteins": 0.9, "fats": 0.2, "carbs": 9.6},
    "broccoli": {"proteins": 2.8, "fats": 0.4, "carbs": 6.6},
    "spinach": {"proteins": 2.9, "fats": 0.4, "carbs": 3.6},
}

VEGETABLE_COSTS = {
    "potato": 0.40,
    "carrot": 0.30,
    "broccoli": 1.50,
    "spinach": 1.80,
}

# Vegetable -> emoji for render_vegetable, keyed by the vegetable name. Written as
# unicode escapes to keep emoji characters out of the source. Vegetables missing
# here render as the bare name (mandrake exercises that fallback in tests).
VEGETABLE_EMOJI = {
    "potato": "\U0001f954",  # potato
    "carrot": "\U0001f955",  # carrot
    "broccoli": "\U0001f966",  # broccoli
    "spinach": "\U0001f96c",  # leafy green
}

# Day -> vegetables eaten that day with quantities (day-5 intentionally empty)
VEGETABLES_EATEN_BY_DAY = {
    "day-1": [Vegetable(name="potato", quantity=1)],
    "day-2": [Vegetable(name="carrot", quantity=1)],
    "day-3": [Vegetable(name="potato", quantity=2), Vegetable(name="broccoli", quantity=1)],
    "day-4": [Vegetable(name="carrot", quantity=1), Vegetable(name="spinach", quantity=1), Vegetable(name="mandrake")],
    "day-5": [],
}

# Number of groups used by similar_vegetables to bucket vegetables by name
VEGETABLE_SIMILAR_GROUPS = 4


def _vegetable_name(item: Any) -> str | None:
    """Extract the vegetable name from an item.

    Args:
        item: Candidate vegetable model

    Returns:
        Value of the name field when it is a Vegetable, None otherwise
    """
    if not isinstance(item, Vegetable):
        return None
    return item.name


def _similarity_bucket(name: str) -> int:
    """Bucket a vegetable name into one of VEGETABLE_SIMILAR_GROUPS groups.

    crc32 is used instead of built-in hash() because str hashing is salted per
    interpreter run, which would make the grouping differ between processes.

    Args:
        name: Vegetable name to bucket

    Returns:
        Bucket index in range(VEGETABLE_SIMILAR_GROUPS)
    """
    return zlib.crc32(name.encode()) % VEGETABLE_SIMILAR_GROUPS


@annotated(
    meta={
        "tool_type": "inserter",
        "aliases": ["vegetables"],
        "supported_renders": ["vegetable"],
        "output_type": "Vegetable",
        "output_semantic": "vegetable",
    }
)
def insert_vegetables(pattern: str = "") -> list[Vegetable]:
    """Insert vegetable items with id, name, calories, color, ftype, and tags.

    Args:
        pattern: Optional pattern to filter vegetables by name (e.g., "ro" for carrot and broccoli)

    Returns:
        List of Vegetable models with id, name, calories, color, ftype, and tags
    """
    if not pattern:
        return ALL_VEGETABLES

    pattern_lower = pattern.lower()
    return [vegetable for vegetable in ALL_VEGETABLES if pattern_lower in vegetable.name.lower()]


@annotated(meta={"attribute_type": "simple"})
def vegetable_translate_ru(item: Vegetable) -> str | None:
    """Translate vegetable name to Russian.

    Args:
        item: Vegetable model

    Returns:
        Russian translation of vegetable name, or None if not found
    """
    name = _vegetable_name(item)
    if name is None:
        return None
    return VEGETABLE_TRANSLATIONS_RU.get(name)


@annotated(meta={"attribute_type": "simple", "dependencies": ["vegetable_translate_ru"]})
def vegetable_translate_ru_upper(item: Vegetable, vegetable_translate_ru: str | None = None) -> str | None:
    """Translate vegetable name to Russian and convert to uppercase.

    This attribute depends on vegetable_translate_ru and transforms its output.

    Args:
        item: Vegetable model
        vegetable_translate_ru: Russian translation from vegetable_translate_ru attribute (injected)

    Returns:
        Uppercase Russian translation of vegetable name, or None if translation not found
    """
    if vegetable_translate_ru is None:
        return None
    return vegetable_translate_ru.upper()


@annotated(meta={"attribute_type": "simple"})
def vegetable_pfc(item: Vegetable) -> dict | None:
    """Calculate PFC (proteins, fats, carbs) for a vegetable.

    Args:
        item: Vegetable model

    Returns:
        Dict with proteins, fats, and carbs values in grams, or None if not found
    """
    name = _vegetable_name(item)
    if name is None:
        return None
    return VEGETABLE_NUTRITION_DATA.get(name)


@annotated(meta={"attribute_type": "simple"})
def vegetable_cost(item: Vegetable) -> float | None:
    """Get cost per unit for a vegetable.

    Args:
        item: Vegetable model

    Returns:
        Cost per unit in dollars, or None if not found
    """
    name = _vegetable_name(item)
    if name is None:
        return None
    return VEGETABLE_COSTS.get(name)


@annotated(
    meta={
        "tool_type": "extender",
        "item_type": "Vegetable",
        "output_type": "Vegetable",
        "output_semantic": "vegetable",
    }
)
def similar_vegetables(item: Vegetable) -> list[Vegetable]:
    """Extend each vegetable with 2-3 similar vegetables.

    Similarity is based on crc32(name) % 4. Vegetables with the same bucket value
    are considered similar (deterministic grouping, stable across runs).

    Args:
        item: Vegetable model

    Returns:
        List of 2-3 similar Vegetable models with id, name, calories, color, ftype, and tags

    Examples:
        - For potato -> Vegetables with the same crc32(name) % 4 bucket
        - For carrot -> Vegetables with the same crc32(name) % 4 bucket
    """
    name = _vegetable_name(item)
    if name is None:
        return []

    bucket = _similarity_bucket(name)
    similar = [v for v in ALL_VEGETABLES if v.name != name and _similarity_bucket(v.name) == bucket]
    return similar[:3]


@annotated(meta={"tool_type": "extender", "item_type": "str", "output_type": "Vegetable"})
def extend_menu_vegetables(item: str) -> list[Vegetable]:
    """Extend menu days with eaten vegetables data.

    For each day, returns the vegetables eaten that day with their quantities.

    Args:
        item: The day identifier (e.g., "day-1", "day-2", etc.)

    Returns:
        List of Vegetable models with name and quantity
    """
    return VEGETABLES_EATEN_BY_DAY.get(item, [])


@annotated(
    meta={
        "item_type": "Vegetable",
        "item_semantic": "vegetable",
        "tool_type": "render",
        "aliases": ["vegetable"],
        "shape": SHAPE_ITEM,
    }
)
def render_vegetable(item: Vegetable, indent: str = "", attrs: dict[str, Any] | None = None) -> str:
    """Render a vegetable as its emoji and name.

    Declared item semantic "vegetable", matching insert_vegetables
    (output_semantic "vegetable"), so `vegetables, :` recommends this render
    without any supported_renders declaration.

    Args:
        item: Vegetable model with a name field
        indent: Indentation string
        attrs: Attributes dict (unused, part of the render signature)

    Returns:
        "<emoji> <name>", or the bare name when the vegetable has no emoji in VEGETABLE_EMOJI
    """
    name = item.name if isinstance(item, Vegetable) else None
    if not name:
        return f"{indent}{item}"
    emoji = VEGETABLE_EMOJI.get(name)
    if not emoji:
        return f"{indent}{name}"
    return f"{indent}{emoji} {name}"
