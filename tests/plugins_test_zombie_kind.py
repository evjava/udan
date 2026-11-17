"""A tool whose kind no package declares.

The loader builds a bare kind from a tool_type the vocabulary does not know
(impl_utils_tools_loader), which is the state a dropped package used to produce:
the tool loads, the chain cannot interpret it. The scenario lives here since the
attribute kind's owner moved into udan (udan.attributes) - every chain-forming
kind's owner is core-internal now, so no module list can produce an unowned kind,
and UDAN-422's guarantee is exercised with a kind nothing declares instead.
"""

from udan.core_tools_loading.api_annotated import annotated


@annotated(meta={"tool_type": "zombie"})
def zombie_inserter() -> list[int]:
    """A chain-forming-shaped tool of a kind no package owns."""
    return [0, 1]
