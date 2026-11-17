"""Forest type system.

This module contains the TypeSystem class which implements the TypeSystemAPI.
It owns the per-kind transitions of the forest type descriptor: how each
tool kind changes the level types of the chain built so far, and which
combinations cannot describe a real forest. It also answers which tools
fit the chain and how the suggestion surfaces order them (suggest(): the bare
`:` render advice ranks its sections, the bare `?` completions group by kind).
"""

from collections.abc import Iterable

from udan.core.api_constants import OVERRIDES_OUTPUT
from udan.core.api_exceptions import TypeCombinationError
from udan.core.api_forests import Node
from udan.core.api_item_types import ITEM_TYPE_ANY, fits_chain, is_item_type_accepted
from udan.core.api_type_system import ForestTypeDescriptor, TypeSystemAPI
from udan.core.utils_chain import chain_declares_meta
from udan.core_tools_loading.api_tool_kinds import ToolKindsRegistryAPI
from udan.core_tools_loading.api_tools import ToolDescriptor, ToolKind, ToolMetadata
from udan.core_tools_loading.api_tools_registry import ToolsRegistryAPI


def _display_name(name: str, metadata: ToolMetadata) -> str:
    """Qualify a tool name with its domain for display.

    Args:
        name: Canonical tool name
        metadata: Metadata of the tool

    Returns:
        "domain.name" when the tool declares a domain other than builtins, else "name"
    """
    domain = metadata.meta.get("domain", "")
    return f"{domain}.{name}" if domain and domain != "builtins" else name


def _description(metadata: ToolMetadata) -> str:
    """First line of a tool description, for suggestion listings.

    Args:
        metadata: Metadata of the tool

    Returns:
        First description line, stripped
    """
    return (metadata.description or "").split("\n", maxsplit=1)[0].strip()


def _matches_pattern(name: str, metadata: ToolMetadata, pattern: str) -> bool:
    """Does a tool match a completions pattern?

    Args:
        name: Canonical tool name
        metadata: Metadata of the tool
        pattern: Substring to match; "" matches everything

    Returns:
        True when the pattern is found in the name, the domain-qualified name,
        or one of the aliases - the same match the help listing applied
        when the filter lived there. The pattern's underscored spelling is
        tried after the typed one, so `ls-fi` names `ls_files` the way the
        resolver's dash sugar names a written tool
    """
    if not pattern:
        return True
    domain = metadata.meta.get("domain", "")
    full_name = f"{domain}.{name}" if domain and domain != "builtins" else name
    aliases = metadata.meta.get("aliases", [])
    candidates = (name, full_name, *aliases)
    return any(spelling in candidate for spelling in (pattern, pattern.replace("-", "_")) for candidate in candidates)


def _kind_section(kind: ToolKind | str) -> str:
    """Section heading of one tool kind, for the completions sections.

    Args:
        kind: Tool kind (ToolMetadata.tool_type) or its name

    Returns:
        "Inserters:" for "inserter", "Attributes:" for "attribute"
    """
    name = kind.name if isinstance(kind, ToolKind) else kind
    return f"{name.capitalize()}s:"


