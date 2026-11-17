"""Public API for the Udan forest type system.

This module defines the forest type descriptor folded from the tool chain
and the API interface for the type system that folds and checks it.
"""

from collections.abc import Iterable
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict

from udan.core.api_item_types import ITEM_TYPE_ANY, ITEM_TYPE_GROUP
from udan.core_tools_loading.api_tools import ToolDescriptor, ToolMetadata
from udan.core_tools_loading.api_types import TypeDescriptor

if TYPE_CHECKING:
    from udan.core.api_forests import Node


class ForestTypeDescriptor(BaseModel):
    """Item types of a forest, one descriptor per level, outermost first.

    The index in ``depths`` equals the forest depth. Computed at query
    resolution by folding the tool chain with the per-kind transition
    methods below. Empty ``depths`` mean the chain has no data source, so the
    forest will have no items (or the descriptor is hand-built); a source
    whose item type is not declared is a level of "any", never empty - unknown
    types must switch the type filter off, not guess.
    """

    model_config = ConfigDict(frozen=True)

    depths: list[TypeDescriptor] = []

    @classmethod
    def unknown(cls) -> ForestTypeDescriptor:
        """One level of unknown type: a source without a declared item type.

        A data source (inserter with undeclared output, bare literal) still
        produces items, so the level exists - only its type is unknown.
        """
        return cls(depths=[TypeDescriptor(name=ITEM_TYPE_ANY)])

    @classmethod
    def from_created_level(cls, output_type: str | None, output_semantic: str | None = None) -> ForestTypeDescriptor:
        """Start the stack from an inserter's declared output type.

        An inserter is the only data source of a chain, so it replaces whatever
        was known. An undeclared output type yields one level of "any": items
        exist, their type is unknown. The declared output semantic rides on the
        type the same way ("dict/fruit").

        Args:
            output_type: Item type declared by the inserter, None when undeclared
            output_semantic: Domain meaning declared by the inserter, None when undeclared

        Returns:
            Forest type descriptor with one level
        """
        if not output_type:
            return cls.unknown()
        return cls(depths=[TypeDescriptor(name=output_type, semantic=output_semantic)])

    def with_appended_level(self, output_type: str | None, output_semantic: str | None = None) -> ForestTypeDescriptor:
        """Append one level: the extender's items become children of the current level.

        Args:
            output_type: Item type declared by the extender; None appends nothing
            output_semantic: Domain meaning declared by the extender, None when undeclared

        Returns:
            Forest type descriptor with the appended level
        """
        if not output_type:
            return self
        return self.model_copy(
            update={"depths": [*self.depths, TypeDescriptor(name=output_type, semantic=output_semantic)]}
        )

    def with_wrapped_level(self) -> ForestTypeDescriptor:
        """Wrap the current items in groups: a "group" level is inserted on top."""
        return self.model_copy(update={"depths": [TypeDescriptor(name=ITEM_TYPE_GROUP), *self.depths]})

    def with_rewritten_level(self, output_type: str | None, output_semantic: str | None = None) -> ForestTypeDescriptor:
        """Rewrite the deepest level in place (mapper and replacer).

        Undeclared output type or an empty stack leaves the descriptor unchanged.

        Args:
            output_type: Item type declared by the mapper/replacer; None rewrites nothing
            output_semantic: Domain meaning declared by the mapper/replacer, None when undeclared

        Returns:
            Forest type descriptor with the rewritten deepest level
        """
        if not output_type or not self.depths:
            return self
        depths = [*self.depths[:-1], TypeDescriptor(name=output_type, semantic=output_semantic)]
        return self.model_copy(update={"depths": depths})

    def with_requested(self, desc: ToolDescriptor, level: int | None = None) -> ForestTypeDescriptor:
        """Attach a requested descriptor to one level of the forest.

        Args:
            desc: Descriptor collected by the query resolver
            level: Depth to attach to. None means the deepest level existing so
                far (the default fit). An explicit level must already exist.

        Returns:
            New descriptor with the request attached (this model is frozen)

        Raises:
            ValueError: If an explicit level does not exist
        """
        if level is None:
            if not self.depths:
                # No-loss rule: a descriptor collected before any typed level
                # must survive; expose the gap via the "any" level in debug output.
                return self.model_copy(update={"depths": [TypeDescriptor(name=ITEM_TYPE_ANY, requested=[desc])]})
            level = len(self.depths) - 1
        if not 0 <= level < len(self.depths):
            raise ValueError(f"requested level {level} does not exist in {self}")
        depths = [*self.depths[:level], self.depths[level].with_requested(desc), *self.depths[level + 1 :]]
        return self.model_copy(update={"depths": depths})

    def flattened_requested(self) -> list[ToolDescriptor]:
        """All requested descriptors in level order, insertion order within a level."""
        return [desc for depth in self.depths for desc in depth.requested]

    def __str__(self) -> str:
        """Short representation: "[dict/fruit{fruit_cost}]", "[group, int]", "[]" when unknown."""
        return "[" + ", ".join(str(depth) for depth in self.depths) + "]"

    __repr__ = __str__


