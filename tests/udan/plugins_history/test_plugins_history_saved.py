"""Tests for the saved queries plugin parts of udan.plugins_history.

Covers the saved and saved-tags inserters and the saved-item render, the
saved_saved/saved_tags attributes, the history_saved attributes, and the
render checkbox.
"""

import json
from pathlib import Path

import pytest

import udan.plugins_history.plugins_history
from tests.conftest import make_qp, register_tools_from_module
from udan.plugins_history import plugins_history
from udan.plugins_history.api_history import SavedQueriesAPI
from udan.plugins_history.plugins_history import (
    history_saved,
    history_saved_tags,
    render_history,
    render_saved,
    saved,
    saved_saved,
    saved_tags,
    saved_tags_list,
)


class StubSavedStorage(SavedQueriesAPI):
    """In-memory saved queries storage for tests."""

    def __init__(self, entries: list[dict] | None = None) -> None:
        self.entries: list[dict] = entries if entries is not None else []

    def list_saved(self) -> list[dict]:
        return list(self.entries)

    def add(self, pattern: str, query: str, history_id: int | None = None, tags: list[str] | None = None) -> None:
        self.entries.append(
            {
                "pattern": pattern,
                "query": query,
                "tags": list(tags) if tags else [],
                "create_date": "2026-01-01T00:00:00",
                "history_id": history_id,
            }
        )

    def delete(self, pattern: str) -> int:
        before = len(self.entries)
        self.entries = [e for e in self.entries if e["pattern"] != pattern]
        return before - len(self.entries)

    def get_by_history_id(self, history_id: int) -> dict | None:
        return next((e for e in self.entries if e.get("history_id") == history_id), None)

    def update_tags(self, history_id: int, tags: list[str]) -> int:
        updated = 0
        for entry in self.entries:
            if entry.get("history_id") == history_id:
                entry["tags"] = list(tags)
                updated += 1
        return updated

    def update_tags_by_pattern(self, pattern: str, tags: list[str]) -> int:
        updated = 0
        for entry in self.entries:
            if entry.get("pattern") == pattern:
                entry["tags"] = list(tags)
                updated += 1
        return updated

    def delete_by_history_id(self, history_id: int) -> int:
        before = len(self.entries)
        self.entries = [e for e in self.entries if e.get("history_id") != history_id]
        return before - len(self.entries)


def _entry(history_id: int | None = 42, command: str = "vars") -> dict:
    entry: dict = {
        "timestamp": "2026-01-09T20:00:00",
        "command": command,
        "success": True,
        "total_items": 5,
    }
    if history_id is not None:
        entry["history_id"] = history_id
    return entry


def _record(
    pattern: str = "my-sort",
    query: str = "range 100, sort",
    tags: list[str] | None = None,
    history_id: int | None = None,
) -> dict:
    return {
        "pattern": pattern,
        "query": query,
        "tags": list(tags) if tags else [],
        "create_date": "2026-01-09T20:00:00",
        "history_id": history_id,
    }


# --- saved inserter ---


def _write_saved(
    path: Path,
    pattern: str,
    query: str,
    tags: list[str] | None = None,
    create_date: str = "2026-01-09T20:00:00",
) -> None:
    """Helper: append one entry to saved.jsonl."""
    path.parent.mkdir(parents=True, exist_ok=True)

    entry: dict = {"pattern": pattern, "query": query, "create_date": create_date}
    if tags:
        entry["tags"] = " ".join(tags)
    with open(path, "a") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


@pytest.fixture
def saved_jsonl_path(tmp_path: Path) -> Path:
    return tmp_path / "saved.jsonl"


@pytest.fixture
def saved_env(saved_jsonl_path: Path, monkeypatch):
    """Point saved queries path to the test jsonl BEFORE the container is created."""
    monkeypatch.setenv("UDAN_HISTORY_SAVED_PATH", str(saved_jsonl_path))
    return saved_jsonl_path


@pytest.fixture
def ctx_with_saved(saved_env, make_ctx):
    ctx = make_ctx(plugins_history)
    register_tools_from_module(ctx, udan.plugins_history.plugins_history.__name__)
    return ctx


def test_empty_saved(ctx_with_saved):
    qp_with_saved = make_qp(ctx_with_saved)
    _, _, _, out = qp_with_saved.execute_query("saved")
    assert out == ""


