"""Tests for markdown plugins."""

from pathlib import Path

from tests.conftest import make_qp, register_tools_from_module
from udan.plugins_tools_demo import plugins_demo, plugins_fruits
from udan.plugins_tools_examples import plugins_markdown
from udan.plugins_tools_examples.api_types import ASTChunk
from udan.plugins_tools_examples.plugins_markdown import (
    md_files,
    md_lines,
    md_search,
    md_table,
    render_markdown_generic,
)
from udan.plugins_tools_examples.plugins_org_parser import OrgItem
from udan.renders import plugins_tables


def test_md_files(tmp_path):
    """Test md_files inserter."""
    # Create test markdown files
    (tmp_path / "doc1.md").write_text("# Doc 1")
    (tmp_path / "doc2.md").write_text("# Doc 2")
    (tmp_path / "readme.txt").write_text("not markdown")

    # Test listing markdown files
    files = list(md_files(str(tmp_path)))
    assert len(files) == 2
    assert all(isinstance(f, Path) for f in files)

    file_names = {f.name for f in files}
    assert file_names == {"doc1.md", "doc2.md"}


def test_md_files_nonexistent_directory():
    """Test md_files with nonexistent directory."""
    files = list(md_files("/nonexistent/path"))
    assert len(files) == 0


def test_md_files_with_query(tmp_path, make_ctx):
    """Test md_files through query execution."""
    (tmp_path / "notes.md").write_text("# Notes")
    (tmp_path / "tasks.md").write_text("# Tasks")

    ctx = make_ctx()
    qp = make_qp(ctx)
    register_tools_from_module(ctx, md_files.__module__)

    forest, attrs, render_specs, out = qp.execute_query(f"md_files {tmp_path}")
    lines = out.strip().split("\n")
    # Check that both files are present with exact format
    assert len(lines) == 2
    # Each line should be "- {path}/{filename}"
    for line in lines:
        assert line.startswith("- ")
        assert line.endswith(".md")
    # Extract filenames and verify both are present
    file_names = [line.split("/")[-1] for line in lines]
    assert set(file_names) == {"notes.md", "tasks.md"}


def test_md_search(tmp_path):
    """Test md_search extender."""
    # Create test markdown file
    md_file = tmp_path / "test.md"
    md_file.write_text("# Header\nline with todo\nanother line\ntodo item")

    # Test searching for pattern
    results = list(md_search(md_file, r"todo"))
    assert len(results) == 2

    # Check format: {path}:{line} :: {match}
    for r in results:
        assert " :: " in r
        assert "todo" in r
        # Should contain line number like ":1 ::" or ":2 ::"
        assert ":" in r and " :: " in r

    # Test case-sensitive pattern
    md_file_upper = tmp_path / "upper.md"
    md_file_upper.write_text("TODO: fix\nTODO: implement\ntodo: small task")

    results_upper = list(md_search(md_file_upper, r"TODO"))
    assert len(results_upper) == 2
    assert all("TODO" in r for r in results_upper)

    results_lower = list(md_search(md_file_upper, r"todo"))
    assert len(results_lower) == 1
    assert "todo: small task" in results_lower[0]


def test_md_search_limit(tmp_path):
    """Test md_search with limit parameter."""
    content = "\n".join([f"line {i} with todo" for i in range(100)])
    md_file = tmp_path / "many.md"
    md_file.write_text(content)

    # Test default limit of 200
    results = list(md_search(md_file, r"todo"))
    assert len(results) == 100

    # Test custom limit
    results_limited = list(md_search(md_file, r"todo", limit=10))
    assert len(results_limited) == 10

    # Test limit=0 (unlimited)
    results_unlimited = list(md_search(md_file, r"todo", limit=0))
    assert len(results_unlimited) == 100


def test_md_search_non_path_item():
    """Test md_search with non-Path item."""
    results = list(md_search("not a path", r"todo"))
    assert len(results) == 0


