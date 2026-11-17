"""Tests for help and help_list (plugins_help) and introspect_tool (plugins_system)."""

import importlib
from pathlib import Path

import pytest

import udan.attributes.plugins_operators_attribute
import udan.plugins_history.plugins_history
import udan.plugins_tools_core.plugins_help
import udan.plugins_tools_core.plugins_system
import udan.plugins_tools_examples.plugins_builtins
import udan.plugins_tools_examples.plugins_fs
import udan.renders.plugins_renders
from tests.conftest import make_qp, register_tools_from_module
from udan.core_tools_loading.api_tools import KindArg, ToolKind


@pytest.fixture
def ctx_with_builtins(make_ctx):
    """Provide an UdanContext with builtins, system, history, and renders plugins registered."""
    ctx = make_ctx()
    register_tools_from_module(ctx, udan.plugins_tools_examples.plugins_builtins.__name__)
    register_tools_from_module(ctx, udan.attributes.plugins_operators_attribute.__name__)
    register_tools_from_module(ctx, udan.plugins_tools_core.plugins_help.__name__)
    register_tools_from_module(ctx, udan.plugins_tools_core.plugins_system.__name__)
    register_tools_from_module(ctx, udan.plugins_history.plugins_history.__name__)
    register_tools_from_module(ctx, udan.renders.plugins_renders.__name__)
    return ctx


def test_help_shows_all_tools(ctx_with_builtins):
    qp_with_builtins = make_qp(ctx_with_builtins)
    """Test that ? returns tool metadata as dicts."""
    _, attrs, render, out = qp_with_builtins.execute_query("?")

    # Check that render_help is in the output
    lines = out.strip().split("\n")

    # Find the render_help line (description is truncated with "...")
    render_help_lines = [line for line in lines if line.startswith("  - system.render_help ::")]
    assert len(render_help_lines) == 1
    assert "render_help ::" in render_help_lines[0]
    assert "Show help for a render" in render_help_lines[0]
    assert "[" in render_help_lines[0]  # Has location in brackets


def test_help_raw_output_format(ctx_with_builtins):
    qp_with_builtins = make_qp(ctx_with_builtins)
    """Test that :raw ? shows help for the :raw render."""
    _, attrs, render, out = qp_with_builtins.execute_query(":raw ?")

    # Check that the output contains the expected elements
    assert "renders.raw (render)" in out
    assert "Render item as raw string (str() representation)." in out
    assert "[" in out  # Has location in brackets on name line (e.g., [src/udan/...])


def test_help_exact_alias_shows_docs(ctx_with_builtins):
    qp_with_builtins = make_qp(ctx_with_builtins)
    """Test that an exact alias match shows the tool's docs, not the listing.

    `uniq` names `unique` exactly (its alias), so the docs win even though the
    name also matches the listing by substring.
    """
    _, attrs, render, out = qp_with_builtins.execute_query("help uniq")

    assert out.startswith("- unique (replacer)")
    assert "Remove duplicate items" in out


def test_help_exact_qualified_name_shows_docs(ctx_with_builtins):
    qp_with_builtins = make_qp(ctx_with_builtins)
    """Test that an exact name match shows the docs instead of the listing.

    `fs.relative_path` names one tool exactly; `relative_path_update`
    merely contains that pattern as a substring and must not turn the answer
    into a two-entry listing.
    """
    register_tools_from_module(ctx_with_builtins, udan.plugins_tools_examples.plugins_fs.__name__)

    _, attrs, render, out = qp_with_builtins.execute_query("fs.relative_path?")

    assert out.startswith("- fs.relative_path (attribute)")
    assert "relative_path_update" not in out


def test_help_dashed_name_shows_docs(ctx_with_builtins):
    """Test that the dashed spelling of a name shows the tool's docs.

    `ls-files` names `ls_files` the way the resolver's dash sugar names a
    written tool: `ls-files?` is the page `ls_files?` shows, not the
    unfiltered listing the no-match pattern falls back to.
    """
    register_tools_from_module(ctx_with_builtins, udan.plugins_tools_examples.plugins_fs.__name__)
    qp_fs = make_qp(ctx_with_builtins)

    _, attrs, render, out_dashed = qp_fs.execute_query("ls-files?")
    _, attrs, render, out_typed = qp_fs.execute_query("ls_files?")

    assert out_dashed == out_typed
    assert out_dashed.startswith("- fs.insert_ls_files (inserter)")
    assert "List files in a directory" in out_dashed


def test_help_dashed_pattern_narrows_the_listing(ctx_with_builtins):
    """Test that a dashed pattern fragment narrows the listing to the underscored tool."""
    register_tools_from_module(ctx_with_builtins, udan.plugins_tools_examples.plugins_fs.__name__)
    qp_fs = make_qp(ctx_with_builtins)

    _, attrs, render, out = qp_fs.execute_query("? ls-fi")

    assert "fs.insert_ls_files" in out
    assert "domain=aggregates" not in out


