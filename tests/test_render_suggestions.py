"""Bare `:` render listing: the pipeline answers it like `:?`, filtered by the chain.

`query, :` lowers to the same help query as `query, :?`: the listing holds
the renders whose declared item_type fits the forest levels built so far (an
undeclared or "any" item type fits every chain), grouped by domain. A render
whose declared item semantic names one of the levels leads its group.
"""

import pytest

from tests.conftest import make_qp
from udan.attributes import plugins_operators_attribute
from udan.plugins_history import plugins_history
from udan.plugins_tools_core import plugins_help, plugins_system
from udan.plugins_tools_demo import plugins_demo, plugins_fruits
from udan.plugins_tools_examples import plugins_builtins, plugins_org
from udan.renders import plugins_renders

# plugins_org provides the org renders that insert_fruits endorses (supported_renders)
MODULES = (
    plugins_demo,
    plugins_fruits,
    plugins_builtins,
    plugins_operators_attribute,
    plugins_help,
    plugins_system,
    plugins_history,
    plugins_renders,
    plugins_org,
)


def _listed(out: str) -> list[str]:
    """Qualified names of the listing entries, in shown order."""
    return [line.strip()[2:].split(" :: ")[0] for line in out.splitlines() if line.startswith("  - ")]


@pytest.fixture
def advice(make_ctx):
    """Factory: the listing text of `query, :` executed on the given plugin set."""

    def _advice(query: str, modules: tuple = MODULES) -> str:
        ctx = make_ctx(*modules)
        qp = make_qp(ctx)
        return qp.execute_query(f"{query}, :")[3]

    return _advice


def test_colon_matches_render_question(make_ctx):
    """`:` and `:?` are one mechanism: the same chain gets the identical listing."""
    ctx = make_ctx(*MODULES)
    qp = make_qp(ctx)

    assert qp.execute_query("fruits, :")[3] == qp.execute_query("fruits, :?")[3]


def test_fruits_suggestions_type_filtered(advice):
    """The dict/fruit chain lists the fruit render and the dict renders; nothing else."""
    out = advice("fruits")

    assert _listed(out) == [
        "fruits.render_fruit",
        "renders.render_attr",
        "renders.render_attr_then_multiline",
        "renders.render_format",
        "renders.render_lines_item",
        "renders.render_list",
        "renders.render_raw",
        "renders.render_table",
        "renders.render_table_row",
        "renders.render_term_list_item",
    ]


def test_help_list_suggestions_type_filtered(advice):
    """The tool_metadata chain fits the same renders as the dict/fruit chain."""
    out = advice("help_list")

    assert "renders.render_attr ::" in out
    assert "renders.render_raw ::" in out
    # introspect-item renders tool_group items, which this chain does not provide
    assert "renders.render_introspect" not in out


def test_range_suggestions_have_no_dict_renders(advice):
    """range declares int items: dict and str renders drop out, any-typed stay."""
    out = advice("range 3")

    assert _listed(out) == [
        "renders.render_format",
        "renders.render_lines_item",
        "renders.render_list",
        "renders.render_raw",
        "renders.render_term_list_item",
    ]