def test_md_search_with_md_files_workflow(tmp_path):
    """Test workflow: md_files -> md_search."""
    # Create test markdown files
    (tmp_path / "doc1.md").write_text("# Doc 1\nTODO: task 1\nsome content")
    (tmp_path / "doc2.md").write_text("# Doc 2\nTODO: task 2\nother content")

    # Get files with md_files
    files = list(md_files(str(tmp_path)))
    assert len(files) == 2

    # Search each file with md_search
    all_todos = []
    for file in files:
        todos = list(md_search(file, r"TODO"))
        all_todos.extend(todos)

    assert len(all_todos) == 2
    assert all("TODO" in r for r in all_todos)


def test_md_search_with_query(tmp_path, make_ctx):
    """Test md_search through query execution."""
    md_file = tmp_path / "notes.md"
    md_file.write_text("# Notes\nTODO: implement feature\nTODO: fix bug")

    ctx = make_ctx()
    qp = make_qp(ctx)
    register_tools_from_module(ctx, md_files.__module__)

    # Query: insert files, then search for TODO
    # Note: Using just function names without insert_/extend_ prefixes
    # The system should resolve markdown.md_files -> md_files
    forest, attrs, render_specs, out = qp.execute_query(f"md_files {tmp_path}, md_search TODO")

    lines = out.strip().split("\n")
    # Should have multiple lines with the " :: " separator format
    separator_lines = [line for line in lines if " :: " in line]
    assert len(separator_lines) >= 2
    # At least some separator lines should have TODO in the match portion
    todo_lines = [line for line in separator_lines if "TODO" in line]
    assert len(todo_lines) >= 2


def test_md_lines_basic(tmp_path):
    """Test md_lines with basic pattern matching."""
    # Create test markdown files
    file1 = tmp_path / "test1.md"
    file1.write_text("# Header\nline with todo\ntodo item\nanother line")

    file2 = tmp_path / "test2.md"
    file2.write_text("## Section\nTODO: fix bug\nsomething else\ntodo: add feature")

    # Test finding lines with "todo" (case-sensitive)
    results = list(md_lines(str(tmp_path), r"todo"))
    assert len(results) == 3  # Only lowercase "todo", not "TODO"

    # Check that all results are strings
    assert all(isinstance(r, str) for r in results)

    # Check format: {path}:{line} :: {match}
    for r in results:
        assert " :: " in r
        assert ":" in r  # Should have line number

    # Check content
    assert "line with todo" in results[0] or "line with todo" in results[1] or "line with todo" in results[2]
    assert "todo item" in results[0] or "todo item" in results[1] or "todo item" in results[2]

    # Test case-insensitive pattern to get all 4
    results_ci = list(md_lines(str(tmp_path), r"(?i)todo"))
    assert len(results_ci) == 4


def test_md_lines_case_sensitive(tmp_path):
    """Test md_lines case sensitivity."""
    file1 = tmp_path / "case_test.md"
    file1.write_text("# Header\nTODO: fix\nTODO: implement\ntodo: small task")

    # Test case-sensitive pattern (uppercase TODO)
    results_upper = list(md_lines(str(tmp_path), r"TODO"))
    assert len(results_upper) == 2
    assert all("TODO" in r for r in results_upper)

    # Test lowercase pattern (only matches lowercase)
    results_lower = list(md_lines(str(tmp_path), r"todo"))
    assert len(results_lower) == 1
    assert "todo: small task" in results_lower[0]

    # Test case-insensitive pattern (matches all)
    results = list(md_lines(str(tmp_path), r"(?i)todo"))
    assert len(results) == 3


def test_md_lines_output_format(tmp_path):
    """Test output format: '- {path}:{line} :: {match}'."""
    content = "# Title\n## Section\nTODO: fix this"
    file1 = tmp_path / "format_test.md"
    file1.write_text(content)

    results = list(md_lines(str(tmp_path), r"TODO"))
    assert len(results) == 1

    # Check format: {path}:{line} :: {match}
    result = results[0]
    assert " :: " in result

    # Extract parts
    parts = result.split(" :: ", 1)
    prefix = parts[0]  # "{path}:{line}"
    match = parts[1]  # "{match}"

    # Check prefix format - should end with ":3" (line number)
    assert prefix.endswith(":3")
    assert "format_test.md" in prefix

    # Check match content
    assert match == "TODO: fix this"


