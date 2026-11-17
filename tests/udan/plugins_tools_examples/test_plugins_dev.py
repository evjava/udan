"""Tests for plugins_dev (ssearch operator)."""

from pathlib import Path

from udan.plugins_tools_examples.api_types import ASTChunk
from udan.plugins_tools_examples.plugins_dev import ssearch


def _write_test_file(tmp_path: Path, filename: str, code: str) -> Path:
    f = tmp_path / filename
    f.write_text(code)
    return f


def test_ssearch_python_def_shorthand(tmp_path):
    """Test ssearch finds functions by shorthand pattern."""
    _write_test_file(
        tmp_path,
        "example.py",
        "class Foo:\n    def __init__(self):\n        self.x = 1\n\n    def bar(self):\n        pass\n",
    )

    results = list(ssearch(str(tmp_path / "*.py"), "def __init__"))
    assert len(results) == 1
    chunk = results[0]
    assert isinstance(chunk, ASTChunk)
    assert chunk.name == "__init__"
    assert chunk.source_file == str(tmp_path / "example.py")
    assert chunk.line_start_number == 2
    assert "self.x = 1" in chunk.full_code


def test_ssearch_python_class_shorthand(tmp_path):
    """Test ssearch finds classes by shorthand pattern."""
    _write_test_file(tmp_path, "cls.py", "class MyClass:\n    pass\n\ndef func():\n    pass\n")

    results = list(ssearch(str(tmp_path / "*.py"), "class MyClass"))
    assert len(results) == 1
    assert results[0].name == "MyClass"
    assert results[0].type == "class_definition"


def test_ssearch_python_raw_query(tmp_path):
    """Test ssearch with raw S-expression query."""
    _write_test_file(tmp_path, "raw.py", "def foo():\n    pass\n\ndef bar():\n    pass\n")

    results = list(ssearch(str(tmp_path / "*.py"), "(function_definition) @fn"))
    assert len(results) == 2
    names = {r.name for r in results}
    assert names == {"foo", "bar"}


def test_ssearch_toml_shorthand(tmp_path):
    """Test ssearch finds TOML key-value pairs."""
    _write_test_file(tmp_path, "conf.toml", 'name = "udan"\nversion = "1.0"\n')

    results = list(ssearch(str(tmp_path / "*.toml"), "name"))
    assert len(results) == 1
    assert 'name = "udan"' in results[0].full_code


def test_ssearch_lang_auto_detect(tmp_path):
    """Test ssearch auto-detects language from file extension."""
    _write_test_file(tmp_path, "detect.py", "def hello():\n    pass\n")

    results = list(ssearch(str(tmp_path / "*.py"), "def hello"))
    assert len(results) == 1
    assert results[0].name == "hello"


def test_ssearch_lang_override(tmp_path):
    """Test ssearch with explicit lang override."""
    _write_test_file(tmp_path, "detect.py", "def hello():\n    pass\n")

    results = list(ssearch(str(tmp_path / "*.py"), "def hello", lang="python"))
    assert len(results) == 1


def test_ssearch_no_matches(tmp_path):
    """Test ssearch returns empty when no matches."""
    _write_test_file(tmp_path, "nomatch.py", "x = 1\ny = 2\n")

    results = list(ssearch(str(tmp_path / "*.py"), "def nonexistent"))
    assert results == []


def test_ssearch_multiple_files(tmp_path):
    """Test ssearch across multiple files."""
    _write_test_file(tmp_path, "a.py", "def alpha():\n    pass\n")
    _write_test_file(tmp_path, "b.py", "def beta():\n    pass\n")

    results = list(ssearch(str(tmp_path / "*.py"), "(function_definition) @fn"))
    assert len(results) == 2
    names = {r.name for r in results}
    assert names == {"alpha", "beta"}


def test_ssearch_line_numbers(tmp_path):
    """Test ssearch returns correct line_start_number and line_end_number."""
    _write_test_file(
        tmp_path,
        "lines.py",
        "x = 1\n\ndef foo():\n    a = 1\n    b = 2\n    return a + b\n\ny = 3\n",
    )

    results = list(ssearch(str(tmp_path / "*.py"), "def foo"))
    assert len(results) == 1
    chunk = results[0]
    assert chunk.line_start_number == 3
    assert chunk.line_end_number == 6
    assert chunk.line_start_number <= chunk.line_end_number


def test_ssearch_import_shorthand(tmp_path):
    """Test ssearch finds import statements."""
    _write_test_file(tmp_path, "imports.py", "import os\nimport sys\n\nx = 1\n")

    results = list(ssearch(str(tmp_path / "*.py"), "import os"))
    assert len(results) == 2
    codes = {r.full_code for r in results}
    assert "import os" in codes
    assert "import sys" in codes


def test_ssearch_decorator_shorthand(tmp_path):
    """Test ssearch finds decorators."""
    _write_test_file(
        tmp_path,
        "deco.py",
        "@property\ndef value(self):\n    return self._value\n",
    )

    results = list(ssearch(str(tmp_path / "*.py"), "@property"))
    assert len(results) == 1
    assert results[0].name == "property"
