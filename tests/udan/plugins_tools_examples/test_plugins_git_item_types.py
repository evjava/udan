"""Item-type contract of the git plugin's metadata.

Moved from udan's tests/test_impl_item_types.py together with the plugin: the
promoted ``item_type`` / ``output_type`` / semantic fields as declared by
udan.plugins_tools_examples.plugins_git.
"""

from udan.core.api_attributes import ATTRIBUTE
from udan.core_tools_loading.impl_tool_kinds import ToolKindsRegistry
from udan.core_tools_loading.impl_tools_loader import ToolsLoader
from udan.operator.plugins_operator_extender import EXTENDER
from udan.operator.plugins_operator_filter import FILTER
from udan.operator.plugins_operator_grouper import GROUPER
from udan.operator.plugins_operator_inserter import INSERTER
from udan.operator.plugins_operator_mapper import MAPPER
from udan.plugins_tools_examples import plugins_git
from udan.renders.api_renders import RENDER

# The kinds the core ships, and the operator kinds - all of them plugin kinds now - the
# git plugin's tools are declared as. Promoting ``output_type`` from meta to a
# typed field is validated against the kind's own item-type keys, so a loader built
# outside the container needs the vocabulary: without it every declared kind name
# resolves to a bare kind that carries no keys and the declared types stay unpromoted
# (None).
BUILTIN_KINDS: tuple = (ATTRIBUTE, RENDER, INSERTER, FILTER, EXTENDER, GROUPER, MAPPER)


def _builtin_kinds() -> ToolKindsRegistry:
    kinds = ToolKindsRegistry()
    for kind in BUILTIN_KINDS:
        kinds.register(kind)
    return kinds


def _load_git_metadatas() -> dict:
    loader = ToolsLoader(cache_dir=None, use_cache=False, kinds=_builtin_kinds())
    return {m.name: m for m, _ in loader.load_from_module(plugins_git)}


def test_loaded_git_metadatas_carry_fixed_types():
    metadatas = _load_git_metadatas()

    commits = metadatas["commits"]
    assert commits.output_type == "CommitInfo"
    assert commits.output_semantic is None

    insert_diff = metadatas["insert_diff"]
    assert insert_diff.output_type == "GitDiffFile"

    insert_status = metadatas["insert_status"]
    assert insert_status.output_type == "GitStatus"

    ext_commit_files = metadatas["extend_commit_files"]
    assert ext_commit_files.item_type == "CommitInfo"

    ext_diff_hunks = metadatas["extend_diff_hunks"]
    assert ext_diff_hunks.item_type == "GitDiffFile"
    assert ext_diff_hunks.output_type == "DiffHunk"

    ext_stash_show = metadatas["extend_stash_show"]
    assert ext_stash_show.item_type == "str"
    assert ext_stash_show.output_type == "GitDiffFile"


def test_loaded_git_renders_carry_item_type_and_semantic():
    metadatas = _load_git_metadatas()

    commit_log = metadatas["render_commit_log"]
    assert commit_log.meta["item_type"] == "dict"
    assert commit_log.meta["item_semantic"] == "CommitInfo"

    status_full = metadatas["render_status_full"]
    assert status_full.meta["item_type"] == "dict"
    assert status_full.meta["item_semantic"] == "GitStatus"

    org_diff = metadatas["render_org_diff"]
    assert org_diff.meta["item_type"] == "GitDiffFile"
    assert "item_semantic" not in org_diff.meta

    org_diff_hunk = metadatas["render_org_diff_hunk"]
    assert org_diff_hunk.meta["item_type"] == "GitDiffFile|DiffHunk"
    assert org_diff_hunk.meta["item_semantic"] == "DiffHunk"