def test_md_lines_no_matches(tmp_path):
    """Test md_lines when pattern doesn't match anything."""
    file1 = tmp_path / "empty.md"
    file1.write_text("# Header\nsome content\nno matches here")

    results = list(md_lines(str(tmp_path), r"NONEXISTENT"))
    assert len(results) == 0


def test_md_lines_no_markdown_files(tmp_path):
    """Test md_lines when directory has no markdown files."""
    # Create non-markdown files
    (tmp_path / "file.txt").write_text("content")
    (tmp_path / "file.py").write_text("code")

    results = list(md_lines(str(tmp_path), r"."))
    assert len(results) == 0


def test_md_lines_nonexistent_directory():
    """Test md_lines with nonexistent directory."""
    results = list(md_lines("/nonexistent/path", r"."))
    assert len(results) == 0


def test_md_lines_with_query(tmp_path, make_ctx):
    """Test md_lines through query execution."""
    # Create test markdown files
    file1 = tmp_path / "notes.md"
    file1.write_text("# Project Notes\n\nTODO: implement feature X\nTODO: fix bug Y\n")

    file2 = tmp_path / "ideas.md"
    file2.write_text("# Ideas\n\nTODO: research Z\n")

    ctx = make_ctx()
    qp = make_qp(ctx)
    register_tools_from_module(ctx, md_lines.__module__)

    # Query should show lines matching TODO
    forest, attrs, render_specs, out = qp.execute_query(f'md_lines {tmp_path} "TODO"')

    # Should show the formatted lines with separator
    lines = out.strip().split("\n")
    separator_lines = [line for line in lines if " :: " in line]
    assert len(separator_lines) >= 3
    # At least some separator lines should contain TODO
    todo_lines = [line for line in separator_lines if "TODO" in line]
    assert len(todo_lines) >= 3


def test_md_lines_regex_patterns(tmp_path):
    """Test md_lines with various regex patterns."""
    content = """# Header
## Subheader
### Subsubheader

- item 1
- item 2
* item 3

1. numbered
2. items

[link](url)
"""

    file1 = tmp_path / "patterns.md"
    file1.write_text(content)

    # Test headers pattern
    headers = list(md_lines(str(tmp_path), r"^#+"))
    assert len(headers) == 3

    # Test list items pattern
    list_items = list(md_lines(str(tmp_path), r"^[\s]*[-*]"))
    assert len(list_items) == 3

    # Test numbered list pattern
    numbered = list(md_lines(str(tmp_path), r"^\d+\."))
    assert len(numbered) == 2

    # Test link pattern
    links = list(md_lines(str(tmp_path), r"\[.*\]\(.*\)"))
    assert len(links) == 1


def test_md_lines_limit(tmp_path):
    """Test md_lines with limit parameter."""
    # Create file with many matching lines
    content = "\n".join([f"line {i} with todo" for i in range(100)])
    file1 = tmp_path / "many_lines.md"
    file1.write_text(content)

    # Test default limit of 200 (should return all 100)
    results = list(md_lines(str(tmp_path), r"todo"))
    assert len(results) == 100

    # Test custom limit
    results_limited = list(md_lines(str(tmp_path), r"todo", limit=10))
    assert len(results_limited) == 10

    # Test limit=1
    results_one = list(md_lines(str(tmp_path), r"todo", limit=1))
    assert len(results_one) == 1

    # Test limit=0 (unlimited)
    results_unlimited = list(md_lines(str(tmp_path), r"todo", limit=0))
    assert len(results_unlimited) == 100


def test_md_lines_limit_across_files(tmp_path):
    """Test limit behavior across multiple files."""
    # Create multiple files with matches
    file1 = tmp_path / "doc1.md"
    file1.write_text("\n".join([f"TODO: task {i}" for i in range(50)]))

    file2 = tmp_path / "doc2.md"
    file2.write_text("\n".join([f"TODO: task {i}" for i in range(50, 100)]))

    # Test limit=75 (should get 50 from first file, 25 from second)
    results = list(md_lines(str(tmp_path), r"TODO", limit=75))
    assert len(results) == 75

    # Verify file sources in output
    all_output = "\n".join(results)
    assert "doc1.md" in all_output
    assert "doc2.md" in all_output


