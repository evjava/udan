"""Demo plugin with fruit data: inserters, attributes, extenders, and a render."""

import zlib
from typing import Any

from udan.core.api_forests import Item
from udan.core_tools_loading.api_annotated import annotated
from udan.renders.api_renders import SHAPE_ITEM

DOMAIN = "fruits"

# Shared data
ALL_FRUITS: list[dict[str, Any]] = [
    {"id": 1, "name": "apple", "calories": 52, "color": "red", "ftype": "fruit", "tags": ["fruit", "sweet", "fresh"]},
    {
        "id": 2,
        "name": "orange",
        "calories": 47,
        "color": "orange",
        "ftype": "fruit",
        "tags": ["fruit", "sweet", "citrus"],
    },
    {
        "id": 3,
        "name": "banana",
        "calories": 89,
        "color": "yellow",
        "ftype": "fruit",
        "tags": ["fruit", "sweet", "tropical"],
    },
    {
        "id": 4,
        "name": "strawberry",
        "calories": 32,
        "color": "red",
        "ftype": "berry",
        "tags": ["berry", "sweet", "fresh"],
    },
    {"id": 5, "name": "blueberry", "calories": 57, "color": "blue", "ftype": "berry", "tags": ["berry", "fresh"]},
    {"id": 6, "name": "raspberry", "calories": 52, "color": "red", "ftype": "berry", "tags": ["berry", "fresh"]},
    {"id": 7, "name": "grape", "calories": 62, "color": "purple", "ftype": "fruit", "tags": ["fruit", "sweet"]},
    {"id": 8, "name": "pineapple", "calories": 50, "color": "yellow", "ftype": "fruit", "tags": ["fruit", "tropical"]},
    {
        "id": 9,
        "name": "mango",
        "calories": 60,
        "color": "orange",
        "ftype": "fruit",
        "tags": ["fruit", "tropical", "sweet"],
    },
    # ambrosia is intentionally untagged (mythical fruit)
    {"id": 10, "name": "ambrosia", "calories": None, "color": None, "ftype": "fruit", "tags": []},
]

TRANSLATIONS_RU = {
    "apple": "яблоко",
    "orange": "апельсин",
    "banana": "банан",
    "strawberry": "клубника",
    "blueberry": "черника",
    "raspberry": "малина",
    "grape": "виноград",
    "pineapple": "ананас",
    "mango": "манго",
}

NUTRITION_DATA = {
    "apple": {"proteins": 0.3, "fats": 0.2, "carbs": 14.0},
    "orange": {"proteins": 0.9, "fats": 0.1, "carbs": 12.0},
    "banana": {"proteins": 1.1, "fats": 0.3, "carbs": 23.0},
    "strawberry": {"proteins": 0.7, "fats": 0.3, "carbs": 7.7},
    "blueberry": {"proteins": 0.7, "fats": 0.3, "carbs": 14.5},
    "raspberry": {"proteins": 1.2, "fats": 0.7, "carbs": 12.0},
    "grape": {"proteins": 0.7, "fats": 0.2, "carbs": 18.0},
    "pineapple": {"proteins": 0.5, "fats": 0.1, "carbs": 13.0},
    "mango": {"proteins": 0.8, "fats": 0.4, "carbs": 15.0},
}

FRUIT_COSTS = {
    "apple": 1.20,
    "orange": 0.80,
    "banana": 0.50,
    "strawberry": 3.50,
    "blueberry": 4.00,
    "raspberry": 3.80,
    "grape": 2.50,
    "pineapple": 2.00,
    "mango": 1.80,
}

# Fruit -> emoji for render_fruit, keyed by the fruit name. Written as unicode
# escapes to keep emoji characters out of the source. Fruits missing here render
# as the bare name (raspberry and ambrosia exercise that fallback in tests).
FRUIT_EMOJI = {
    "apple": "\U0001f34e",  # red apple
    "orange": "\U0001f34a",  # tangerine
    "banana": "\U0001f34c",  # banana
    "strawberry": "\U0001f353",  # strawberry
    "blueberry": "\U0001fad0",  # blueberries
    "grape": "\U0001f347",  # grapes
    "pineapple": "\U0001f34d",  # pineapple
    "mango": "\U0001f96d",  # mango
}

# Day -> fruits eaten that day with quantities (day-5 intentionally empty)
FRUITS_EATEN_BY_DAY = {
    "day-1": [{"name": "apple", "quantity": 1}],
    "day-2": [{"name": "orange", "quantity": 1}],
    "day-3": [{"name": "apple", "quantity": 2}, {"name": "orange", "quantity": 1}],
    "day-4": [{"name": "apple", "quantity": 1}, {"name": "grape", "quantity": 1}, {"name": "mango", "quantity": 1}],
    "day-5": [],
}

# Number of groups used by similar_fruits to bucket fruits by name
FRUIT_SIMILAR_GROUPS = 4


def _fruit_name(item: Any) -> str | None:
    """Extract the fruit name from an item dict.

    Args:
        item: Candidate fruit dict

    Returns:
        Value of the "name" key when it is a string, None otherwise
    """
    if not isinstance(item, dict):
        return None
    name = item.get("name")
    return name if isinstance(name, str) else None


