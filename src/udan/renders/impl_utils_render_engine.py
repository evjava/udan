"""Utility functions for render specification parsing."""

from udan.renders.api_renders import RenderDescriptor


def _parse_render_spec(render_spec: str) -> RenderDescriptor:
    """Parse a render specification string into a RenderDescriptor.

    Args:
        render_spec: String like ":org", ":org-item(id,name)", or ":org-item id name"

    Returns:
        RenderDescriptor with name (without leading colon) and args
    """
    # Strip leading colon if present
    if render_spec.startswith(":"):
        render_spec = render_spec[1:]

    # Check for parenthesized syntax: render-name(arg1,arg2,...)
    if "(" in render_spec and render_spec.endswith(")"):
        # Parse: org-item(id,name) -> name="org-item", args=("id", "name")
        name, args_str = render_spec.split("(", 1)
        args_str = args_str[:-1]  # Remove trailing ")"
        args = tuple(arg.strip() for arg in args_str.split(",")) if args_str.strip() else ()
        return RenderDescriptor.create(name, args)
    else:
        # Parse space-separated: org-item id name -> name="org-item", args=("id", "name")
        parts = render_spec.split()
        name = parts[0]
        args = tuple(parts[1:]) if len(parts) > 1 else ()
        return RenderDescriptor.create(name, args)