def test_md_lines_limit_no_matches(tmp_path):
    """Test limit when pattern doesn't match anything."""
    file1 = tmp_path / "no_match.md"
    file1.write_text("# Header\nsome content\nno matches here")

    # Even with limit, should return empty list
    results = list(md_lines(str(tmp_path), r"NONEXISTENT", limit=10))
    assert len(results) == 0


def test_md_lines_two_documents_workflow(tmp_path):
    """Test complete workflow with two markdown documents."""
    # Document 1: Project tasks
    tasks = tmp_path / "TASKS.md"
    tasks.write_text("""# Project Tasks

## High Priority
- [ ] TODO: Implement authentication
- [ ] DONE: Fix login bug

## Low Priority
- [ ] TODO: Update documentation
- [ ] TODO: Add unit tests
""")

    # Document 2: Meeting notes
    notes = tmp_path / "NOTES.md"
    notes.write_text("""# Meeting Notes

## 2024-01-15
Discussed TODO: Implement authentication
Assigned to: John

## 2024-01-20
Reviewed DONE: Fix login bug
Verified fix works correctly
""")

    # Find all TODO items (case-sensitive, uppercase)
    todo_results = list(md_lines(str(tmp_path), r"TODO"))
    assert len(todo_results) == 4  # 3 in TASKS.md, 1 in NOTES.md

    # Verify file sources in output
    all_output = "\n".join(todo_results)
    assert "TASKS.md" in all_output
    assert "NOTES.md" in all_output

    # Find all lines with "authentication"
    auth_results = list(md_lines(str(tmp_path), r"authentication"))
    assert len(auth_results) == 2
    all_auth = "\n".join(auth_results)
    assert "TASKS.md" in all_auth
    assert "NOTES.md" in all_auth

    # Find checkboxes
    checkbox_results = list(md_lines(str(tmp_path), r"^- \["))
    assert len(checkbox_results) == 4
    all_checkboxes = "\n".join(checkbox_results)
    assert "TASKS.md" in all_checkboxes
    # Checkboxes only exist in TASKS.md
    assert "NOTES.md" not in all_checkboxes


TABLE_DOC = """# Report

| a | b | c | d |
|---|---|---|---|
| 1 | 2 | 3 | 4 |
| 5 | 6 | 7 | 8 |

plain text line
"""


def test_md_table(tmp_path):
    """Test md_table inserter."""
    md_file = tmp_path / "table.md"
    md_file.write_text(TABLE_DOC)

    results = list(md_table(f"{md_file}:3"))
    expected = [
        {"a": "1", "b": "2", "c": "3", "d": "4"},
        {"a": "5", "b": "6", "c": "7", "d": "8"},
    ]
    assert results == expected


def test_md_table_line_argument(tmp_path):
    """Test md_table with the line number as second argument."""
    md_file = tmp_path / "table.md"
    md_file.write_text(TABLE_DOC)

    results = list(md_table(str(md_file), 3))
    expected = [
        {"a": "1", "b": "2", "c": "3", "d": "4"},
        {"a": "5", "b": "6", "c": "7", "d": "8"},
    ]
    assert results == expected


def test_md_table_line_argument_string(tmp_path):
    """Test md_table with the line number passed as string."""
    md_file = tmp_path / "table.md"
    md_file.write_text(TABLE_DOC)

    results = list(md_table(str(md_file), "5"))
    expected = [
        {"a": "1", "b": "2", "c": "3", "d": "4"},
        {"a": "5", "b": "6", "c": "7", "d": "8"},
    ]
    assert results == expected


