"""Item-type contracts on tool metadata.

Pure helpers over the declared item types (the promoted `item_type` fields, meta-only
for the kinds without a promoted field): which declared types accept each other's items, whether
a tool can consume from the levels built so far, and whether it
can sit at a chain position. Consumed by the type system for chain validation and
render suggestions, and by the help listing for the `?` completions filter.
"""

from udan.core_tools_loading.api_tools import ToolMetadata
from udan.core_tools_loading.api_types import ITEM_TYPE_ANY

# Item-type vocabulary used for forest level types.
# ITEM_TYPE_ANY ("any" - a level of unknown type: a source with undeclared output, or
# descriptors collected before any typed level) is defined in udan.core_tools_loading.api_types:
# it is the loader's no-contract marker, and this module reads it with the rest of the
# vocabulary.
ITEM_TYPE_GROUP = "group"  # level holding Group items created by a grouper

# Declared item types that accept each other's items: numeric types interoperate
# (and bool is an int subclass in Python); tool metadata entries are dicts
# at runtime, and a tool group level is a group, so contracts declared on
# the base type fit both. Every other declared type must match the level name
# exactly or share a "|" union with it.
_ITEM_TYPE_FAMILIES: dict[str, frozenset[str]] = {
    "int": frozenset({"int", "float", "bool"}),
    "float": frozenset({"float", "int"}),
    "dict": frozenset({"dict", "tool_metadata"}),
    "tool_metadata": frozenset({"tool_metadata", "dict"}),
    "group": frozenset({"group", "tool_group"}),
    "tool_group": frozenset({"tool_group", "group"}),
}


def accepted_item_types(item_type: str) -> frozenset[str]:
    """Level names one declared item type accepts.

    Args:
        item_type: Declared item type: a leaf ("int") or a union ("str|Path")

    Returns:
        Level names that fit: the union leaves plus their family members
    """
    accepted: set[str] = set()
    for leaf in item_type.split("|"):
        leaf = leaf.strip()
        accepted.add(leaf)
        accepted |= _ITEM_TYPE_FAMILIES.get(leaf, frozenset())
    return frozenset(accepted)


def is_item_type_accepted(item_type: str | None, levels: list[str]) -> bool:
    """Does a declared item type fit the level types built so far?

    An undeclared contract and "any" constrain nothing on either side, and a
    level of "any" is unknown type knowledge that switches the check off -
    unknown must not reject. Item-consuming kinds apply at every depth, so
    a contract is satisfied when any level fits (see TypeSystem.combine).

    Args:
        item_type: Item type declared by the tool, None when undeclared
        levels: Item type names of the forest levels built so far

    Returns:
        True when the tool can consume from the levels
    """
    if not item_type or item_type == ITEM_TYPE_ANY:
        return True
    if not levels or ITEM_TYPE_ANY in levels:
        return True
    accepted = accepted_item_types(item_type)
    return any(level in accepted for level in levels)


def declared_item_type(metadata: ToolMetadata) -> str | None:
    """Item type a tool consumes, from its typed field or render meta.

    Args:
        metadata: Metadata of the tool

    Returns:
        Declared item type: the promoted `item_type` for the kinds that promote it,
        the meta `item_type` for the kinds without a promoted field (the type the
        loader derived from the 'item' annotation lives there, see
        impl_utils_tools_loader); None when nothing is declared.
    """
    # A kind that promotes no item contract keeps the type the loader derived in meta,
    # so its metadata's own `item_type` field is not authoritative - it is the default
    # the metadata class was built with, empty for every kind the loader had no
    # contract keys for.
    if metadata.tool_type.item_type_keys:
        return metadata.item_type
    return metadata.meta.get("item_type")


def fits_chain(metadata: ToolMetadata, levels: list[str]) -> bool:
    """Can this tool be used at a chain position whose levels are built so far?

    Inserters carry no item contract - they can only open a chain - so any existing
    level means the position is not theirs. Every other kind fits when its declared
    item type fits the levels (see is_item_type_accepted).

    Args:
        metadata: Metadata of the tool
        levels: Item type names of the current chain's levels built so far

    Returns:
        True when the tool can be used at that position; an empty level list
        (no data source yet) accepts everything
    """
    # The inserter kind is a plugin kind, so nothing here holds its kind object; the
    # name match stands in for the "an inserter can only open a chain" rule until it
    # becomes a declaration on the kind
    if metadata.tool_type == "inserter":
        return not levels
    return is_item_type_accepted(declared_item_type(metadata), levels)
