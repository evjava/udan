"""Tests for the history plugin configuration (HistoryConfig).

Covers env mapping with the plugin's own prefix, the loud unknown-key error,
and storage selection driven by the configured path extension.
"""

import pytest

from udan.plugins_history.api_history import DummyHistoryLogger, DummySavedQueries
from udan.plugins_history.history_config import HistoryConfig
from udan.plugins_history.impl_history_jsonl import HistoryLogger
from udan.plugins_history.impl_saved_jsonl import SavedQueriesJsonl
from udan.plugins_history.plugins_history import create_history_storage, create_saved_storage


def test_history_config_defaults():
    """Test that the plugin config has sane defaults."""
    config = HistoryConfig()

    assert config.path.endswith("history.db")
    assert config.saved_path.endswith("saved.db")


def test_history_config_env_prefix_maps_history_path(monkeypatch):
    """Test that UDAN_HISTORY_PATH feeds path."""
    monkeypatch.setenv("UDAN_HISTORY_PATH", "/tmp/hs.jsonl")

    assert HistoryConfig().path == "/tmp/hs.jsonl"


def test_history_config_env_prefix_maps_saved_path(monkeypatch):
    """Test that UDAN_HISTORY_SAVED_PATH feeds saved_path."""
    monkeypatch.setenv("UDAN_HISTORY_SAVED_PATH", "/tmp/saved.jsonl")

    assert HistoryConfig().saved_path == "/tmp/saved.jsonl"


def test_history_config_shared_env_file_ignores_other_configs_keys(tmp_path, monkeypatch):
    """Test that a shared .env does not crash extra="forbid" on other configs' keys."""
    env_file = tmp_path / "shared.env"
    env_file.write_text(
        "UDAN_HISTORY_PATH=/tmp/from-env.jsonl\n"
        'UDAN_TOOLS_PREFERENCES_INPUT={"a": "b"}\n'
        "UDAN_HISTORY_SAVED_PATH=/tmp/saved-from-env.db\n"
    )
    # Drop the env vars so the values must come from the file
    monkeypatch.delenv("UDAN_HISTORY_PATH", raising=False)
    monkeypatch.delenv("UDAN_HISTORY_SAVED_PATH", raising=False)
    monkeypatch.setenv("ENV_FILE", str(env_file))

    config = HistoryConfig()

    assert config.path == "/tmp/from-env.jsonl"
    assert config.saved_path == "/tmp/saved-from-env.db"


def test_history_config_shared_env_file_typo_is_loud(tmp_path, monkeypatch):
    """Test that a typo inside the plugin's own env namespace raises."""
    env_file = tmp_path / "typo.env"
    env_file.write_text("UDAN_HISTORY_PAT=/tmp/typo.jsonl\n")
    monkeypatch.setenv("ENV_FILE", str(env_file))

    with pytest.raises(ValueError, match="udan_history_pat"):
        HistoryConfig()


def test_history_config_init_kwarg_wins_over_env(monkeypatch):
    """Test that init kwargs beat the env var (pydantic precedence)."""
    monkeypatch.setenv("UDAN_HISTORY_SAVED_PATH", "/tmp/from-env.db")

    config = HistoryConfig(saved_path="/tmp/explicit.db")

    assert config.saved_path == "/tmp/explicit.db"


def test_history_config_unknown_key_raises():
    """Test that a typo in the plugin config is loud, not silently ignored."""
    with pytest.raises(ValueError, match="Extra inputs are not permitted"):
        HistoryConfig(histrory_path="/tmp/x.db")


def test_storage_selection_by_extension():
    """Test that factories pick the implementation from the path extension."""
    assert isinstance(create_history_storage("/tmp/h.jsonl"), HistoryLogger)
    assert isinstance(create_history_storage("/tmp/h.txt"), DummyHistoryLogger)
    assert isinstance(create_history_storage(None), DummyHistoryLogger)
    assert isinstance(create_saved_storage("/tmp/s.jsonl"), SavedQueriesJsonl)
    assert isinstance(create_saved_storage("/tmp/s.txt"), DummySavedQueries)
    assert isinstance(create_saved_storage(None), DummySavedQueries)