def test_list_saved_queries(ctx_with_saved, saved_jsonl_path: Path):
    qp_with_saved = make_qp(ctx_with_saved)
    _write_saved(saved_jsonl_path, "my-sort", "range 100, sort")
    _write_saved(saved_jsonl_path, "my-limit", "range 50, limit 5")

    _, _, _, out = qp_with_saved.execute_query("saved")
    expected = "\n".join(
        [
            "- [X] 2026-01-09 20:00:00 [] :: range 100, sort",
            "- [X] 2026-01-09 20:00:00 [] :: range 50, limit 5",
        ]
    )
    assert out == expected


def test_filter_by_tag(ctx_with_saved, saved_jsonl_path: Path):
    qp_with_saved = make_qp(ctx_with_saved)
    _write_saved(saved_jsonl_path, "my-sort", "range 100, sort", tags=["demo"])
    _write_saved(saved_jsonl_path, "my-limit", "range 50, limit 5")

    _, _, _, out = qp_with_saved.execute_query("saved demo")
    assert out == "- [X] 2026-01-09 20:00:00 [demo] :: range 100, sort"


def test_filter_by_two_tags_ands(ctx_with_saved, saved_jsonl_path: Path):
    qp_with_saved = make_qp(ctx_with_saved)
    _write_saved(saved_jsonl_path, "my-sort", "range 100, sort", tags=["demo", "ux"])
    _write_saved(saved_jsonl_path, "my-limit", "range 50, limit 5", tags=["demo"])

    _, _, _, out = qp_with_saved.execute_query("saved demo ux")
    assert out == "- [X] 2026-01-09 20:00:00 [demo, ux] :: range 100, sort"


def test_filter_excludes_tag_with_dash(ctx_with_saved, saved_jsonl_path: Path):
    qp_with_saved = make_qp(ctx_with_saved)
    _write_saved(saved_jsonl_path, "my-sort", "range 100, sort", tags=["demo"])
    _write_saved(saved_jsonl_path, "my-limit", "range 50, limit 5")

    _, _, _, out = qp_with_saved.execute_query("saved -demo")
    assert out == "- [X] 2026-01-09 20:00:00 [] :: range 50, limit 5"


def test_filter_tag_match_is_exact(ctx_with_saved, saved_jsonl_path: Path):
    qp_with_saved = make_qp(ctx_with_saved)
    _write_saved(saved_jsonl_path, "my-sort", "range 100, sort", tags=["demo-run"])

    _, _, _, out = qp_with_saved.execute_query("saved demo")
    assert out == ""


def test_filter_unknown_tag_yields_empty(ctx_with_saved, saved_jsonl_path: Path):
    qp_with_saved = make_qp(ctx_with_saved)
    _write_saved(saved_jsonl_path, "my-sort", "range 100, sort")

    _, _, _, out = qp_with_saved.execute_query("saved nosuchtag")
    assert out == ""


def test_filter_by_query_text(ctx_with_saved, saved_jsonl_path: Path):
    qp_with_saved = make_qp(ctx_with_saved)
    _write_saved(saved_jsonl_path, "my-sort", "range 100, sort")
    _write_saved(saved_jsonl_path, "my-limit", "range 50, limit 5")

    _, _, _, out = qp_with_saved.execute_query("saved sort")
    assert out == "- [X] 2026-01-09 20:00:00 [] :: range 100, sort"


def test_filter_by_pattern_name_text(ctx_with_saved, saved_jsonl_path: Path):
    qp_with_saved = make_qp(ctx_with_saved)
    _write_saved(saved_jsonl_path, "my-sort", "range 100, sort")
    _write_saved(saved_jsonl_path, "my-limit", "range 50, limit 5")

    _, _, _, out = qp_with_saved.execute_query("saved limit")
    assert out == "- [X] 2026-01-09 20:00:00 [] :: range 50, limit 5"


def test_filter_token_matches_tag_or_text(ctx_with_saved, saved_jsonl_path: Path):
    qp_with_saved = make_qp(ctx_with_saved)
    _write_saved(saved_jsonl_path, "my-sort", "range 100, sort", tags=["demo"])
    _write_saved(saved_jsonl_path, "my-demo", "range 50, limit 5")

    _, _, _, out = qp_with_saved.execute_query("saved demo")
    expected = "\n".join(
        [
            "- [X] 2026-01-09 20:00:00 [demo] :: range 100, sort",
            "- [X] 2026-01-09 20:00:00 [] :: range 50, limit 5",
        ]
    )
    assert out == expected


def test_filter_excludes_text_with_dash(ctx_with_saved, saved_jsonl_path: Path):
    qp_with_saved = make_qp(ctx_with_saved)
    _write_saved(saved_jsonl_path, "my-sort", "range 100, sort")
    _write_saved(saved_jsonl_path, "my-limit", "range 50, limit 5")

    _, _, _, out = qp_with_saved.execute_query("saved range -limit")
    assert out == "- [X] 2026-01-09 20:00:00 [] :: range 100, sort"


