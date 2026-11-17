"""Tests for the shell plugin (shell_on attribute)."""

import hashlib

import pytest

from tests.conftest import make_qp
from udan.attributes import plugins_operators_attribute
from udan.attributes.api_attribute_storage import AttributeStorageAPI
from udan.core.api_attributes import AttributeDescriptor
from udan.plugins_tools_core import plugins_system
from udan.plugins_tools_examples import plugins_builtins, plugins_fs, plugins_shell
from udan.plugins_tools_examples.plugins_shell import shell_on

atd = AttributeDescriptor.create


def _md5_of(path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def _make_files(tmp_path):
    (tmp_path / "a.txt").write_text("hello\n")
    (tmp_path / "b.txt").write_text("bye\n")


def _shell_on_values(ctx, args: dict):
    storage = ctx.container.get(AttributeStorageAPI)
    at_d = atd("shell_on", args)
    assert at_d in storage.attributes, f"shell_on not calculated for args={args}"
    return storage.attributes[at_d]


def test_shell_on_appends_item_when_no_dollar_item(tmp_path, monkeypatch):
    """Without $item in command, item is appended: `md5sum <item>`."""
    file = tmp_path / "a.txt"
    file.write_text("hello\n")
    monkeypatch.chdir(tmp_path)

    result = shell_on(item="a.txt", command="md5sum")

    assert result == f"{_md5_of(file)}  a.txt"


def test_shell_on_substitutes_dollar_item(tmp_path):
    """With $item in command, it is substituted with the item path."""
    file = tmp_path / "a.txt"
    file.write_text("hello\n")

    result = shell_on(item=file, command="md5sum $item")

    assert result == f"{_md5_of(file)}  {file}"


def test_shell_on_both_forms_equivalent(tmp_path, monkeypatch):
    """`md5sum` and `md5sum $item` produce the same command."""
    file = tmp_path / "a.txt"
    file.write_text("hello\n")
    monkeypatch.chdir(tmp_path)

    assert shell_on(item="a.txt", command="md5sum") == shell_on(item="a.txt", command="md5sum $item")


def test_shell_on_requires_command():
    with pytest.raises(ValueError, match="requires a command"):
        shell_on(item="a.txt")


def test_shell_on_query_append_form(make_ctx, tmp_path):
    """Query `shell_on md5sum` appends each item path to the command."""
    ctx = make_ctx(plugins_builtins, plugins_operators_attribute, plugins_system, plugins_fs, plugins_shell)
    qp = make_qp(ctx)
    _make_files(tmp_path)

    forest, _, _, _ = qp.execute_query(f"ls_files {tmp_path} '*.txt', shell_on md5sum")

    values = _shell_on_values(ctx, {"command": "md5sum"})
    assert len(values) == 2
    for file in (tmp_path / "a.txt", tmp_path / "b.txt"):
        assert values[file] == f"{_md5_of(file)}  {file}"
    assert set(forest.items) == {tmp_path / "a.txt", tmp_path / "b.txt"}


def test_shell_on_query_substitution_form(make_ctx, tmp_path):
    """Query `shell_on 'md5sum $item'` substitutes $item with each item path."""
    ctx = make_ctx(plugins_builtins, plugins_operators_attribute, plugins_system, plugins_fs, plugins_shell)
    qp = make_qp(ctx)
    _make_files(tmp_path)

    forest, _, _, _ = qp.execute_query(f"ls_files {tmp_path} '*.txt', shell_on 'md5sum $item'")

    values = _shell_on_values(ctx, {"command": "md5sum $item"})
    assert len(values) == 2
    for file in (tmp_path / "a.txt", tmp_path / "b.txt"):
        assert values[file] == f"{_md5_of(file)}  {file}"
    assert set(forest.items) == {tmp_path / "a.txt", tmp_path / "b.txt"}