def test_help_list_dashed_pattern(ctx_with_builtins):
    """Test that help_list matches a dashed pattern against the underscored name."""
    register_tools_from_module(ctx_with_builtins, udan.plugins_tools_examples.plugins_fs.__name__)
    rows = udan.plugins_tools_core.plugins_help.help_list(pattern="ls-files", registry=ctx_with_builtins.registry)

    assert [row["name"] for row in rows] == ["fs.insert_ls_files"]


def test_help_filter_by_alias_raw(ctx_with_builtins):
    qp_with_builtins = make_qp(ctx_with_builtins)
    """Test that help filters by alias 'raw' to find 'render_raw'."""
    _, attrs, render, out = qp_with_builtins.execute_query("help raw")

    # Should find the 'render_raw' render which has alias 'raw'
    assert "render_raw" in out
    assert "Render item as raw string" in out


def test_help_filter_by_substring_list(ctx_with_builtins):
    qp_with_builtins = make_qp(ctx_with_builtins)
    """Test that help filters by substring '_list' to find 'help_list'."""
    _, attrs, render, out = qp_with_builtins.execute_query("help _list")

    # '_list' is not a name on its own, so the substring listing is shown
    assert "help_list" in out
    assert "Return metadata for all tools" in out


def test_help_filter_by_alias_attr(ctx_with_builtins):
    qp_with_builtins = make_qp(ctx_with_builtins)
    """Test that help filters by alias 'attr' to find 'render_attr'."""
    _, attrs, render, out = qp_with_builtins.execute_query("help attr")

    # Should find the 'render_attr' render which has alias 'attr'
    assert "render_attr" in out
    assert "Render an item by extracting a specific field" in out


def test_help_filter_by_alias_grep(ctx_with_builtins):
    qp_with_builtins = make_qp(ctx_with_builtins)
    """Test that help filters by alias 'grep' to find 'has_pattern'."""
    _, attrs, render, out = qp_with_builtins.execute_query("help grep")

    # Should find 'has_pattern' which has alias 'grep'
    assert "has_pattern" in out
    assert "Check if pattern matches the item" in out


def test_help_filter_by_alias_grepv(ctx_with_builtins):
    qp_with_builtins = make_qp(ctx_with_builtins)
    """Test that help filters by alias 'grepv' to find 'has_not_pattern'."""
    _, attrs, render, out = qp_with_builtins.execute_query("help grepv")

    # Should find 'has_not_pattern' which has alias 'grepv'
    assert "has_not_pattern" in out
    assert "Check if pattern does NOT match the item" in out


def test_help_list_filters_by_concrete_type(ctx_with_builtins):
    """Test that a concrete tool_type (inserter) matches only that kind."""
    rows = udan.plugins_tools_core.plugins_help.help_list(tool_type="inserter", registry=ctx_with_builtins.registry)

    assert rows
    assert {row["type"] for row in rows} == {"inserter"}


def test_help_list_filters_attributes(ctx_with_builtins):
    """Test that tool_type=attribute returns only attributes."""
    rows = udan.plugins_tools_core.plugins_help.help_list(tool_type="attribute", registry=ctx_with_builtins.registry)

    assert rows
    assert {row["type"] for row in rows} == {"attribute"}


def test_help_list_filters_renders(ctx_with_builtins):
    """Test that tool_type=render returns only renders."""
    rows = udan.plugins_tools_core.plugins_help.help_list(tool_type="render", registry=ctx_with_builtins.registry)

    assert rows
    assert {row["type"] for row in rows} == {"render"}


def test_help_list_filters_operators(ctx_with_builtins):
    """Test that tool_type=operator returns operator kinds but not renders or attributes."""
    rows = udan.plugins_tools_core.plugins_help.help_list(tool_type="operator", registry=ctx_with_builtins.registry)

    assert rows
    types = {row["type"] for row in rows}
    assert "render" not in types
    assert "attribute" not in types


def test_help_list_unknown_type_returns_empty(ctx_with_builtins):
    """Test that an unknown tool_type matches nothing instead of everything."""
    rows = udan.plugins_tools_core.plugins_help.help_list(
        tool_type="nonexistent_kind", registry=ctx_with_builtins.registry
    )

    assert rows == []