def test_list_saved_with_tags(ctx_with_saved, saved_jsonl_path: Path):
    qp_with_saved = make_qp(ctx_with_saved)
    _write_saved(saved_jsonl_path, "my-sort", "range 100, sort", tags=["demo"])
    _write_saved(saved_jsonl_path, "my-limit", "range 50, limit 5")

    _, _, _, out = qp_with_saved.execute_query("saved")
    expected = "\n".join(
        [
            "- [X] 2026-01-09 20:00:00 [demo] :: range 100, sort",
            "- [X] 2026-01-09 20:00:00 [] :: range 50, limit 5",
        ]
    )
    assert out == expected


def test_saved_inserter_direct_with_storage():
    entries = [
        {
            "pattern": "my-sort",
            "query": "range 100, sort",
            "tags": ["demo"],
            "create_date": "2026-10-19T22:48:10.123456+00:00",
            "history_id": None,
        },
        {"pattern": "plain", "query": "vars", "tags": [], "create_date": "2026-01-09T20:00:00", "history_id": None},
    ]
    assert list(saved(saved_storage=StubSavedStorage(entries))) == entries


def test_saved_inserter_direct_filters_by_tokens():
    tagged = {
        "pattern": "my-sort",
        "query": "range 100, sort",
        "tags": ["demo", "ux"],
        "create_date": "2026-10-19T22:48:10.123456+00:00",
        "history_id": None,
    }
    demo_only = {
        "pattern": "my-limit",
        "query": "range 50, limit 5",
        "tags": ["demo"],
        "create_date": "2026-01-09T20:00:00",
        "history_id": None,
    }
    other = {"pattern": "plain", "query": "vars", "tags": [], "create_date": "2026-01-09T20:00:00", "history_id": None}
    storage = StubSavedStorage([tagged, demo_only, other])

    assert list(saved(patterns=["demo"], saved_storage=storage)) == [tagged, demo_only]
    assert list(saved(patterns=["demo", "-ux"], saved_storage=storage)) == [demo_only]
    assert list(saved(patterns=["limit"], saved_storage=storage)) == [demo_only]
    assert list(saved(patterns=["plain"], saved_storage=storage)) == [other]
    assert list(saved(patterns=["sort", "-demo"], saved_storage=storage)) == []
    assert list(saved(saved_storage=storage)) == [tagged, demo_only, other]


# --- saved-tags inserter ---


def test_saved_tags_lists_distinct_sorted_tags(ctx_with_saved, saved_jsonl_path: Path):
    qp_with_saved = make_qp(ctx_with_saved)
    _write_saved(saved_jsonl_path, "my-sort", "range 100, sort", tags=["ux", "demo"])
    _write_saved(saved_jsonl_path, "my-limit", "range 50, limit 5", tags=["demo"])
    _write_saved(saved_jsonl_path, "my-vars", "vars")

    _, _, _, out = qp_with_saved.execute_query("saved-tags")
    assert out == "\n".join(["- demo", "- ux"])


def test_saved_tags_empty_without_records(ctx_with_saved):
    qp_with_saved = make_qp(ctx_with_saved)
    _, _, _, out = qp_with_saved.execute_query("saved-tags")
    assert out == ""


def test_saved_tags_empty_with_only_untagged_records(ctx_with_saved, saved_jsonl_path: Path):
    qp_with_saved = make_qp(ctx_with_saved)
    _write_saved(saved_jsonl_path, "my-sort", "range 100, sort")

    _, _, _, out = qp_with_saved.execute_query("saved-tags")
    assert out == ""


def test_saved_tags_inserter_direct():
    storage = StubSavedStorage(
        [
            _record(pattern="my-sort", tags=["ux", "demo"]),
            _record(pattern="my-limit", tags=["demo"]),
            _record(pattern="my-vars"),
        ]
    )
    assert list(saved_tags_list(saved_storage=storage)) == ["demo", "ux"]
    assert list(saved_tags_list(saved_storage=StubSavedStorage())) == []


# --- render_saved ---


def test_render_saved_with_tags() -> None:
    assert render_saved(_record(tags=["demo", "ux"])) == "- [X] 2026-01-09 20:00:00 [demo, ux] :: range 100, sort"


def test_render_saved_without_tags() -> None:
    assert render_saved(_record()) == "- [X] 2026-01-09 20:00:00 [] :: range 100, sort"