def test_md_table_location_anywhere_in_table(tmp_path):
    """Test md_table with location on delimiter and body rows."""
    md_file = tmp_path / "table.md"
    md_file.write_text(TABLE_DOC)

    expected = [
        {"a": "1", "b": "2", "c": "3", "d": "4"},
        {"a": "5", "b": "6", "c": "7", "d": "8"},
    ]
    assert list(md_table(f"{md_file}:4")) == expected
    assert list(md_table(f"{md_file}:6")) == expected


def test_md_table_no_pipes(tmp_path):
    """Test md_table with a table written without outer pipes."""
    md_file = tmp_path / "no_pipes.md"
    md_file.write_text("a | b\n--- | ---\n1 | 2\n")

    results = list(md_table(f"{md_file}:1"))
    assert results == [{"a": "1", "b": "2"}]


def test_md_table_escaped_pipe(tmp_path):
    """Test md_table with an escaped pipe (\\|) inside a cell."""
    md_file = tmp_path / "escaped.md"
    md_file.write_text("| a \\| b | c |\n|---|---|\n| 1 \\| x | 2 |\n")

    results = list(md_table(f"{md_file}:3"))
    assert results == [{"a \\| b": "1 \\| x", "c": "2"}]


def test_md_table_escaped_pipe_at_row_end(tmp_path):
    """Test md_table when a row ends with an escaped pipe."""
    md_file = tmp_path / "escaped_end.md"
    md_file.write_text("| a | b\n|---|---\n| 1 | 2 \\|\n")

    results = list(md_table(f"{md_file}:3"))
    assert results == [{"a": "1", "b": "2 \\|"}]


def test_md_table_missing_cells(tmp_path):
    """Test md_table when a row has fewer cells than columns."""
    md_file = tmp_path / "ragged.md"
    md_file.write_text("| a | b |\n|---|---|\n| 1 |\n")

    results = list(md_table(f"{md_file}:3"))
    assert results == [{"a": "1", "b": ""}]


def test_md_table_no_table(tmp_path):
    """Test md_table when the line is not inside a table."""
    md_file = tmp_path / "plain.md"
    md_file.write_text("# Header\nno table here\n")

    assert list(md_table(f"{md_file}:2")) == []


def test_md_table_invalid_location(tmp_path):
    """Test md_table with malformed location or out-of-range line."""
    md_file = tmp_path / "table.md"
    md_file.write_text("| a |\n|---|\n| 1 |\n")

    assert list(md_table("no-line-number")) == []
    assert list(md_table(str(md_file), 99)) == []
    assert list(md_table(f"{md_file}:99")) == []
    assert list(md_table("/nonexistent/file.md:1")) == []


def test_md_table_with_query(tmp_path, make_ctx):
    """Test md_table with :entries render through query execution."""
    md_file = tmp_path / "table.md"
    md_file.write_text("| a | b |\n|---|---|\n| 1 | 2 |\n")

    ctx = make_ctx(plugins_markdown, plugins_tables)
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query(f'md_table "{md_file}:1", :entries')

    expected = "** entry-1\n- a :: 1\n- b :: 2"
    assert out == expected


def test_md_table_line_argument_with_query(tmp_path, make_ctx):
    """Test md_table second-argument form through query execution."""
    md_file = tmp_path / "table.md"
    md_file.write_text("| a | b |\n|---|---|\n| 1 | 2 |\n| 3 | 4 |\n")

    ctx = make_ctx(plugins_markdown, plugins_tables)
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query(f'md_table "{md_file}" 1, :entries')

    expected = "** entry-1\n- a :: 1\n- b :: 2\n** entry-2\n- a :: 3\n- b :: 4"
    assert out == expected


def test_md_table_transpose(tmp_path):
    """Test md_table with transpose: header becomes first data column."""
    md_file = tmp_path / "table.md"
    md_file.write_text(TABLE_DOC)

    results = list(md_table(f"{md_file}:3", transpose=True))
    expected = [
        {"a": "b", "1": "2", "5": "6"},
        {"a": "c", "1": "3", "5": "7"},
        {"a": "d", "1": "4", "5": "8"},
    ]
    assert results == expected


