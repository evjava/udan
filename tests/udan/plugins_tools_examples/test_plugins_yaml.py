"""Tests for YAML query plugins."""

from udan.plugins_tools_examples.plugins_yaml import resolve_yaml_path, yaml_glob

# ── resolve_yaml_path tests ──


def test_resolve_root():
    """Path '.' returns the data wrapped in a list."""
    data = {"a": 1}
    assert resolve_yaml_path(data, ".") == [data]


def test_resolve_dict_key():
    """Path '.key' extracts a dict value."""
    assert resolve_yaml_path({"x": 42}, ".x") == [42]


def test_resolve_nested_keys():
    """Path '.a.b' navigates nested dicts."""
    data = {"a": {"b": 99}}
    assert resolve_yaml_path(data, ".a.b") == [99]


def test_resolve_missing_key():
    """Missing key returns empty list."""
    assert resolve_yaml_path({"x": 1}, ".y") == []


def test_resolve_list_iteration():
    """Path '[]' iterates over a list."""
    data = [1, 2, 3]
    assert resolve_yaml_path(data, "[]") == [1, 2, 3]


def test_resolve_dict_then_iterate():
    """Path '.items[]' extracts dict value then iterates."""
    data = {"items": [10, 20]}
    assert resolve_yaml_path(data, ".items[]") == [10, 20]


def test_resolve_iterate_then_key():
    """Path '.repos[].id' iterates list then extracts key from each."""
    data = {"repos": [{"id": "a"}, {"id": "b"}]}
    assert resolve_yaml_path(data, ".repos[].id") == ["a", "b"]


def test_resolve_deep_chain():
    """Path '.a[].b[].c' navigates multiple levels of lists and dicts."""
    data = {"a": [{"b": [{"c": 1}, {"c": 2}]}, {"b": [{"c": 3}]}]}
    assert resolve_yaml_path(data, ".a[].b[].c") == [1, 2, 3]


def test_resolve_iterate_non_list():
    """Iterating over a non-list produces empty."""
    data = {"x": "not a list"}
    assert resolve_yaml_path(data, ".x[]") == []


def test_resolve_empty_data():
    """Empty dict returns empty for any key."""
    assert resolve_yaml_path({}, ".foo") == []


def test_resolve_key_from_list():
    """Extracting a key from a list element (not a dict) is skipped."""
    data = [{"id": "a"}, "not_a_dict", {"id": "c"}]
    assert resolve_yaml_path(data, "[].id") == ["a", "c"]


# ── yaml_glob tests ──


TEST_YAML = "tests/resources/test_config.yaml"


def test_yaml_glob_returns_hooks():
    """yaml_glob with .repos[].hooks[] returns all hooks."""
    hooks = yaml_glob(TEST_YAML, ".repos[].hooks[]")
    ids = [h["id"] for h in hooks]
    assert "hook-a" in ids
    assert "hook-b" in ids
    assert "external-hook" in ids
    assert "hook-c" in ids


def test_yaml_glob_returns_hook_count():
    """yaml_glob returns correct number of hooks."""
    hooks = yaml_glob(TEST_YAML, ".repos[].hooks[]")
    assert len(hooks) == 4


def test_yaml_glob_hook_ids():
    """yaml_glob with .repos[].hooks[].id returns just the IDs."""
    ids = yaml_glob(TEST_YAML, ".repos[].hooks[].id")
    assert ids == ["hook-a", "hook-b", "external-hook", "hook-c"]


def test_yaml_glob_repo_urls():
    """yaml_glob with .repos[].repo returns repo URLs."""
    repos = yaml_glob(TEST_YAML, ".repos[].repo")
    assert "local" in repos
    assert "https://github.com/example/example" in repos


def test_yaml_glob_defaults():
    """yaml_glob with .defaults reads top-level non-repos keys."""
    defaults = yaml_glob(TEST_YAML, ".defaults")
    assert defaults == [{"fail_fast": True}]


def test_yaml_glob_root():
    """yaml_glob with default path '.' returns entire document."""
    root = yaml_glob(TEST_YAML)
    assert isinstance(root, list)
    assert len(root) == 1
    assert "repos" in root[0]


def test_yaml_glob_missing_file():
    """yaml_glob returns empty list for non-existent file."""
    assert yaml_glob("nonexistent.yaml", ".repos") == []


def test_yaml_glob_invalid_path():
    """yaml_glob returns empty list for path that doesn't match structure."""
    assert yaml_glob(TEST_YAML, ".nonexistent.key") == []


def test_yaml_glob_hook_entry():
    """yaml_glob can extract entry fields from hooks."""
    entries = yaml_glob(TEST_YAML, ".repos[].hooks[].entry")
    assert "python scripts/a.py" in entries
    assert "bash scripts/c.sh" in entries


def test_yaml_glob_hook_language():
    """yaml_glob can extract language fields from hooks."""
    languages = yaml_glob(TEST_YAML, ".repos[].hooks[].language")
    assert languages.count("system") == 3
    assert "python" in languages


def test_yaml_glob_filter_by_field():
    """Combine yaml_glob with dict filtering manually."""
    hooks = yaml_glob(TEST_YAML, ".repos[].hooks[]")
    system_hooks = [h for h in hooks if h.get("language") == "system"]
    assert len(system_hooks) == 3
    assert all(h["language"] == "system" for h in system_hooks)