def test_render_saved_tuple_format() -> None:
    assert render_saved((2, _record(tags=["demo"]))) == "- [X] 2026-01-09 20:00:00 [demo] :: range 100, sort"


def test_render_saved_with_indent() -> None:
    assert render_saved(_record(), indent="    ") == "    - [X] 2026-01-09 20:00:00 [] :: range 100, sort"


def test_render_saved_non_dict_item() -> None:
    assert render_saved("not a dict") == "- not a dict"


# --- saved_saved attribute ---


def test_saved_saved_true_for_saved_record() -> None:
    assert saved_saved(_record()) is True


def test_saved_saved_false_for_non_dict_item() -> None:
    assert saved_saved("not a dict") is False


def test_saved_saved_false_for_nested_non_dict_item() -> None:
    assert saved_saved((2, "not a dict")) is False


# --- saved_tags attribute ---


def test_saved_tags_returns_record_tags() -> None:
    assert saved_tags(_record(tags=["demo", "ux"])) == ["demo", "ux"]


def test_saved_tags_empty_for_untagged_record() -> None:
    assert saved_tags(_record()) == []


def test_saved_tags_empty_for_non_dict_item() -> None:
    assert saved_tags("not a dict") == []


# --- history_saved attribute ---


def test_history_saved_true_when_linked_saved_exists() -> None:
    storage = StubSavedStorage()
    storage.add("vars", "vars", history_id=42)

    assert history_saved(_entry(), saved_storage=storage) is True


def test_history_saved_false_when_no_linked_saved() -> None:
    storage = StubSavedStorage()

    assert history_saved(_entry(), saved_storage=storage) is False


def test_history_saved_false_without_history_id() -> None:
    storage = StubSavedStorage()
    storage.add("vars", "vars", history_id=42)

    assert history_saved(_entry(history_id=None), saved_storage=storage) is False


def test_history_saved_false_without_storage() -> None:
    assert history_saved(_entry(), saved_storage=None) is False


def test_history_saved_false_for_non_dict_item() -> None:
    storage = StubSavedStorage()

    assert history_saved("not a dict", saved_storage=storage) is False


# --- history_saved_tags attribute ---


def test_history_saved_tags_returns_linked_tags() -> None:
    storage = StubSavedStorage()
    storage.add("vars", "vars", history_id=42, tags=["alice"])

    assert history_saved_tags(_entry(), saved_storage=storage) == ["alice"]


def test_history_saved_tags_empty_when_not_saved() -> None:
    storage = StubSavedStorage()

    assert history_saved_tags(_entry(), saved_storage=storage) == []


def test_history_saved_tags_empty_without_history_id() -> None:
    storage = StubSavedStorage()
    storage.add("vars", "vars", history_id=42)

    assert history_saved_tags(_entry(history_id=None), saved_storage=storage) == []


def test_history_saved_tags_empty_without_storage() -> None:
    assert history_saved_tags(_entry(), saved_storage=None) == []


# --- render_history checkbox and history id ---


def test_render_history_shows_history_id_and_unchecked_box() -> None:
    result = render_history(_entry())

    assert result == "- [ ] [] #42 2026-01-09 20:00:00 🟢 (5 items) :: vars"


def test_render_history_no_id_part_without_history_id() -> None:
    result = render_history(_entry(history_id=None))

    assert result == "- [ ] [] 2026-01-09 20:00:00 🟢 (5 items) :: vars"


def test_render_history_checked_box_when_saved() -> None:
    storage = StubSavedStorage()
    storage.add("vars", "vars", history_id=42)

    result = render_history(_entry(), saved_storage=storage)

    assert result == "- [X] [] #42 2026-01-09 20:00:00 🟢 (5 items) :: vars"


def test_render_history_unchecked_box_when_not_saved() -> None:
    storage = StubSavedStorage()

    result = render_history(_entry(), saved_storage=storage)

    assert result == "- [ ] [] #42 2026-01-09 20:00:00 🟢 (5 items) :: vars"


def test_render_history_shows_tag_group_when_saved_with_tags() -> None:
    storage = StubSavedStorage()
    storage.add("vars", "vars", history_id=42, tags=["alice", "bob"])

    result = render_history(_entry(), saved_storage=storage)

    assert result == "- [X] [alice, bob] #42 2026-01-09 20:00:00 🟢 (5 items) :: vars"


def test_render_history_shows_empty_tag_group_when_saved_without_tags() -> None:
    storage = StubSavedStorage()
    storage.add("vars", "vars", history_id=42)

    result = render_history(_entry(), saved_storage=storage)

    assert result == "- [X] [] #42 2026-01-09 20:00:00 🟢 (5 items) :: vars"
