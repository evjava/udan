"""Public API for the render engine.

This module defines the public interface for rendering Forests to string
representations through render tools: the output step the core calls
(udan.core.api_output_engine.OutputEngineAPI), done by rendering.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from udan.attributes.api_attribute_storage import AttributeStorageAPI
from udan.core.api_exec_context import ExecContextAPI
from udan.core.api_forests import Forest
from udan.core.api_output_engine import OutputEngineAPI
from udan.renders.api_renders import FRONTEND_TEXT

if TYPE_CHECKING:
    from udan.core.api_attributes import AttributeDescriptor
    from udan.renders.api_renders import RenderDescriptor


class RenderEngineAPI(OutputEngineAPI):
    """API interface for rendering Forest to string representation.

    The output seam the core calls (OutputEngineAPI) and the render surface the
    render descriptors drive, in one contract: rendering is how the core's output
    step is done.
    """

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
        2. Find aggregate render (if any) - search through all render_ds
        3. If aggregate render found, pass items to it directly
        4. Otherwise, render each item with its preferred render
        5. Add debug log if debug mode is enabled

        Args:
            forest: The forest to render
            attr_ds: List of attribute descriptors to display
            render_tools: List of render descriptor objects
            ctx: Optional execution context for dependency injection in renders
            storage: Optional attribute storage for accessing attribute values
            frontend: Requested output frontend for render resolution

        Returns:
            String representation of the forest
        """
        raise NotImplementedError

    def has_variant(self, key: str, frontend: str = FRONTEND_TEXT) -> bool:
        """Check whether a render name is registered with a variant for the frontend.

        It lives here and not on the tools registry because the frontend axis is a
        word of the render domain: the render kind declares it as its
        `variant_meta_key` (api_renders.RENDER), the same reason `is_aggregate_render`
        is a render-domain answer and not a registry method. A frontend that embeds
        rendered output asks it to decide between passing the fragment through and
        escaping it: a render without a variant for the frontend resolved to its text
        variant, whose output is not safe to embed.

        Args:
            key: Render name or alias
            frontend: Requested output frontend

        Returns:
            True when a render variant for this frontend is registered under the name
        """
        raise NotImplementedError