def _similarity_bucket(name: str) -> int:
    """Bucket a fruit name into one of FRUIT_SIMILAR_GROUPS groups.

    crc32 is used instead of built-in hash() because str hashing is salted per
    interpreter run, which would make the grouping differ between processes.

    Args:
        name: Fruit name to bucket

    Returns:
        Bucket index in range(FRUIT_SIMILAR_GROUPS)
    """
    return zlib.crc32(name.encode()) % FRUIT_SIMILAR_GROUPS


@annotated(
    meta={
        "tool_type": "inserter",
        "aliases": ["fruits"],
        "supported_renders": ["org-item(id,name)"],
        "output_type": "dict",
        "output_semantic": "fruit",
    }
)
def insert_fruits(pattern: str = "") -> list[dict]:
    """Insert fruit items with id, name, calories, color, ftype, and tags.

    Args:
        pattern: Optional pattern to filter fruits by name (e.g., "berry" for all berries)

    Returns:
        List of fruit dictionaries with id, name, calories, color, ftype, and tags
    """
    if not pattern:
        return ALL_FRUITS

    pattern_lower = pattern.lower()
    return [fruit for fruit in ALL_FRUITS if pattern_lower in fruit["name"].lower()]


@annotated(meta={"attribute_type": "simple"})
def translate_ru(item: dict) -> str | None:
    """Translate fruit name to Russian.

    Args:
        item: Dict with fruit information (must contain 'name' key)

    Returns:
        Russian translation of fruit name, or None if name not found
    """
    name = _fruit_name(item)
    if name is None:
        return None
    return TRANSLATIONS_RU.get(name)


@annotated(meta={"attribute_type": "simple", "dependencies": ["translate_ru"]})
def translate_ru_upper(item: dict, translate_ru: str | None = None) -> str | None:
    """Translate fruit name to Russian and convert to uppercase.

    This attribute depends on translate_ru and transforms its output.

    Args:
        item: Dict with fruit information (must contain 'name' key)
        translate_ru: Russian translation from translate_ru attribute (injected)

    Returns:
        Uppercase Russian translation of fruit name, or None if translation not found
    """
    if translate_ru is None:
        return None
    return translate_ru.upper()


@annotated(meta={"attribute_type": "simple"})
def pfc(item: dict) -> dict | None:
    """Calculate PFC (proteins, fats, carbs) for a fruit.

    Args:
        item: Dict with fruit information (must contain 'name' key)

    Returns:
        Dict with proteins, fats, and carbs values in grams, or None if name not found
    """
    name = _fruit_name(item)
    if name is None:
        return None
    return NUTRITION_DATA.get(name)


@annotated(meta={"attribute_type": "simple"})
def fruit_cost(item: dict) -> float | None:
    """Get cost per unit for a fruit.

    Args:
        item: Dict with fruit information (must contain 'name' key)

    Returns:
        Cost per unit in dollars, or None if not found
    """
    name = _fruit_name(item)
    if name is None:
        return None
    return FRUIT_COSTS.get(name)


@annotated(meta={"tool_type": "extender", "item_type": "dict", "output_type": "dict", "output_semantic": "fruit"})
def similar_fruits(item: dict) -> list[dict]:
    """Extend each fruit with 2-3 similar fruits.

    Similarity is based on crc32(name) % 4. Fruits with the same bucket value
    are considered similar (deterministic grouping, stable across runs).

    Args:
        item: Dict with fruit information (must contain 'name' key)

    Returns:
        List of 2-3 similar fruit dictionaries with id, name, calories, color, ftype, and tags

    Examples:
        - For apple -> Fruits with the same crc32(name) % 4 bucket
        - For strawberry -> Fruits with the same crc32(name) % 4 bucket
    """
    name = _fruit_name(item)
    if name is None:
        return []

    bucket = _similarity_bucket(name)
    similar = [f for f in ALL_FRUITS if f.get("name") != name and _similarity_bucket(f["name"]) == bucket]
    return similar[:3]


@annotated(meta={"tool_type": "extender", "item_type": "str", "output_type": "dict"})
def extend_menu_fruits(item: str) -> list[dict]:
    """Extend menu days with eaten fruits data.

    For each day, returns the fruits eaten that day with their quantities.

    Args:
        item: The day identifier (e.g., "day-1", "day-2", etc.)

    Returns:
        List of fruit dictionaries with name and quantity
    """
    return FRUITS_EATEN_BY_DAY.get(item, [])


@annotated(
    meta={
        "item_type": "dict",
        "item_semantic": "fruit",
        "tool_type": "render",
        "aliases": ["fruit"],
        "shape": SHAPE_ITEM,
    }
)
def render_fruit(item: Item, indent: str = "", attrs: dict[str, Any] | None = None) -> str:
    """Render a fruit as its emoji and name.

    Declared item semantic "fruit", matching insert_fruits (output_semantic "fruit"),
    so `fruits, :` recommends this render without any supported_renders declaration.

    Args:
        item: Fruit dict with a "name" key
        indent: Indentation string
        attrs: Attributes dict (unused, part of the render signature)

    Returns:
        "<emoji> <name>", or the bare name when the fruit has no emoji in FRUIT_EMOJI
    """
    name = item.get("name") if isinstance(item, dict) else None
    if not name:
        return f"{indent}{item}"
    emoji = FRUIT_EMOJI.get(name)
    if not emoji:
        return f"{indent}{name}"
    return f"{indent}{emoji} {name}"