class TypeSystem(TypeSystemAPI):
    """Folds tool transitions onto the forest type descriptor.

    The table mirrors how the engine applies a chain: a kind whose level_change is
    "replaces" starts the descriptor over, "appends" adds a level under the last one,
    "wraps" groups the last level, and a kind whose rewrites_items is set rewrites the
    deepest level. A kind that creates a level over a sourceless chain is rejected:
    the forest would be empty and the level it creates could never exist. A kind with
    a declared input type is rejected when no level of the chain built so far can
    provide that type - its items would reach it unconverted.
    """

    def __init__(self, registry: ToolsRegistryAPI, kinds: ToolKindsRegistryAPI) -> None:
        """Initialize type system.

        Args:
            registry: ToolsRegistryAPI instance for accessing metadata
            kinds: The tool kind vocabulary, for reading which kinds the loaded
                packages declared
        """
        self._registry = registry
        self._kinds = kinds

    def combine(self, ftd: ForestTypeDescriptor, descriptor: ToolDescriptor) -> ForestTypeDescriptor:
        """Combine the forest types built so far with the next tool of the chain.

        Args:
            ftd: Forest type descriptor before this chain item
            descriptor: Tool descriptor resolved for the chain item

        Returns:
            Forest type descriptor after the item; empty depths mean "unknown"

        Raises:
            TypeCombinationError: If the tool creates a level while the
                chain has no data source, or consumes items of a type no level
                of the chain provides
        """
        metadata = self._registry.get_metadata(descriptor.name)
        if metadata is None:
            return ForestTypeDescriptor()
        kind, out, semantic = metadata.tool_type, metadata.output_type, metadata.output_semantic
        # A kind the vocabulary does not hold is owned by no loaded package: the tool
        # loaded as a bare kind that declares no rules - no level change, no item
        # contract. The fold records the one thing it knows (a source, its type
        # unknown) and leaves the verdict to the chain routing, which dispatches by
        # kind and says what is missing; folding "no data source" here would blame the
        # render instead.
        if kind.name not in self._kinds:
            return ForestTypeDescriptor.unknown()
        # The level transitions are the kind's own declaration (level_change), so a
        # kind a plugin adds folds without this table growing
        if kind.level_change == "replaces":
            return ForestTypeDescriptor.from_created_level(out, semantic)
        self._require_input_fit(ftd, metadata)
        if kind.level_change == "appends":
            self._require_source(ftd, metadata)
            return ftd.with_appended_level(out, semantic)
        if kind.level_change == "wraps":
            self._require_source(ftd, metadata)
            return ftd.with_wrapped_level()
        if kind.rewrites_items:
            return ftd.with_rewritten_level(out, semantic)
        return ftd  # a kind that declares no output contract

    def suggest(
        self,
        ftd: ForestTypeDescriptor,
        pattern: str = "",
        tool_type: str = "",
        endorsed: Iterable[str] = (),
    ) -> dict[str, dict[str, ToolMetadata]]:
        """Tools usable at a chain position, as suggestion sections.

        Args:
            ftd: Forest type descriptor of the chain built so far; no levels means
                no data source yet, which accepts everything
            pattern: Substring matched against the name, the domain-qualified name,
                and the aliases; "" matches everything
            tool_type: Kind filter ("" for all kinds, see
                ToolMetadata.matches_type_filter)
            endorsed: Render names declared by the chain's tools
                (supported_renders meta)

        Returns:
            Dict of section heading -> canonical tool name -> metadata;
            ranked render sections when narrowed to renders, sections by kind
            (registry order within a section, first-encounter order across them)
            otherwise
        """
        levels = [depth.name for depth in ftd.depths]
        return self._kind_sections(levels, pattern, tool_type)

    def _kind_sections(self, levels: list[str], pattern: str, tool_type: str) -> dict[str, dict[str, ToolMetadata]]:
        """Section the fitting tools by kind, one section per kind met.

        Args:
            levels: Item type names of the chain levels built so far
            pattern: Substring matched against the name, the domain-qualified name,
                and the aliases; "" matches everything
            tool_type: Kind filter ("" for all kinds)

        Returns:
            Dict of section heading (one per kind) -> canonical tool name
            -> metadata
        """
        sections: dict[str, dict[str, ToolMetadata]] = {}
        for name, metadata in self._registry.get_metadatas().items():
            if name != metadata.name:
                continue
            if not metadata.matches_type_filter(tool_type):
                continue
            if not _matches_pattern(name, metadata, pattern):
                continue
            if not fits_chain(metadata, levels):
                continue
            sections.setdefault(_kind_section(metadata.tool_type), {})[name] = metadata
        return sections

    def require_source_for_output(
        self, ftd: ForestTypeDescriptor, output_ds: Iterable[ToolDescriptor], node: Node
    ) -> None:
        """Reject output tools folded onto a sourceless chain: there is nothing to show.

        Args:
            ftd: Forest type descriptor of the chain built so far
            output_ds: Output descriptors (renders) requested by the query
            node: Resolved query tree, to recognize output-overriding chains

        Raises:
            TypeCombinationError: If output specs are requested while the descriptor
                has no levels, so the forest is empty and there would be nothing
                to produce output of
        """
        output_specs = list(output_ds)
        overrides_output = chain_declares_meta(self._registry.get_metadatas(), node, OVERRIDES_OUTPUT)
        if not output_specs or ftd.depths or overrides_output:
            return
        names = ", ".join(f"'{r.name}'" for r in output_specs)
        creators_heading, creators = self._suggested_level_creators()
        raise TypeCombinationError(
            f"{names} requested, but the chain has no data source",
            explanation="insert items first - start the chain with a level-creating tool",
            suggestions={creators_heading: creators},
        )

    def _require_input_fit(self, ftd: ForestTypeDescriptor, metadata: ToolMetadata) -> None:
        """Reject a tool whose declared input type no level of the chain provides.

        Args:
            ftd: Forest type descriptor before this chain item
            metadata: Metadata of the tool being folded

        Raises:
            TypeCombinationError: If the tool declares a specific input type
                and no level of the descriptor fits it
        """
        levels = [depth.name for depth in ftd.depths]
        item_type = metadata.item_type
        if item_type is None or is_item_type_accepted(item_type, levels):
            return
        creators_heading, creators = self._suggested_producing(item_type)
        kind = metadata.tool_type.name
        raise TypeCombinationError(
            f"{kind} '{metadata.name}' consumes '{item_type}', the chain has {ftd}",
            explanation=f"use a tool that fits the chain - produce '{item_type}' first, "
            f"or pick one of the fitting {kind}s",
            suggestions={
                creators_heading: creators,
                f"{kind}s that fit {ftd}:": self._suggested_fitting(kind, levels),
            },
        )

    def _require_source(self, ftd: ForestTypeDescriptor, metadata: ToolMetadata) -> None:
        """Reject a level-creating tool folded onto a sourceless chain.

        Args:
            ftd: Forest type descriptor before this chain item
            metadata: Metadata of the tool being folded

        Raises:
            TypeCombinationError: If the descriptor has no levels, so there is
                nothing the tool could create its level from
        """
        if ftd.depths:
            return
        creators_heading, creators = self._suggested_level_creators()
        raise TypeCombinationError(
            f"{metadata.tool_type.name} '{metadata.name}' creates a level, but the chain has no data source",
            explanation="insert items first - start the chain with a level-creating tool",
            suggestions={creators_heading: creators},
        )

    def _canonical_operator_kind_items(self) -> dict[str, ToolMetadata]:
        """Canonical-name -> metadata of the tools of the "operator" filter group, sorted by name.

        Aliases resolve to the metadata of their canonical name, so only
        canonical names are listed.

        Returns:
            Dict of canonical name -> metadata
        """
        items = {
            name: metadata
            for name, metadata in self._registry.get_metadatas().items()
            if metadata.tool_type.filter_group == "operator" and name == metadata.name
        }
        return dict(sorted(items.items()))

    def _described(self, items: dict[str, ToolMetadata]) -> dict[str, str]:
        """Format a metadata selection as a suggestion section.

        Args:
            items: Canonical name -> metadata

        Returns:
            Dict of display name -> first description line
        """
        return {_display_name(name, metadata): _description(metadata) for name, metadata in items.items()}

    def _suggested_level_creators(self) -> tuple[str, dict[str, str]]:
        """Collect the kinds that start a chain over, as suggestions for a sourceless chain.

        The heading names the kinds found, so the advice says what the running
        vocabulary offers rather than a kind name this table hardcodes.

        Returns:
            (heading, display name -> first description line), sorted by name
        """
        creators = {
            name: metadata
            for name, metadata in self._canonical_operator_kind_items().items()
            if metadata.tool_type.level_change == "replaces"
        }
        kinds = sorted({metadata.tool_type.name for metadata in creators.values()})
        heading = f"{kinds[0]}s that create a level:" if len(kinds) == 1 else f"{', '.join(kinds)} that create a level:"
        return heading, self._described(creators)

    def _suggested_producing(self, wanted_item_type: str) -> tuple[str, dict[str, str]]:
        """Collect level creators whose declared output type fits the wanted input type.

        An undeclared or "any" output says nothing about the produced type and
        is not suggested. The heading names the kinds found, so the advice says what
        the running vocabulary offers rather than a kind name this table hardcodes.

        Args:
            wanted_item_type: Item type the chain fails to provide

        Returns:
            (heading, display name -> first description line), sorted by name
        """
        creators = {
            name: metadata
            for name, metadata in self._canonical_operator_kind_items().items()
            if metadata.tool_type.level_change == "replaces"
            and metadata.output_type
            and metadata.output_type != ITEM_TYPE_ANY
            and is_item_type_accepted(wanted_item_type, [metadata.output_type])
        }
        kinds = sorted({metadata.tool_type.name for metadata in creators.values()})
        heading = f"{kinds[0]}s producing '{wanted_item_type}':" if len(kinds) == 1 else ""
        return heading, self._described(creators)

    def _suggested_fitting(self, kind: str, levels: list[str]) -> dict[str, str]:
        """Collect same-kind tools whose declared input type fits the current levels.

        An undeclared or "any" input fits every chain and would list half the
        registry, so only specific declared contracts are suggested.

        Args:
            kind: Tool kind to collect (the kind that failed)
            levels: Item type names of the forest levels built so far

        Returns:
            Dict of display name -> first description line, sorted by name
        """
        fitting = {
            name: metadata
            for name, metadata in self._canonical_operator_kind_items().items()
            if metadata.tool_type.name == kind
            and metadata.item_type
            and metadata.item_type != ITEM_TYPE_ANY
            and is_item_type_accepted(metadata.item_type, levels)
        }
        return self._described(fitting)


