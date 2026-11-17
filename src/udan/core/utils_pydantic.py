"""Validators for udan configuration."""

import json
import os
from pathlib import Path
from typing import Annotated, Any

from pydantic import AfterValidator, BeforeValidator
from pydantic_settings import (
    BaseSettings,
    DotEnvSettingsSource,
    NoDecode,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)


def _expand_user_if_needed(path: str | Path) -> str:
    """Expand ~ in path if present.

    Args:
        path: Path string or Path object

    Returns:
        Expanded path as string

    Examples:
        >>> _expand_user_if_needed("~/test")
        '/home/user/test'
        >>> _expand_user_if_needed("/absolute/path")
        '/absolute/path'
    """
    return str(Path(path).expanduser())


# Type alias for path fields that expand ~
ExpandedPath = Annotated[str, AfterValidator(_expand_user_if_needed)]


def _parse_string_list(value: str | list[str]) -> list[str]:
    """Parse a list of strings given as comma-separated values or as a JSON list.

    Args:
        value: Raw field value: a comma-separated string, a JSON list string,
            or an already-parsed list

    Returns:
        Parsed list of strings

    Examples:
        >>> _parse_string_list("udan.plugins_tools_demo, udan.plugins_history")
        ['udan.plugins_tools_demo', 'udan.plugins_history']
        >>> _parse_string_list('["udan.plugins_tools_demo"]')
        ['udan.plugins_tools_demo']
        >>> _parse_string_list(["udan.plugins_tools_demo"])
        ['udan.plugins_tools_demo']
    """
    if not isinstance(value, str):
        return list(value)
    stripped = value.strip()
    if stripped.startswith("["):
        parsed = json.loads(stripped)
        return [str(item).strip() for item in parsed]
    return [item.strip() for item in stripped.split(",") if item.strip()]


# Type alias for list-of-strings fields whose env value is comma-separated
# (a JSON list string is still accepted). NoDecode turns off pydantic-settings'
# JSON decoding so the string reaches the validator as-is.
CommaSeparatedList = Annotated[list[str], NoDecode, BeforeValidator(_parse_string_list)]


class NamespacedDotenvSource(DotEnvSettingsSource):
    """Dotenv source that only claims keys of its own config's namespace.

    Keeps keys that are known field names plus unknown keys inside the
    config's env_prefix (so typos there still raise loudly); drops keys
    belonging to other configs sharing the same .env file.
    """

    def __init__(self, inner: DotEnvSettingsSource) -> None:
        """Build the source from an already-configured dotenv source.

        Args:
            inner: Dotenv source whose file, encoding and env options are reused.
        """
        super().__init__(
            inner.settings_cls,
            env_file=inner.env_file,
            env_file_encoding=inner.env_file_encoding,
            case_sensitive=inner.case_sensitive,
            env_prefix=inner.env_prefix,
            env_nested_delimiter=inner.env_nested_delimiter,
            env_ignore_empty=inner.env_ignore_empty,
            env_parse_none_str=inner.env_parse_none_str,
            env_parse_enums=inner.env_parse_enums,
        )

    def __call__(self) -> dict[str, Any]:
        data = super().__call__()
        fields = self.settings_cls.model_fields
        # Keys are lowercased together with the prefix when matching is case-insensitive
        prefix = self.env_prefix if self.case_sensitive else self.env_prefix.lower()
        return {key: value for key, value in data.items() if key in fields or key.startswith(prefix)}


class ConfigBaseSettings(BaseSettings):
    """Base class for udan configuration settings with ENV_FILE support.

    This class extends pydantic_settings.BaseSettings and provides a create()
    classmethod for loading configuration from a custom .env file.

    Environment Variables:
        ENV_FILE: Path to custom .env file (overrides default .env file location)

    Example:
        >>> class MyConfig(ConfigBaseSettings):
        ...     model_config = SettingsConfigDict(env_prefix="", env_file=".env", ...)
        ...     my_config_dir: ExpandedPath = Field(default="./.config")
        >>>
        >>> # Use default .env file
        >>> config = MyConfig()
        >>>
        >>> # Use custom .env file
        >>> config = MyConfig.create(env_file="/custom/path/.env")
    """

    model_config = SettingsConfigDict(
        env_prefix="",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Track the env_file used for loading (for debugging/inspection)
    env_file: ExpandedPath | None = None

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Use a dotenv source that only claims keys of this config's namespace.

        All udan configs (core and plugin) share one .env file. A config with
        extra="forbid" would otherwise crash on keys belonging to a different
        config, because DotEnvSettingsSource passes every unused key through.
        """
        if not isinstance(dotenv_settings, DotEnvSettingsSource):
            return (init_settings, env_settings, dotenv_settings, file_secret_settings)
        return (init_settings, env_settings, NamespacedDotenvSource(dotenv_settings), file_secret_settings)

    def __init__(self, **kwargs):
        """Initialize config, checking for ENV_FILE environment variable."""
        # Check for ENV_FILE environment variable if not explicitly provided
        env_file = os.getenv("ENV_FILE")
        if env_file and "_env_file" not in kwargs:
            kwargs["_env_file"] = env_file
        super().__init__(**kwargs)
        # Store the env_file that was used for loading
        if "_env_file" in kwargs:
            self.env_file = kwargs["_env_file"]  # type: ignore[assignment]

    @classmethod
    def create(cls, env_file: str | None = None) -> ConfigBaseSettings:
        """Create config instance with optional custom .env file.

        Args:
            env_file: Optional path to custom .env file. If None, checks ENV_FILE env var.

        Returns:
            Config instance loaded from specified .env file

        Examples:
            >>> # Use default .env file
            >>> config = MyConfig.create()
            >>>
            >>> # Use custom .env file
            >>> config = MyConfig.create(env_file="/custom/path/.env")
        """
        if env_file is None:
            # Check for ENV_FILE environment variable
            env_file = os.getenv("ENV_FILE")
        if env_file:
            instance = cls(_env_file=env_file)
            instance.env_file = env_file  # type: ignore[assignment]
            return instance
        return cls()
