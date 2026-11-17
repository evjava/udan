"""Rendering logic for converting forest to string representation.

This module contains the RenderEngine class for rendering Forest objects to string
format, with support for displaying attribute values and custom renders.

IMPORTANT: Core modules must NOT contain plugin-specific rendering logic.
All custom formatting (e.g., org-mode source blocks, markdown, etc.) must
be delegated to plugins through the render system. This ensures core modules
remain generic and don't depend on specific plugin implementations.

Plugins provide renders by annotating functions with @annotated(meta={"tool_type": "render"}).
When rendering attributes, the core checks the attribute metadata for a "render" key
and uses the specified render function to format the attribute value.
"""

import inspect
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

# Using ToolsRegistryAPI (implementation passed at runtime)
from udan.attributes.api_attribute_storage import AttributeStorageAPI
from udan.core.api_attributes import AttributeDescriptor
from udan.core.api_exec_context import ExecContextAPI
from udan.core.api_forests import Forest, Item
from udan.core.api_logger import LoggerAPI
from udan.core.utils_tables import _row_columns
from udan.core_tools_loading.api_annotated import unwrap_function
from udan.core_tools_loading.api_tool_kinds import ToolKindService
from udan.core_tools_loading.api_tools import ToolDescriptor, ToolKind
from udan.core_tools_loading.api_tools_registry import ToolsRegistryAPI
from udan.core_tools_loading.api_types import Group
from udan.renders.api_render_engine import RenderEngineAPI
from udan.renders.api_renders import (
    FRONTEND,
    FRONTEND_TEXT,
    RENDER,
    RENDER_ATTR,
    RenderDescriptor,
    is_aggregate_render,
)


@dataclass
class RenderDecision:
    render_fn: Callable
    render_item: Item
    indent: str
    is_custom: bool = False
    attr_identity: str = ""
    render_name: str = ""
    reason: str = ""
    render_desc: RenderDescriptor | None = None


