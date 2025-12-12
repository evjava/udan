"""Tests for main module."""

import pytest
from pathlib import Path

from data_navigator.main import main


@pytest.fixture
def tmp_dir(tmp_path):
    """Fixture providing a temporary directory path."""
    return str(tmp_path)


def test_main_with_directory(tmp_dir):
    """Test main() with a valid directory containing files."""
    # Create some test files
    test_files = ["file1.txt", "file2.py", "file3.json"]
    for filename in test_files:
        (Path(tmp_dir) / filename).touch()
    
    result = main(tmp_dir)
    
    # Result should be sorted file names, one per line
    lines = result.split("\n")
    assert len(lines) == 3
    assert "file1.txt" in lines
    assert "file2.py" in lines
    assert "file3.json" in lines
    # Check that it's sorted
    assert lines == sorted(test_files)


def test_main_with_empty_directory(tmp_dir):
    """Test main() with an empty directory."""
    result = main(tmp_dir)
    assert result == ""


def test_main_with_nonexistent_path():
    """Test main() with a non-existent path."""
    result = main("/nonexistent/path/that/does/not/exist")
    assert "Error:" in result
    assert "not a directory" in result or "does not exist" in result


def test_main_with_file_not_directory(tmp_path):
    """Test main() with a file path instead of directory."""
    tmpfile_path = tmp_path / "test_file.txt"
    tmpfile_path.touch()
    
    result = main(str(tmpfile_path))
    assert "Error:" in result
    assert "not a directory" in result