EXTENDER_ON_DEPTH_LINE = (
    "    on_depth: depth :: Extend only the nodes at that depth (0 = top level); 'all' extends every node, "
    "'leaf' only the ones without children"
)
EXTENDER_MAX_DEPTH_LINE = (
    "    max_depth: integer :: Recursion levels beyond the first extension (0 = extend once, the default)"
)
EXTENDER_POSITION_LINE = (
    "    position: path :: Extend only the node at that hierarchical position "
    "(1.2 = children[1].children[2]); the other nodes pass through untouched; "
    "-1 or the empty path switches it off"
)
GROUPER_POSITION_LINE = (
    "    position: path :: Group only the children of the node at that hierarchical position "
    "(1.2 = children[1].children[2]); the other nodes pass through untouched; "
    "-1 or the empty path switches it off"
)
FILTER_ON_DEPTH_LINE = (
    "    on_depth: depth :: Filter only the items at that depth (0 = top level); 'all' filters every item, "
    "'leaf' only the ones without children"
)


def test_introspect_tool_shows_extender_args(ctx_with_builtins):
    """Test that an extender's help lists the framework arguments its kind accepts."""
    qp_with_builtins = make_qp(ctx_with_builtins)
    _, attrs, render, out = qp_with_builtins.execute_query("help extend_by_attribute")

    lines = out.strip().split("\n")
    header_idx = lines.index("Extender args:")
    assert lines[header_idx + 1] == EXTENDER_ON_DEPTH_LINE
    assert lines[header_idx + 2] == EXTENDER_MAX_DEPTH_LINE
    assert lines[header_idx + 3] == EXTENDER_POSITION_LINE


def test_introspect_tool_shows_grouper_args(ctx_with_builtins):
    """Test that a grouper's help lists the framework arguments its kind accepts."""
    qp_with_builtins = make_qp(ctx_with_builtins)
    _, attrs, render, out = qp_with_builtins.execute_query("help group_by_field")

    lines = out.strip().split("\n")
    header_idx = lines.index("Grouper args:")
    assert lines[header_idx + 1] == GROUPER_POSITION_LINE


def test_introspect_tool_shows_filter_args(ctx_with_builtins):
    """Test that a filter's help lists only the framework arguments a filter accepts."""
    qp_with_builtins = make_qp(ctx_with_builtins)
    _, attrs, render, out = qp_with_builtins.execute_query("help grep")

    lines = out.strip().split("\n")
    header_idx = lines.index("Filter args:")
    assert lines[header_idx + 1] == FILTER_ON_DEPTH_LINE
    assert "max_depth" not in out


def test_introspect_tool_does_not_repeat_documented_args(ctx_with_builtins):
    """Test that a parameter the description's Args section documents gets no extra line."""
    qp_with_builtins = make_qp(ctx_with_builtins)
    _, attrs, render, out = qp_with_builtins.execute_query("help group_by_field")

    lines = out.strip().split("\n")
    assert "    field: Field name to group by" in lines
    assert "  - field: string!" not in lines


def test_introspect_tool_without_kind_args(ctx_with_builtins):
    """Test that a tool whose kind accepts no framework arguments gets no section."""
    qp_with_builtins = make_qp(ctx_with_builtins)
    _, attrs, render, out = qp_with_builtins.execute_query("help uniq")

    assert out.startswith("- unique (replacer)")
    assert "Replacer args:" not in out


def test_kind_args_block_builds_section():
    """Test the block builder: header plus one indented line per arg, empty without args."""
    kind = ToolKind(
        name="extender",
        kind_args=(KindArg(name="on_depth", arg_type="integer", description="Extend only that depth"),),
    )

    assert (
        udan.plugins_tools_core.plugins_system._kind_args_block(kind)
        == "Extender args:\n    on_depth: integer :: Extend only that depth"
    )
    assert udan.plugins_tools_core.plugins_system._kind_args_block(ToolKind(name="grouper")) == ""


def test_docstring_arg_names_reads_args_section():
    """Test the Args-section reader: base-indent entries, continuations and later sections."""
    description = (
        "Group items.\n"
        "\n"
        "Args:\n"
        "    field: The field to group by\n"
        "          continued on the next line\n"
        "    desc: Order of the groups\n"
        "\n"
        "Returns:\n"
        "    The group key\n"
    )

    assert udan.plugins_tools_core.plugins_system._docstring_arg_names(description) == {"field", "desc"}
    assert udan.plugins_tools_core.plugins_system._docstring_arg_names("Remove duplicate items.") == set()


def test_question_atom_is_the_listing_alias(ctx_with_builtins):
    qp_with_builtins = make_qp(ctx_with_builtins)
    """`?` resolves through its alias: the same output the written `help` shows."""
    _, _, _, out_atom, _ = qp_with_builtins.execute_query_split_debug("?")
    _, _, _, out_written, _ = qp_with_builtins.execute_query_split_debug("help")

    assert out_atom == out_written
    assert "domain=builtins" in out_atom


