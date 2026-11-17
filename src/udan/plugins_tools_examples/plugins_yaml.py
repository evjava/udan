"""Udan plugin for querying YAML files with path patterns.

Provides a generic inserter that reads a YAML file and returns items
matching a jq-like path pattern. No external dependencies beyond PyYAML.

Pattern syntax (inspired by jq/yq):
    .key        -> dict lookup by key
    []          -> iterate over list
    .key[]      -> dict lookup, then iterate
    .a.b.c      -> nested dict lookup

Examples:
    yaml_glob ".pre-commit-config.yaml" path=".repos[].hooks[]"
    yaml_glob ".pre-commit-config.yaml" path=".repos[].hooks[].id"
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from udan.core_tools_loading.api_annotated import annotated
from udan.core_tools_loading.api_types import JsonValue

DOMAIN = "yaml"


def resolve_yaml_path(data: JsonValue, path: str) -> list[JsonValue]:
    """Resolve a jq-like path against parsed YAML data.

    Tokenizes the path into .key and [] segments, then walks the data.

    Args:
        data: Parsed YAML data (dict, list, or scalar)
        path: Path pattern, e.g. ".repos[].hooks[].id"

    Returns:
        List of matched items
    """
    tokens = re.findall(r"\.(\w+)|(\[\])", path)
    results: list[JsonValue] = [data]
    for dot_key, bracket in tokens:
        if bracket:
            results = [item for r in results if isinstance(r, list) for item in r]
        elif dot_key:
            results = [r[dot_key] for r in results if isinstance(r, dict) and dot_key in r]
    return results


@annotated(
    meta={
        "tool_type": "inserter",
        "output_type": "dict",
        "supported_renders": ["table", "list"],
    }
)
def yaml_glob(file: str, path: str = ".") -> list[JsonValue]:
    """Read a YAML file and return items matching a path pattern.

    Uses a jq-like path syntax to navigate nested dicts and lists.

    Args:
        file: Path to the YAML file
        path: jq-like path pattern (e.g. ".repos[].hooks[]").
              Default "." returns the entire document.

    Returns:
        List of matched items (dicts, strings, numbers, etc.)

    Examples:
        yaml_glob ".pre-commit-config.yaml" path=".repos[].hooks[]"
        yaml_glob ".pre-commit-config.yaml" path=".repos[].hooks[].id"
        yaml_glob ".pre-commit-config.yaml" path=".repos[].repo"
    """
    file_path = Path(file).expanduser()
    if not file_path.is_file():
        return []

    try:
        with open(file_path) as f:
            data = yaml.safe_load(f)
    except OSError, yaml.YAMLError:
        return []

    if data is None:
        return []

    return resolve_yaml_path(data, path)
