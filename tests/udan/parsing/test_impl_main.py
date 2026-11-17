"""Tests for main.py CLI argument parsing."""

import pytest

from udan.parsing.main import _parse_args, main


def parse(argv: list[str]) -> dict:
    """Helper: parse args and return as dict."""
    ns = _parse_args(argv)
    return {"query": ns.query, "comment": ns.comment, "debug": ns.debug}


def test_parse() -> None:
    """Test _parse_args() with various inputs."""
    assert parse(["menu"]) == {"query": "menu", "comment": "", "debug": False}
    assert parse(["some query"]) == {"query": "some query", "comment": "", "debug": False}
    assert parse(['"bad-modules.txt", extend_file_lines']) == {
        "query": '"bad-modules.txt", extend_file_lines',
        "comment": "",
        "debug": False,
    }
    assert parse(['some "literal"']) == {"query": 'some "literal"', "comment": "", "debug": False}
    assert parse(["some 'literal'"]) == {"query": "some 'literal'", "comment": "", "debug": False}
    assert parse(["--query=some"]) == {"query": "some", "comment": "", "debug": False}
    assert parse(["--query=some query"]) == {"query": "some query", "comment": "", "debug": False}
    assert parse(['--query="bad-modules.txt", extend_file_lines']) == {
        "query": '"bad-modules.txt", extend_file_lines',
        "comment": "",
        "debug": False,
    }
    assert parse(["some-query", "--comment=testing"]) == {"query": "some-query", "comment": "testing", "debug": False}
    assert parse(["some-query", "--debug"]) == {"query": "some-query", "comment": "", "debug": True}
    assert parse(["some-query", "--comment=testing", "--debug"]) == {
        "query": "some-query",
        "comment": "testing",
        "debug": True,
    }
    assert parse(['"bad-modules.txt", e', "--comment=test", "--debug"]) == {
        "query": '"bad-modules.txt", e',
        "comment": "test",
        "debug": True,
    }
    assert parse(["--query", "some value"]) == {"query": "some value", "comment": "", "debug": False}
    assert parse(["--query", "some value", "--debug"]) == {"query": "some value", "comment": "", "debug": True}


def test_parse_errors() -> None:
    """Test _parse_args() error cases."""
    with pytest.raises(SystemExit):
        parse([])

    with pytest.raises(SystemExit):
        parse(["some-query", "--invalid"])


def test_main_success_returns_output() -> None:
    """Test main() returns the rendered output of a successful query."""
    assert main("demo.menu, limit 2") == "- day-1\n- day-2"


def test_main_failure_exits_non_zero_on_stderr(capsys) -> None:
    """Test main() reports a failed query on stderr and exits 1, not as an empty result."""
    with pytest.raises(SystemExit) as exc:
        main("bogus_step_name, grep udan.")

    assert exc.value.code == 1
    captured = capsys.readouterr()
    assert "Bare literal 'bogus_step_name' is not allowed." in captured.err
    assert captured.out == ""


def test_main_parse_failure_prints_advice_without_traceback(capsys) -> None:
    """Test a failed parse reads as lark's detail without debug - no traceback noise."""
    with pytest.raises(SystemExit) as exc:
        main('fruits "apple')

    assert exc.value.code == 1
    captured = capsys.readouterr()
    assert captured.err.startswith(
        "Query parse error: No terminal matches '\"' in the current parser context, at line 1 col 8"
    )
    assert "Expected one of:" in captured.err
    assert "Traceback" not in captured.err
    assert captured.out == ""


def test_main_parse_failure_prints_traceback_with_debug(capsys) -> None:
    """Test a failed parse shows the raw lark error as is with debug on."""
    with pytest.raises(SystemExit):
        main('fruits "apple', debug=True)

    captured = capsys.readouterr()
    assert "lark.exceptions.UnexpectedCharacters" in captured.err
    assert captured.out == ""