class TypeSystemAPI:
    """API interface for forest type inference.

    The type system owns the per-kind transitions of the forest type
    descriptor (see ForestTypeDescriptor): how each tool kind changes
    the level types of the chain built so far, and which combinations cannot
    describe a real forest. It can be disabled (udan_types_enabled=False,
    see DummyTypeSystem): then it folds nothing, rejects nothing, and suggests
    everything.
    """

    def combine(self, ftd: ForestTypeDescriptor, descriptor: ToolDescriptor) -> ForestTypeDescriptor:
        """Combine the forest types built so far with the next tool of the chain.

        Args:
            ftd: Forest type descriptor before this chain item
            descriptor: Tool descriptor resolved for the chain item

        Returns:
            Forest type descriptor after the item; empty depths mean the chain
            has no data source

        Raises:
            TypeCombinationError: If the tool cannot be combined with
                ftd - a chain item that creates a level with no data source,
                where the forest would be empty and the created level could
                never exist
        """
        raise NotImplementedError

    def suggest(
        self,
        ftd: ForestTypeDescriptor,
        pattern: str = "",
        tool_type: str = "",
        endorsed: Iterable[str] = (),
    ) -> dict[str, dict[str, ToolMetadata]]:
        """Tools usable at a chain position, as suggestion sections.

        The one completions verdict behind both suggestion surfaces: every
        registered tool that can sit at that position, narrowed by the
        inputs the asking surface provides, so the caller never filters the
        registry itself. Inserters fit only a sourceless chain; every other
        kind fits when its declared input type accepts one of the levels
        (fits_chain) - an undeclared or "any" contract, and a level of "any",
        constrains nothing.

        Sections carry the ordering the surface shows. Narrowed to renders
        (tool_type="render", the bare `:` surface) the sections are
        ranked: endorsed renders first - named in `endorsed` or matching a
        level's item semantic - then the merely type-compatible rest. Semantic
        fit is a recommendation, not a filter: an endorsed render is listed
        regardless of its declared item type. Any other narrowing sections by
        kind ("Inserters:", "Attributes:", ...).

        Args:
            ftd: Forest type descriptor of the chain built so far; no levels
                means no data source yet, which accepts everything
            pattern: Substring matched against the name, the domain-qualified
                name, and the aliases; "" matches everything
            tool_type: Kind filter ("render", "operator", "attribute",
                a concrete kind, or "" for all kinds) - the `:?` render-only
                variant narrows with "render"
            endorsed: Render names declared by the chain's tools
                (supported_renders meta); ranks the render-narrowed sections,
                ignored by every other narrowing

        Returns:
            Dict of section heading -> canonical tool name -> metadata;
            aliases resolve to their canonical name's metadata, so only
            canonical names are listed
        """
        raise NotImplementedError

    def require_source_for_output(
        self, ftd: ForestTypeDescriptor, output_ds: Iterable[ToolDescriptor], node: Node
    ) -> None:
        """Reject output specs requested on a chain without a data source.

        Args:
            ftd: Forest type descriptor of the chain built so far
            output_ds: Output descriptors (renders) requested by the query
            node: Resolved query tree, to recognize output-overriding chains

        Raises:
            TypeCombinationError: If output specs are requested while the
                descriptor has no levels, so the forest is empty and they would
                be applied to nothing
        """
        raise NotImplementedError
