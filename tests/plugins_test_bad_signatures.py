"""Tools that deliberately violate their kind's signature rule.

Kept out of plugins_test.py on purpose: validate_signature runs at register time,
so a violating tool fails to load and would take the whole module with it.
Only the tests asserting the rejection load this module.
"""

from udan.core_tools_loading.api_annotated import annotated

DOMAIN = "test_bad_signatures"


@annotated
def filter_bad(div: int) -> bool:
    return div > 0


@annotated
def group_bad(x: str) -> str:
    return x