def test_md_table_transpose_alias(tmp_path):
    """Test md_table transpose via the short t alias."""
    md_file = tmp_path / "table.md"
    md_file.write_text(TABLE_DOC)

    results = list(md_table(f"{md_file}:3", t=True))
    expected = [
        {"a": "b", "1": "2", "5": "6"},
        {"a": "c", "1": "3", "5": "7"},
        {"a": "d", "1": "4", "5": "8"},
    ]
    assert results == expected


def test_md_table_transpose_string_true(tmp_path):
    """Test md_table transpose with the flag value arriving as a string."""
    md_file = tmp_path / "table.md"
    md_file.write_text("| a | b |\n|---|---|\n| 1 | 2 |\n")

    assert list(md_table(f"{md_file}:3", transpose="true")) == [{"a": "b", "1": "2"}]
    assert list(md_table(f"{md_file}:3", transpose="false")) == [{"a": "1", "b": "2"}]


def test_md_table_transpose_with_query(tmp_path, make_ctx):
    """Test md_table transpose flags through query execution."""
    md_file = tmp_path / "table.md"
    md_file.write_text("| a | b |\n|---|---|\n| 1 | 2 |\n")

    ctx = make_ctx(plugins_markdown, plugins_tables)
    qp = make_qp(ctx)

    expected = "** entry-1\n- a :: b\n- 1 :: 2"
    for flag in ("--transpose", "--t", "--transpose=True"):
        forest, attrs, render_specs, out = qp.execute_query(f'md_table "{md_file}:1" {flag}, :entries')
        assert out == expected


def test_render_markdown_generic():
    """Test markdown render at different depths."""
    assert render_markdown_generic("apple") == "# apple"
    assert render_markdown_generic("apple", depth=1) == "## apple"
    assert render_markdown_generic("apple", depth=2) == "### apple"


def test_render_markdown_generic_indent():
    """Test markdown render with indent."""
    # Heading lines never have leading spaces
    # Only metadata list gets indented
    item = {"id": 1, "name": "apple"}
    result = render_markdown_generic(item, indent="  ", depth=1)
    lines = result.split("\n")
    assert lines[0] == "## 1 apple"  # No indent on heading
    assert lines[1] == "  - **id**: 1"  # Indent on metadata


def test_render_markdown_generic_dict():
    """Test markdown render for dicts."""
    item = {"id": 1, "name": "apple"}
    result = render_markdown_generic(item)
    expected = "# 1 apple\n- **id**: 1\n- **name**: apple"
    assert result == expected


def test_render_markdown_generic_org_item():
    """Test markdown render for OrgItem."""
    item = OrgItem(level=2, title="reading list", date="21.07.23-01:20:09", tags=["python"], content="some notes")
    result = render_markdown_generic(item)
    expected = "## reading list\ndate: 21.07.23-01:20:09\ntags: python\nsome notes"
    assert result == expected


def test_render_markdown_generic_astchunk():
    """Test markdown render for ASTChunk."""
    item = ASTChunk(
        type="function",
        name="foo",
        source_file="src/mod.py",
        line_start_number=3,
        line_end_number=5,
        docstring="Does foo.\nSecond line.",
        full_code="def foo():\n    return 1",
    )
    result = render_markdown_generic(item)
    expected = (
        "# def foo\n"
        "- **source_file**: src/mod.py:3-5\n"
        "- **docstring**: Does foo.\n"
        "\n"
        "```python\n"
        "  def foo():\n"
        "      return 1\n"
        "```"
    )
    assert result == expected


def test_markdown_render_with_query(make_ctx):
    """Test :markdown render through query execution."""
    ctx = make_ctx(plugins_demo, plugins_fruits, plugins_markdown)
    qp = make_qp(ctx)
    forest, attrs, render_specs, out = qp.execute_query("range 1 5, extend_multiply 1 2 3, :markdown")

    expected = "\n".join(
        [
            "# 1",
            "## 1",
            "## 2",
            "## 3",
            "# 2",
            "## 2",
            "## 4",
            "## 6",
            "# 3",
            "## 3",
            "## 6",
            "## 9",
            "# 4",
            "## 4",
            "## 8",
            "## 12",
        ]
    )
    assert out == expected