def test_question_atom_keeps_listing_arguments(ctx_with_builtins):
    """`? uniq` and `? _list --group=type` are the written forms through the alias."""
    qp_with_builtins = make_qp(ctx_with_builtins)
    _, _, _, out_docs, _ = qp_with_builtins.execute_query_split_debug("? uniq")
    _, _, _, out_docs_written, _ = qp_with_builtins.execute_query_split_debug("help uniq")

    assert out_docs == out_docs_written
    assert out_docs.startswith("- unique (replacer)")

    _, _, _, out_grouped, _ = qp_with_builtins.execute_query_split_debug("? _list --group=type")
    _, _, _, out_grouped_written, _ = qp_with_builtins.execute_query_split_debug("help _list --group=type")

    assert out_grouped == out_grouped_written
    assert "- type=inserter ::" in out_grouped


def test_listing_describes_the_question_alias(ctx_with_builtins):
    """The listing names the alias in the description; the alias is no row of its own."""
    qp_with_builtins = make_qp(ctx_with_builtins)
    _, _, _, out, _ = qp_with_builtins.execute_query_split_debug("?")

    help_rows = [line for line in out.splitlines() if "help.help ::" in line]
    assert len(help_rows) == 1
    assert "(aliases: ?)" in help_rows[0]


def test_location_path_shows_external_file_absolute(tmp_path):
    """A file outside the udan project shows its absolute location."""
    external = tmp_path / "plugins_ext.py"
    external.write_text("def insert_probe():\n    return []\n")

    location = udan.plugins_tools_core.plugins_system._format_location_path(str(external))

    assert location == str(external.resolve())


def test_location_path_resolves_symlinked_external_file(tmp_path):
    """A location recorded through a symlink shows the file's real path."""
    real = tmp_path / "real"
    real.mkdir()
    external = real / "plugins_ext.py"
    external.write_text("def insert_probe():\n    return []\n")
    (tmp_path / "ext").symlink_to(real)

    location = udan.plugins_tools_core.plugins_system._format_location_path(str(tmp_path / "ext" / "plugins_ext.py"))

    assert location == str(external.resolve())


def test_location_path_keeps_missing_external_file_as_recorded():
    """An external file the resolution cannot find on disk shows as it was recorded."""
    location = udan.plugins_tools_core.plugins_system._format_location_path("/tmp/nowhere/plugins_ext.py")

    assert location == "/tmp/nowhere/plugins_ext.py"


def test_location_path_keeps_project_file_relative(monkeypatch):
    """A file of the udan project keeps the short cwd-relative location."""
    project_root = Path(udan.plugins_tools_core.plugins_help.__file__).parents[3]
    own_file = project_root / "src/udan/plugins_tools_core/plugins_help.py"
    monkeypatch.chdir(project_root)

    location = udan.plugins_tools_core.plugins_system._format_location_path(str(own_file))

    assert location == "src/udan/plugins_tools_core/plugins_help.py"


def test_location_path_shows_project_file_absolute_outside_cwd(monkeypatch, tmp_path):
    """A udan file outside the cwd shows its absolute location."""
    own_file = Path(udan.plugins_tools_core.plugins_help.__file__)
    monkeypatch.chdir(tmp_path)

    location = udan.plugins_tools_core.plugins_system._format_location_path(str(own_file))

    assert location == str(own_file)


EXTERNAL_TOOL_SOURCE = '''
from udan.core_tools_loading.api_annotated import annotated


@annotated(meta={"tool_type": "inserter"})
def insert_external_probe() -> list[int]:
    """Insert one number."""
    return [7]
'''


def test_listing_shows_external_package_location_absolute(ctx_with_builtins, tmp_path, monkeypatch):
    """A tool of a package outside the udan project shows an absolute location."""
    package_dir = tmp_path / "udan_plugins_ext_fixture"
    package_dir.mkdir()
    (package_dir / "__init__.py").write_text("")
    module_file = package_dir / "plugins_ext_fixture.py"
    module_file.write_text(EXTERNAL_TOOL_SOURCE)
    monkeypatch.syspath_prepend(str(tmp_path))
    module = importlib.import_module("udan_plugins_ext_fixture.plugins_ext_fixture")

    register_tools_from_module(ctx_with_builtins, module.__name__)
    qp = make_qp(ctx_with_builtins)
    _, _, _, out = qp.execute_query("? external_probe")

    listing_line = next(line for line in out.splitlines() if line.startswith("  - insert_external_probe ::"))
    decorator_line = next(
        number
        for number, text in enumerate(module_file.read_text().splitlines(), start=1)
        if text.startswith("@annotated(")
    )

    assert listing_line.endswith(f"[{module_file.resolve()}:{decorator_line}]")
