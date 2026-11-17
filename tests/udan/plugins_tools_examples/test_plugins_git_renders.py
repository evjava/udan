"""Tests for the git renders that moved with the plugin out of udan's core test files.

- ``test_org_diff_render_with_loaded_attribute`` came from udan's tests/test_impl_renders.py
- ``test_render_item_semantic_matches_level_semantic`` came from udan's tests/test_render_suggestions.py
"""

import pytest

from tests.conftest import make_qp
from udan.attributes import plugins_operators_attribute
from udan.attributes.api_attribute_storage import AttributeStorageAPI
from udan.core.api_attributes import AttributeDescriptor
from udan.core.api_forests import Forest
from udan.plugins_history import plugins_history
from udan.plugins_tools_core import plugins_help, plugins_system
from udan.plugins_tools_demo import plugins_demo, plugins_fruits
from udan.plugins_tools_examples import plugins_builtins, plugins_git, plugins_org
from udan.plugins_tools_examples.plugins_git import GitDiffFile
from udan.renders import plugins_renders
from udan.renders.api_renders import RenderDescriptor

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
MODULES_GIT = (*MODULES, plugins_git)


def _listed(out: str) -> list[str]:
    """Qualified names of the listing entries, in shown order."""
    return [line.strip()[2:].split(" :: ")[0] for line in out.splitlines() if line.startswith("  - ")]


@pytest.fixture
def advice(make_ctx):
    """Factory: the listing text of `query, :` executed on the given plugin set."""

    def _advice(query: str, modules: tuple) -> str:
        ctx = make_ctx(*modules)
        qp = make_qp(ctx)
        return qp.execute_query(f"{query}, :")[3]

    return _advice


def _diff_forest_with_attr(ctx) -> tuple[Forest, AttributeDescriptor]:
    """Forest of GitDiffFile items with a change-size attribute loaded into the store.

    GitDiffFile is unhashable, so values go through set_attr_value (id-keyed storage).
    """
    small = GitDiffFile(file_path="small.py", diff_content="+ c", additions=1, deletions=0)
    large = GitDiffFile(file_path="large.py", diff_content="- a\n+ b", additions=3, deletions=7)
    at_d = AttributeDescriptor(name="git_diff_file_size", args={})
    store = ctx.container.get(AttributeStorageAPI)
    store.set_attr_value(at_d, small, 1)
    store.set_attr_value(at_d, large, 10)
    return Forest(items=[small, large], depths=[0, 0]), at_d


def test_org_diff_render_with_loaded_attribute(make_ctx):
    """Regression: attribute loaded for sorting must not break the org-diff render.

    render_org_diff declares no `attrs` parameter; passing attrs to it used to raise
    TypeError and silently fall back to the raw item repr.
    """
    ctx = make_ctx(plugins_git, plugins_renders)
    forest, at_d = _diff_forest_with_attr(ctx)

    result = ctx._output.output_forest(forest, [at_d], [RenderDescriptor(name="org-diff")], ctx.create_exec_context())

    assert result == (
        "** small.py ( +1 -0 )\n"
        "#+begin_src diff\n"
        "+ c\n"
        "#+end_src\n"
        "** large.py ( +3 -7 )\n"
        "#+begin_src diff\n"
        "- a\n"
        "+ b\n"
        "#+end_src"
    )


def test_render_item_semantic_matches_level_semantic(advice):
    """The DiffHunk semantic puts the org-diff renders first in their group."""
    out = advice("insert_diff, extend_diff_hunks", modules=MODULES_GIT)

    names = _listed(out)
    assert names[0] == "git.render_org_diff_hunk"
    assert "git.render_org_diff" in names
    assert "renders.render_raw" in names
