"""A plugin module declaring a second frontend variant of an existing render.

The frontend axis is the render kind's variant axis (RENDER.variant_meta_key): one
render name can carry several renders, one per frontend, told apart by the FRONTEND
meta. This module registers a second variant of ':table' under the alias the text
variant already uses, so the frontend-aware read (`RenderEngineAPI.has_variant`) has
both sides of render resolution in one container.
"""

from typing import Any

from udan.core_tools_loading.api_annotated import annotated
from udan.renders.api_renders import FRONTEND, SHAPE_CHILDREN

FRONTEND_HTML: str = "html"
"""The frontend value this fixture's variant declares.

udan's own renders are text-only (api_renders.FRONTEND_TEXT is the only value a
core render names), so the fixture exercising the variant axis declares its
second value here, beside the render that declares it in meta.
"""


@annotated(
    meta={
        "item_type": "group",
        "tool_type": "render",
        "aliases": ["table"],
        "shape": SHAPE_CHILDREN,
        FRONTEND: FRONTEND_HTML,
    }
)
def render_html_table_test(depths: list[int], children: list[Any], attr_ds: list[Any]) -> str:
    """The html variant of ':table': markup instead of the text table."""
    return "<table/>"