class DummyTypeSystem(TypeSystemAPI):
    """Types disabled: folds nothing, rejects nothing, suggests everything flat.

    combine keeps only the requested descriptors collected so far, dropping the
    level types: empty levels keep `?` listing the whole registry, while the
    no-loss rule on ForestTypeDescriptor.with_requested keeps descriptor
    collection working wherever in the chain they are requested.
    """

    def __init__(self, registry: ToolsRegistryAPI) -> None:
        """Initialize dummy type system.

        Args:
            registry: ToolsRegistryAPI instance, for listing renders unfiltered
        """
        self._registry = registry

    def combine(self, ftd: ForestTypeDescriptor, descriptor: ToolDescriptor) -> ForestTypeDescriptor:
        """Fold nothing: types stay unknown, the requested descriptors are kept.

        Args:
            ftd: Forest type descriptor before this chain item
            descriptor: Tool descriptor resolved for the chain item

        Returns:
            Empty descriptor re-armed with the requests collected so far; the
            no-loss rule puts them on an "any" level, so descriptor seeding
            works wherever in the chain they are requested
        """
        result = ForestTypeDescriptor()
        for desc in ftd.flattened_requested():
            result = result.with_requested(desc)
        return result

    def suggest(
        self,
        ftd: ForestTypeDescriptor,
        pattern: str = "",
        tool_type: str = "",
        endorsed: Iterable[str] = (),
    ) -> dict[str, dict[str, ToolMetadata]]:
        """Every fitting candidate in one flat section: types disabled, nothing is type-filtered.

        The query's own narrowing still applies - pattern and tool_type
        are the query's, not the type system's; only the type filter is dropped.

        Args:
            ftd: Forest type descriptor of the chain built so far (ignored)
            pattern: Substring matched against the name, the domain-qualified name,
                and the aliases; "" matches everything
            tool_type: Kind filter ("" for all kinds, see
                ToolMetadata.matches_type_filter)
            endorsed: Render names declared by the chain's tools (ignored)

        Returns:
            Dict of one section heading -> canonical tool name -> metadata,
            registry order
        """
        fitting = {
            name: metadata
            for name, metadata in self._registry.get_metadatas().items()
            if name == metadata.name
            and metadata.matches_type_filter(tool_type)
            and _matches_pattern(name, metadata, pattern)
        }
        return {"Tools:": fitting}

    def require_source_for_output(
        self, ftd: ForestTypeDescriptor, output_ds: Iterable[ToolDescriptor], node: Node
    ) -> None:
        """Reject nothing: with types disabled an output spec on a sourceless chain still passes.

        Args:
            ftd: Forest type descriptor of the chain built so far (ignored)
            output_ds: Output descriptors requested by the query (ignored)
            node: Resolved query tree (ignored)
        """