class RenderEngineImpl(ToolKindService, RenderEngineAPI):
    """Renderer for converting Forest to string representation."""

    KINDS: tuple[ToolKind, ...] = (RENDER,)
    """The kind this engine owns: renders."""

    def __init__(  # type: ignore[attr-defined]
        self,
        logger: LoggerAPI,
        registry: ToolsRegistryAPI,
        attribute_storage: AttributeStorageAPI,
    ) -> None:
        """Initialize the renderer.

        The storage is the attribute package's own component: rendering reads
        attribute values from it, the runtime that computes them is that package's
        service and never reaches here.

        Args:
            logger: Logger instance
            registry: ToolsRegistryAPI instance
            attribute_storage: AttributeStorageAPI holding the calculated attribute values
        """
        self._logger = logger
        self._registry = registry
        self._attribute_storage = attribute_storage

    def output_forest(
        self,
        forest: Forest,
        requested: Sequence[ToolDescriptor],
        output_specs: Sequence[ToolDescriptor],
        ctx: ExecContextAPI,
        frontend: str = FRONTEND_TEXT,
    ) -> str:
        """The core's output seam, answered by rendering.

        Args:
            forest: The forest to produce the output of
            requested: The descriptors requested with the query, whose values are
                displayed alongside the items
            output_specs: The render descriptors the query resolved
            ctx: Execution context for dependency injection in renders
            frontend: Requested output frontend for render resolution

        Returns:
            String representation of the forest
        """
        # The seam carries the walk's generic descriptors; the render path keys on
        # the domain subclasses (attribute values, render definitions)
        attr_ds = [d for d in requested if isinstance(d, AttributeDescriptor)]
        render_ds = [d for d in output_specs if isinstance(d, RenderDescriptor)]
        return self.render_forest(
            forest,
            attr_ds,
            render_ds,
            ctx=ctx,
            frontend=frontend or FRONTEND_TEXT,
        )

    def default_output_specs(self) -> list[ToolDescriptor]:
        """The introspection item render: what a query with no render named shows."""
        return [RenderDescriptor.create("introspect-item")]

    def has_variant(self, key: str, frontend: str = FRONTEND_TEXT) -> bool:
        """Check whether a render name is registered with a variant for the frontend.

        Read off the registry's own public read: a variant exists when a registered
        render reachable under `key` (its name or one of its aliases) declares the
        frontend in its meta. The flat key of a non-text variant is deliberately
        never occupied (see ToolsRegistry._register), so the alias alone cannot
        answer this - the aliases of every registered render are what carries it.

        Args:
            key: Render name or alias
            frontend: Requested output frontend

        Returns:
            True when a render variant for this frontend is registered under the name
        """
        for metadata in self._registry.get_metadatas(RENDER).values():
            names = {metadata.name, *metadata.meta.get("aliases", [])}
            if key in names and metadata.meta.get(FRONTEND, FRONTEND_TEXT) == frontend:
                return True
        return False

    def render_forest(
        self,
        forest: Forest,
        attr_ds: list[AttributeDescriptor],
        render_tools: list[RenderDescriptor],
        ctx: ExecContextAPI,
        storage: AttributeStorageAPI | None = None,
        frontend: str = FRONTEND_TEXT,
    ) -> str:
        """Render a forest to string representation.

        Process:
        1. Parse render tools into render descriptors
        2. Get storage from attribute_runtime
        3. Find aggregate render (if any)
        4. Run pre-render phase to set system attributes (render)
        5. If aggregate render found, use it (composing the per-item rendered
           lines); otherwise render each item
        6. Add debug log if enabled

        Args:
            forest: The forest to render
            attr_ds: List of attribute descriptors to display
            render_tools: List of render descriptors
            ctx: Execution context for dependency injection and query-time logging
            storage: Optional attribute storage for accessing attribute values
            frontend: Requested output frontend for render resolution
                (FRONTEND_TEXT by default); selects the matching render
                variant when a render name has several

        Returns:
            String representation of the forest
        """
        # 1. Parse render tools into render descriptors
        render_ds = render_tools or []

        # 2. Get storage from attribute_runtime
        if storage is None:
            storage = self._attribute_storage
        assert storage is not None

        # 3. Find aggregate render (if any); the per-item render choice depends on
        # whether an aggregate composes the item lines
        aggr_result = self._find_aggregate_render(render_ds, frontend)

        # 4. Run pre-render phase to set system attributes (render)
        self._pre_render(forest, attr_ds, render_ds, ctx, storage, frontend, for_aggregate=aggr_result is not None)

        if aggr_result:
            # 5. Use aggregate render, feeding it the per-item rendered lines
            render_fn, render_desc = aggr_result
            result = self._render_with_aggregate(render_fn, render_desc, forest, attr_ds, render_ds, storage, frontend)
        else:
            # 5. Render each item with its preferred render
            result = self._render_items(forest, attr_ds, render_ds, storage, frontend)

        # 6. Append aggregate summary (if any aggregate attrs)
        result = self._render_summary(result, attr_ds, storage)

        return result

    def _find_aggregate_render(
        self, render_ds: list[RenderDescriptor], frontend: str = FRONTEND_TEXT
    ) -> tuple[Callable, RenderDescriptor] | None:
        """Find aggregate render from render descriptors.

        Args:
            render_ds: List of render descriptors to search
            frontend: Requested output frontend for render resolution

        Returns:
            Tuple of (render_fn, render_desc) or None if no aggregate render found
        """
        for render_desc in render_ds:
            try:
                if is_aggregate_render(self._registry, render_desc.name):
                    render_fn = self._registry.resolve(render_desc.name, kind=RENDER, frontend=frontend).fn
                    return render_fn, render_desc
            except ValueError, AttributeError:
                pass
        return None

    def get_ioc_debug_log(self, show_time: bool = False) -> str:
        """Get debug log from the IOC-injected logger."""
        return self._logger.get_log(show_time=show_time)

    def _resolve_attrs_for_aggregate(
        self,
        children: list[Any],
        attr_ds: list[AttributeDescriptor],
    ) -> tuple[list[Any], list[dict]]:
        """Resolve per-item attrs and merge into dict items for aggregate renders."""
        storage = self._attribute_storage
        if storage is None:
            return children, []

        items_attrs: list[dict] = []
        merged_items: list[Any] = []
        for item in children:
            # Collect attrs for this item
            item_attrs: dict[str, Any] = {}
            for at_d in attr_ds:
                val = storage.get_attr_value(at_d, item)
                if val is not None:
                    item_attrs[at_d.name] = val
            items_attrs.append(item_attrs)

            # Merge attrs into dict items
            if isinstance(item, dict):
                merged = dict(item)
                merged.update(item_attrs)
                merged_items.append(merged)
            else:
                merged_items.append(item)
        return merged_items, items_attrs

    def _render_with_aggregate(
        self,
        render_fn: Callable,
        render_desc: RenderDescriptor,
        forest: Forest,
        attr_ds: list[AttributeDescriptor],
        render_ds: list[RenderDescriptor],
        storage: AttributeStorageAPI,
        frontend: str = FRONTEND_TEXT,
    ) -> str:
        """Render forest using aggregate render function.

        Args:
            render_fn: Aggregate render function
            render_desc: Render descriptor
            forest: The forest to render
            attr_ds: List of attribute descriptors
            render_ds: List of render descriptors (for per-item line rendering)
            storage: Attribute storage for accessing attribute values
            frontend: Requested output frontend for render resolution

        Returns:
            Rendered string
        """
        depths = forest.depths
        render_args = render_desc.args if render_desc else ()

        # Get items from forest
        children = forest.items

        # Resolve per-item attrs and merge into dict items
        items_attrs: list[dict] | None = None
        if attr_ds:
            children, items_attrs = self._resolve_attrs_for_aggregate(children, attr_ds)

        # Aggregate renders collect dict items; row items are seen as their columns
        # (aggregate renders declare no row item semantic, see _render_view)
        children = [self._render_view(item, row_aware=False) for item in children]

        # Unwrap the function to get the original signature
        actual_fn = unwrap_function(render_fn)

        # Build kwargs for dependencies that won't be auto-injected by DI
        sig = inspect.signature(actual_fn)
        kwargs: dict[str, Any] = {}

        # Pass registry if the function has a registry parameter
        if "registry" in sig.parameters:
            kwargs["registry"] = self._registry

        # Pass items_attrs if the function declares it
        if "items_attrs" in sig.parameters and items_attrs is not None:
            kwargs["items_attrs"] = items_attrs

        # Pass storage if the function has a storage parameter
        if "storage" in sig.parameters:
            kwargs["storage"] = self._attribute_storage

        # Pass per-item rendered lines if the function declares them: the aggregate
        # render joins lines rendered by each item's own per-item render
        if "rendered_items" in sig.parameters:
            kwargs["rendered_items"] = self._render_items_for_aggregate(forest, attr_ds, render_ds, storage, frontend)

        # Separate named args (--key=value) from positional render args
        positional_args = []
        for arg in render_args:
            if isinstance(arg, str) and arg.startswith("--") and "=" in arg:
                key, _, value = arg[2:].partition("=")
                kwargs[key] = value
            else:
                positional_args.append(arg)

        # Call the function with depths, children, attr_ds, and additional args
        return render_fn(depths, children, attr_ds, *positional_args, **kwargs)

    def _render_items_for_aggregate(
        self,
        forest: Forest,
        attr_ds: list[AttributeDescriptor],
        render_ds: list[RenderDescriptor],
        storage: AttributeStorageAPI,
        frontend: str = FRONTEND_TEXT,
    ) -> list[str]:
        """Render per-item content lines for an aggregate render.

        Each line is the item rendered by its own per-item render. Lines carry no
        indentation and no bullet: the aggregate render owns the layout
        (indentation, bullets, headings) and joins the lines itself.

        Args:
            forest: The forest to render
            attr_ds: List of attribute descriptors to display
            render_ds: List of render descriptors
            storage: Attribute storage for accessing attribute values
            frontend: Requested output frontend for render resolution

        Returns:
            One rendered line per item, in forest order
        """
        lines = []
        item_render_d = self._first_item_render_desc(render_ds)
        for depth, item in forest.as_pairs():
            result = self._determine_item_render(
                item, forest, attr_ds, render_ds, depth, storage, frontend, for_aggregate=True
            )
            if not result:
                continue
            # Layout (indentation, bullets) belongs to the aggregate render
            result.indent = ""
            if item_render_d is not None and not result.is_custom and not isinstance(item, Group):
                # The render args belong to the per-item render (e.g. :fmt's format)
                result.render_desc = item_render_d
            chunk = self._render_single_item(result, depth)
            if chunk:
                lines.append(chunk)
        return lines

    def _render_summary(
        self,
        rendered: str,
        attr_ds: list[AttributeDescriptor],
        storage: AttributeStorageAPI,
    ) -> str:
        """Append aggregate summary lines if aggregate attrs are present.

        Reads aggregate values stored on the root node item ('forest')
        and appends them as '# name: value' lines below the rendered output.
        """
        root_item = "forest"
        summary_lines: list[str] = []
        for at_d in attr_ds:
            val = storage.get_attr_value(at_d, root_item)
            if val is not None:
                summary_lines.append(f"# {at_d.name}: {val}")
        if not summary_lines:
            return rendered
        footer = "\n".join(summary_lines)
        return f"{rendered}\n{footer}" if rendered else footer

    def _render_items(
        self,
        forest: Forest,
        attr_ds: list[AttributeDescriptor],
        render_ds: list[RenderDescriptor],
        storage: AttributeStorageAPI,
        frontend: str = FRONTEND_TEXT,
    ) -> str:
        """Render each item with its preferred render.

        Args:
            forest: The forest to render
            attr_ds: List of attribute descriptors to display
            render_ds: List of render descriptors
            storage: Attribute storage for accessing attribute values
            frontend: Requested output frontend for render resolution

        Returns:
            Rendered string
        """
        pairs = list(forest.as_pairs())
        if not pairs:
            return ""

        chunks = []
        primary_render_desc = render_ds[0] if render_ds else None

        for depth, item in pairs:
            result = self._determine_item_render(item, forest, attr_ds, render_ds, depth, storage, frontend)
            if result:
                result.render_desc = (
                    primary_render_desc if not result.is_custom and not isinstance(item, Group) else None
                )
                chunk = self._render_single_item(result, depth)
                chunks.append(chunk)

        return "\n".join(c for c in chunks if c)

    def _resolve_render_with_fallback(self, render_name: str, frontend: str = FRONTEND_TEXT) -> Callable:
        """Resolve render function from registry, with fallback for missing renders.

        Args:
            render_name: Name of the render to resolve
            frontend: Requested output frontend for render resolution

        Returns:
            Render function or default fallback function
        """
        try:
            return self._registry.resolve(render_name, kind=RENDER, frontend=frontend).fn
        except ValueError:
            # Render not found, return fallback function
            # Use local fallback to avoid dependency on plugins_renders being loaded
            def _fallback_render(item: Item, indent: str = "") -> str:
                return f"{indent}- {str(item)}"

            return _fallback_render

    def _is_row_aware(self, render_desc: RenderDescriptor | None) -> bool:
        """Does the render present row items themselves?

        A render declares `item_semantic: "row"` when it takes the raw row
        (render_sql_row and friends need the rowid to target the edit); every
        other render wants the row's columns.

        Args:
            render_desc: The render descriptor requested for the item, None for default rendering

        Returns:
            True when the render declares the "row" item semantic
        """
        if render_desc is None:
            return False
        metadata = self._registry.get_metadata(render_desc.name)
        return bool(metadata and metadata.meta.get("item_semantic") == "row")

    def _render_view(self, item: Item, row_aware: bool) -> Item:
        """The item as a render sees it.

        The row inserters (read_csv_rows, read_sql) declare
        `output_semantic: "row"`: their items carry the columns next to the
        row metadata (see _row_columns). Row-aware renders get the raw row;
        every other render gets the columns, so the dict-oriented renders
        (:table, :json, :org, ...) show them without knowing rows exist.

        Args:
            item: The forest item to render
            row_aware: Whether the render presents rows themselves

        Returns:
            The columns dict for a row item shown by a non-row-aware render, the item otherwise
        """
        if row_aware or isinstance(item, dict):
            return item
        return _row_columns(item) or item

    def _apply_render(
        self, item: Item, render_desc: RenderDescriptor | None, render_fn: Callable, indent: str = "", depth: int = 0
    ) -> str:
        """Apply a render descriptor to an item.

        Args:
            item: The item to render (can be a dict with 'item' key and additional kwargs)
            render_desc: The render descriptor (may be None for default rendering)
            render_fn: The render function to apply
            indent: Indentation string (default: "")
            depth: Depth of the item in the forest (default: 0)

        Special keys (attrs, value, ...) are passed to the render only when it declares them.
        A render without an `attrs` parameter still gets the item itself: attributes can be
        loaded for sorting/filtering without taking part in rendering.
        Row items are passed as their columns unless the render is row-aware (see _render_view).

        Returns:
            Rendered string
        """
        try:
            # Extract item and keyword arguments if item is a dict with special keys
            actual_item = item
            special_kwargs: dict[str, Any] = {}
            special_keys = [
                "attrs",
                "key_descriptor",
                "key",
                "multiline_content",
                "value",  # For custom attribute renders
                "original_item",  # For custom attribute renders that need the original item
            ]

            if isinstance(item, dict):
                if "item" in item:
                    # Standard format: {"item": ..., "attr_value": ..., etc}
                    actual_item = item["item"]
                    for key in special_keys:
                        if key in item:
                            special_kwargs[key] = item[key]
                elif "original_item" in item or any(key in item for key in special_keys):
                    # Special keys format: {"key_descriptor": ..., "key": ...}
                    # or custom attribute format: {"_type": "attribute_value", "value": ..., "original_item": ...}
                    # Use the dict as actual_item but also extract special keys
                    for key in special_keys:
                        if key in item:
                            special_kwargs[key] = item[key]

            # Row items are passed as their columns unless the render is row-aware
            actual_item = self._render_view(actual_item, self._is_row_aware(render_desc))

            sig = inspect.signature(render_fn)
            params = sig.parameters
            # **kwargs (VAR_KEYWORD) means the render takes anything, depth included
            accepts_all = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values())
            # Drop special keys the render does not declare instead of failing into the fallback
            extra_kwargs = {key: value for key, value in special_kwargs.items() if accepts_all or key in params}

            # Get args from render_desc, handling None case
            render_args = render_desc.args if render_desc else ()
            if accepts_all or "depth" in params:
                return render_fn(actual_item, indent=indent, depth=depth, *render_args, **extra_kwargs)
            else:
                return render_fn(actual_item, indent=indent, *render_args, **extra_kwargs)
        except Exception:
            # Fallback to default rendering if render fails
            return f"{indent}- {str(item)}"

    def _get_custom_render_attr(self, attr_ds: list[AttributeDescriptor]) -> tuple[str, AttributeDescriptor] | None:
        """Get custom render name and the attribute that defines it.

        Args:
            attr_ds: List of attribute descriptors

        Returns:
            Tuple of (render_name, key_descriptor) or None
        """
        for at_d in attr_ds:
            metadata = self._registry.get_metadata(at_d.name)
            if metadata and metadata.meta:
                render_name = metadata.meta.get("render")
                if render_name:
                    return render_name, at_d
        return None

    def _render_item_without_attrs(self, render_fn: Callable, item: Item, depth: int) -> RenderDecision:
        """Helper to render item without attributes."""
        return RenderDecision(
            render_fn=render_fn, render_item=item, indent="  " * depth, is_custom=False, attr_identity=""
        )

    def _first_item_render_desc(self, render_ds: list[RenderDescriptor]) -> RenderDescriptor | None:
        """First user render that renders a single item.

        Aggregate renders are wrappers: they compose the per-item rendered lines
        instead of replacing them, so they never serve as the per-item render.

        Args:
            render_ds: List of render descriptors (user-specified renders)

        Returns:
            RenderDescriptor or None when every user render is an aggregate
        """
        for render_d in render_ds:
            try:
                if not is_aggregate_render(self._registry, render_d.name):
                    return render_d
            except ValueError, AttributeError:
                pass
        return None

    def _determine_item_render(
        self,
        item: Item,
        forest: Forest,
        attr_ds: list[AttributeDescriptor],
        render_ds: list[RenderDescriptor],
        depth: int,
        storage: AttributeStorageAPI,
        frontend: str = FRONTEND_TEXT,
        for_aggregate: bool = False,
    ) -> RenderDecision | None:
        """Determine which render an item prefers.

        This method queries the 'render' system attribute that was set by pre_render().
        If the render attribute is not set, it falls back to determining the render inline.

        Args:
            item: The item to render
            forest: The forest being rendered
            attr_ds: List of attribute descriptors
            render_ds: List of render descriptors (user-specified renders)
            depth: Depth of the item
            storage: Attribute storage for accessing attribute values
            frontend: Requested output frontend for render resolution
            for_aggregate: Whether the item line is composed by an aggregate render,
                which owns the layout (indentation, bullets)

        Returns:
            RenderDecision or None if item should be skipped
        """
        # First, try to query the render attribute from storage (set by pre_render)
        render_at_d = RENDER_ATTR
        render_name = storage.get_attr_value(render_at_d, item)

        if render_name:
            # Render attribute was set by pre_render, use it
            # Check if this is a custom attribute render (attribute has custom render in metadata)
            is_custom_attr_render = False
            attr_identity = ""
            custom_render_at_d = self._get_custom_render_attr(attr_ds)
            if custom_render_at_d:
                is_custom_attr_render = True
                attr_identity = custom_render_at_d[1].name

            # Resolve the render function
            render_fn = self._resolve_render_with_fallback(render_name, frontend)

            # Build the render_item based on what attributes are available
            if is_custom_attr_render and custom_render_at_d:
                # Custom attribute render
                at_d = custom_render_at_d[1]
                at_val = storage.get_attr_value(at_d, item)
                render_item = {
                    "_type": "attribute_value",
                    "value": at_val,
                    "original_item": item,
                }
                return RenderDecision(
                    render_fn=render_fn,
                    render_item=render_item,
                    indent="  " * depth,
                    is_custom=True,
                    attr_identity=attr_identity,
                )

            # Check if there are attributes to pass along
            if len(attr_ds) >= 1:
                attrs_dict = {at_d.name: storage.get_attr_value(at_d, item) for at_d in attr_ds}
                render_item = {"item": item, "attrs": attrs_dict}
                return RenderDecision(
                    render_fn=render_fn, render_item=render_item, indent="  " * depth, is_custom=False, attr_identity=""
                )
            else:
                return RenderDecision(
                    render_fn=render_fn, render_item=item, indent="  " * depth, is_custom=False, attr_identity=""
                )

        # Fallback: render attribute not set, determine inline (for pre_render phase)
        return self._determine_item_render_inline(
            item, forest, attr_ds, render_ds, depth, storage, frontend, for_aggregate=for_aggregate
        )

    def _render_group_inline(
        self,
        item: Group,
        attr_ds: list[AttributeDescriptor],
        render_ds: list[RenderDescriptor],
        depth: int,
        storage: AttributeStorageAPI,
        frontend: str = FRONTEND_TEXT,
    ) -> RenderDecision:
        """Determine render for Group items during pre_render phase."""
        # When user explicitly specifies :raw render, use it
        if render_ds and render_ds[0].name == "raw":
            render_name = "raw"
            reason = "group item with raw render"
        else:
            render_name = "group-header"
            reason = "group item"
        render_fn = self._resolve_render_with_fallback(render_name, frontend)
        return RenderDecision(
            render_fn=render_fn,
            render_item=item,
            indent="  " * depth,
            render_name=render_name,
            reason=reason,
        )

    def _determine_item_render_inline(
        self,
        item: Item,
        forest: Forest,
        attr_ds: list[AttributeDescriptor],
        render_ds: list[RenderDescriptor],
        depth: int,
        storage: AttributeStorageAPI,
        frontend: str = FRONTEND_TEXT,
        for_aggregate: bool = False,
    ) -> RenderDecision | None:
        """Determine which render an item prefers (inline logic, for pre_render phase).

        This is used by pre_render() to determine the render before storing it.
        During actual rendering, _determine_item_render() queries the stored value.

        Args:
            item: The item to render
            forest: The forest being rendered
            attr_ds: List of attribute descriptors
            render_ds: List of render descriptors (user-specified renders)
            depth: Depth of the item
            storage: Attribute storage for accessing attribute values
            frontend: Requested output frontend for render resolution
            for_aggregate: Whether the item line is composed by an aggregate render,
                which owns the layout; the attr-count fallback then yields bare
                content (lines-item) instead of a bulleted/table line

        Returns:
            RenderDecision or None if item should be skipped
        """
        # Group items have their own preference
        if isinstance(item, Group):
            return self._render_group_inline(item, attr_ds, render_ds, depth, storage, frontend)

        # Check if attribute has custom rendering
        custom_render_at_d = self._get_custom_render_attr(attr_ds)
        if custom_render_at_d:
            render_name = custom_render_at_d[0]
            at_d = custom_render_at_d[1]
            try:
                render_fn = self._registry.resolve(render_name, kind=RENDER, frontend=frontend).fn
                at_val = storage.get_attr_value(at_d, item)
                render_item = {
                    "_type": "attribute_value",
                    "value": at_val,
                    "original_item": item,
                }
                return RenderDecision(
                    render_fn=render_fn,
                    render_item=render_item,
                    indent="  " * depth,
                    is_custom=True,
                    attr_identity=at_d.name,
                    render_name=render_name,
                    reason=f"custom render from attribute metadata: {render_name} (from {at_d.name})",
                )
            except ValueError:
                pass  # Fall through to default handling

        # User specified renders - use first one that renders a single item
        # (aggregate renders compose these lines instead of replacing them)
        item_render_d = self._first_item_render_desc(render_ds)
        if item_render_d is not None:
            render_name = item_render_d.name
            render_fn = self._resolve_render_with_fallback(render_name, frontend)
            if len(attr_ds) == 1:
                at_d = attr_ds[0]
                at_val = storage.get_attr_value(at_d, item)
                render_item = {"item": item, "attrs": {at_d.name: at_val}}
                return RenderDecision(
                    render_fn=render_fn,
                    render_item=render_item,
                    indent="  " * depth,
                    render_name=render_name,
                    reason=f"user-specified render: {render_name}",
                )
            elif len(attr_ds) > 1:
                attrs_dict = {at_d.name: storage.get_attr_value(at_d, item) for at_d in attr_ds}
                render_item = {"item": item, "attrs": attrs_dict}
                return RenderDecision(
                    render_fn=render_fn,
                    render_item=render_item,
                    indent="  " * depth,
                    render_name=render_name,
                    reason=f"user-specified render: {render_name}",
                )
            else:
                d = self._render_item_without_attrs(render_fn, item, depth)
                d.render_name = render_name
                d.reason = f"user-specified render: {render_name}"
                return d

        # No user preference - determine based on attribute count; under an
        # aggregate render the line stays bare because the aggregate owns the layout
        default_item_render = "lines-item" if for_aggregate else "term-list-item"
        if len(attr_ds) == 0:
            render_name = default_item_render
            render_fn = self._resolve_render_with_fallback(render_name, frontend)
            d = self._render_item_without_attrs(render_fn, item, depth)
            d.render_name = render_name
            d.reason = "no attrs, no user render"
            return d
        elif len(attr_ds) == 1:
            render_name = default_item_render
            render_fn = self._resolve_render_with_fallback(render_name, frontend)
            at_d = attr_ds[0]
            at_val = storage.get_attr_value(at_d, item)
            render_item = {"item": item, "attrs": {at_d.name: at_val}}
            return RenderDecision(
                render_fn=render_fn,
                render_item=render_item,
                indent="  " * depth,
                render_name=render_name,
                reason=f"1 attr ({attr_ds[0].name}), no user render",
            )
        else:
            render_name = "lines-item" if for_aggregate else "table-row"
            attr_identities = ", ".join(at_d.name for at_d in attr_ds)
            render_fn = self._resolve_render_with_fallback(render_name, frontend)
            attrs_dict = {at_d.name: storage.get_attr_value(at_d, item) for at_d in attr_ds}
            render_item = {"item": item, "attrs": attrs_dict}
            return RenderDecision(
                render_fn=render_fn,
                render_item=render_item,
                indent="  " * depth,
                render_name=render_name,
                reason=f"{len(attr_ds)} attrs ({attr_identities}), no user render",
            )

    def _render_single_item(
        self,
        rd: RenderDecision,
        depth: int,
    ) -> str:
        """Render a single item with its preferred render.

        Args:
            rd: RenderDecision with render function, item, indent, and metadata
            depth: Depth of the item

        Returns:
            Rendered string
        """
        render_fn = rd.render_fn
        render_item = rd.render_item
        indent = rd.indent
        render_desc = rd.render_desc

        # Special handling for :attr render - parse field_name from args
        if render_desc and render_desc.name == "attr" and render_desc.args:
            arg = render_desc.args[0]
            field_name = arg.split("=", 1)[1] if arg.startswith("--field=") else arg
            # Extract attrs from render_item if present
            attrs = None
            if isinstance(render_item, dict):
                attrs = render_item.get("attrs", {})
            attr_item = (
                render_item.get("item") if isinstance(render_item, dict) and "item" in render_item else render_item
            )
            # Call render_attr directly with explicit parameters
            return render_fn(
                self._render_view(attr_item, self._is_row_aware(render_desc)),
                field_name=field_name,
                indent=indent,
                attrs=attrs,
            )

        # Renders decide themselves whether loaded attributes take part in the output:
        # renders declaring `attrs` label them (e.g. render_org_generic), renders without
        # `attrs` get the bare item. The engine adds no attribute decoration of its own.
        return self._apply_render(render_item, render_desc, render_fn, indent, depth)

    def _pre_render(
        self,
        forest: Forest,
        attr_ds: list[AttributeDescriptor],
        render_ds: list[RenderDescriptor],
        ctx: ExecContextAPI,
        storage: AttributeStorageAPI | None = None,
        frontend: str = FRONTEND_TEXT,
        for_aggregate: bool = False,
    ) -> None:
        """Pre-render phase: determine which render will be used for each item.

        This phase calculates which render will be used for each item
        and stores this information as the 'render' system attribute.

        Args:
            forest: The forest to pre-render
            attr_ds: List of attribute descriptors
            render_ds: List of render descriptors
            ctx: Execution context for query-time logging
            storage: Attribute storage for storing values
            frontend: Requested output frontend for render resolution
            for_aggregate: Whether an aggregate render composes the item lines
        """
        # Get storage from attribute_runtime if not provided
        if storage is None:
            storage = self._attribute_storage
        assert storage is not None

        # Get attribute descriptor for render system attribute
        render_at_d = RENDER_ATTR

        # Process each item to determine render and set system attribute
        logged_renders: set[str] = set()
        for depth, item in forest.as_pairs():
            # Determine which render to use (use inline version to avoid circular dependency)
            render_result = self._determine_item_render_inline(
                item, forest, attr_ds, render_ds, depth, storage, frontend, for_aggregate=for_aggregate
            )

            # Extract render name from result
            if render_result:
                render_name = render_result.render_name
                reason = render_result.reason
            else:
                # Fallback to default
                render_name = "term-list-item"
                reason = "no render determined (fallback)"

            # Log each unique render decision once
            if reason not in logged_renders:
                logged_renders.add(reason)
                ctx.debug(f"Render: {render_name} ({reason})")

            # Store render as system attribute
            storage.set_attr_value(render_at_d, item, render_name)
