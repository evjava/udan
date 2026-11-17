from __future__ import annotations

import re
import subprocess
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast, get_args

from tree_sitter import Query, QueryCursor
from tree_sitter_language_pack import SupportedLanguage, get_language, get_parser

from udan.core_tools_loading.api_annotated import annotated
from udan.plugins_tools_examples.api_types import ASTChunk

DOMAIN = "dev"

_EXT_TO_LANG: dict[str, str] = {
    ".py": "python",
    ".json": "json",
    ".dockerfile": "dockerfile",
    ".toml": "toml",
}

_DOCKERFILE_NAMES = {"Dockerfile", "Dockerfile.dev", "Dockerfile.prod", "Dockerfile.base"}

_TWO_KEYS = 2


def _detect_lang(filepath: str, lang: str | None) -> str | None:
    if lang:
        return lang
    path = Path(filepath)
    if path.name in _DOCKERFILE_NAMES or path.name.startswith("Dockerfile."):
        return "dockerfile"
    return _EXT_TO_LANG.get(path.suffix.lower())


def _shorthand_to_query(lang: str, pattern: str) -> tuple[str, str | None]:
    """Convert shorthand pattern to (query_str, filter_name or None).

    Returns a tuple of (tree-sitter query, optional name to filter captures by).
    If filter_name is set, only return parent nodes whose first identifier child matches.
    """
    if pattern.startswith("("):
        return pattern, None

    if lang == "python":
        if pattern.startswith("def "):
            name = pattern[4:].strip()
            return "(function_definition name: (identifier) @fn.name) @fn.def", name
        if pattern.startswith("class "):
            name = pattern[6:].strip()
            return "(class_definition name: (identifier) @cls.name) @cls.def", name
        if pattern.startswith("@"):
            return "(decorator (identifier) @dec.name) @dec", pattern[1:]
        if pattern.startswith("import "):
            return "(import_statement) @import", None

    if lang == "json":
        return "(pair key: (string (string_content) @key)) @pair", pattern

    if lang == "dockerfile":
        return f"({pattern.lower()}_instruction) @instr", None

    if lang == "toml":
        return "(pair (bare_key) @key) @pair", pattern

    return pattern, None


def _node_text(node, source: bytes) -> str:
    return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def _extract_name(node, source: bytes) -> str:
    for child in node.children:
        if child.type == "identifier":
            return _node_text(child, source)
    return node.type


def _extract_docstring(node, source: bytes) -> str:
    for child in node.children:
        if child.type == "block":
            for stmt in child.children:
                if stmt.type == "expression_statement":
                    for expr in stmt.children:
                        if expr.type == "string":
                            text = _node_text(expr, source)
                            return text.strip("\"'").strip()
            break
    return ""


def _find_main_and_name_keys(captures: dict, filter_name: str | None) -> tuple[str | None, str | None]:
    """Identify the main capture key (parent) and name capture key (child to filter by).

    Strategy: prefer dotted keys (e.g. fn.def / fn.name), then fall back to multi-key
    heuristic: the key with more nodes is "main", the other is "name".
    """
    keys = list(captures.keys())
    if not keys:
        return None, None
    if len(keys) == 1:
        return keys[0], None

    # Try dotted convention: fn.def + fn.name
    main_key = None
    name_key = None
    for key in keys:
        if "." in key and key.endswith(".name"):
            name_key = key
        elif "." in key:
            main_key = key
    if main_key and name_key:
        return main_key, name_key

    # No filter needed -> just use first key
    if filter_name is None:
        return keys[0], None

    # With filter and no dotted keys: heuristically pick main/name
    if len(keys) == _TWO_KEYS:
        k0, k1 = keys
        if captures[k0] and captures[k1]:
            n0_children = captures[k0][0].child_count
            n1_children = captures[k1][0].child_count
            if n0_children >= n1_children:
                return k0, k1
            return k1, k0

    return keys[0], keys[1] if len(keys) > 1 else None


def _search_file(filepath: Path, detected_lang: str, pattern: str) -> Iterable[ASTChunk]:
    """Search a single file for structural matches."""
    if detected_lang not in get_args(SupportedLanguage):
        return
    ts_lang = get_language(cast("SupportedLanguage", detected_lang))
    parser = get_parser(cast("SupportedLanguage", detected_lang))

    query_str, filter_name = _shorthand_to_query(detected_lang, pattern)

    try:
        query = Query(ts_lang, query_str)
    except Exception:
        return

    try:
        source = filepath.read_bytes()
        tree = parser.parse(source)
    except Exception:
        return

    cursor = QueryCursor(query)
    captures = cursor.captures(tree.root_node)
    if not captures:
        return

    main_key, name_key = _find_main_and_name_keys(captures, filter_name)
    if main_key is None:
        return

    main_nodes = captures.get(main_key, [])

    # Build lookup: main_node.id -> name_text (for filtering)
    name_by_parent: dict[int, str] = {}
    if name_key and name_key in captures:
        for name_node in captures[name_key]:
            parent = name_node.parent
            if parent is not None:
                name_by_parent[parent.id] = _node_text(name_node, source)

    matched_ids: set[int] = set()
    for node in main_nodes:
        if node.id in matched_ids:
            continue
        matched_ids.add(node.id)

        if filter_name is not None:
            node_name = name_by_parent.get(node.id)
            if node_name != filter_name:
                continue

        yield ASTChunk(
            name=_extract_name(node, source),
            type=node.type,
            docstring=_extract_docstring(node, source),
            source_file=str(filepath),
            line_start_number=node.start_point[0] + 1,
            line_end_number=node.end_point[0] + 1,
            full_code=_node_text(node, source),
        )


@annotated(
    meta={
        "tool_type": "inserter",
        "output_type": "ASTChunk",
        "supported_renders": ["org"],
    }
)
def ssearch(glob: str, pattern: str = "", lang: str = "") -> Iterable[ASTChunk]:
    """Search files for structural patterns using tree-sitter.

    Args:
        glob: Glob pattern to select files (relative or absolute).
        pattern: Tree-sitter S-expression query or shorthand (e.g. "def __init__", "class Foo", "FROM").
        lang: Language override (python, json, dockerfile, toml). Auto-detected from extension if empty.
    """
    glob_path = Path(glob)
    if glob_path.is_absolute():
        # Absolute path: split into base dir + pattern
        parts = glob_path.parts
        base_idx = 0
        for i, part in enumerate(parts):
            if any(c in part for c in "*?["):
                base_idx = i
                break
        if base_idx == 0 and not any(c in glob for c in "*?["):
            # No glob chars: treat as a single file path
            files = [glob_path] if glob_path.is_file() else sorted(glob_path.glob("*"))
        else:
            base_dir = Path(*parts[:base_idx]) if base_idx > 0 else Path(".")
            pattern_str = str(Path(*parts[base_idx:])) if base_idx < len(parts) else "*"
            files = sorted(base_dir.glob(pattern_str))
    else:
        files = sorted(Path(".").glob(glob))

    for filepath in files:
        if not filepath.is_file():
            continue
        detected_lang = _detect_lang(str(filepath), lang or None)
        if not detected_lang:
            continue
        yield from _search_file(filepath, detected_lang, pattern)


@dataclass
class Duplication:
    locations: list[ASTChunk] = field(default_factory=list)
    num_lines: int = 0

    def __str__(self) -> str:
        first = self.locations[0].name if self.locations else "?"
        second = self.locations[1].name if len(self.locations) > 1 else "?"
        return f"{first} <-> {second} ({len(self.locations)} locations, {self.num_lines} lines)"


_MIN_LOCATIONS = 2

_LOC_RE = re.compile(r"^==(.+?):\[(\d+):(\d+)\]$")

_duplicates_cache: dict[str, tuple[float, list[Duplication]]] = {}


def _get_dir_mtime(directory: Path) -> float:
    latest = 0.0
    for root, _dirs, files in directory.walk():
        for f in files:
            try:
                latest = max(latest, (root / f).stat().st_mtime)
            except OSError:
                pass
    return latest


def _resolve_path(path: str) -> Path | None:
    p = Path(path)
    if p.exists():
        return p
    for prefix in ("src/",):
        candidate = Path(prefix) / p
        if candidate.exists():
            return candidate
    return None


def _read_chunk(path: str, module: str, start: int, end: int) -> ASTChunk | None:
    resolved = _resolve_path(path)
    if resolved is None:
        return None
    try:
        lines = resolved.read_text().splitlines()
    except FileNotFoundError:
        return None
    code = "\n".join(lines[start - 1 : end])
    return ASTChunk(
        name=module.rsplit(".", maxsplit=1)[-1],
        type="duplication",
        docstring="",
        source_file=str(resolved),
        line_start_number=start,
        line_end_number=end,
        full_code=code,
    )


def _parse_pylint_duplicates(output: str) -> list[Duplication]:
    duplications: list[Duplication] = []
    current: Duplication | None = None
    code_lines: list[str] = []

    for line in output.splitlines():
        if "R0801" in line:
            if current is not None:
                current.num_lines = len(code_lines)
            current = Duplication()
            code_lines = []
            duplications.append(current)
            continue

        if current is not None:
            m = _LOC_RE.match(line.strip())
            if m:
                module = m.group(1)
                start = int(m.group(2))
                end = int(m.group(3))
                path = module.replace(".", "/") + ".py"
                chunk = _read_chunk(path, module, start, end)
                if chunk is not None:
                    current.locations.append(chunk)
            elif line.startswith("    ") and "(duplicate-code)" not in line:
                code_lines.append(line)
            elif "(duplicate-code)" in line:
                if current is not None:
                    current.num_lines = len(code_lines)
                    current = None
                    code_lines = []

    if current is not None:
        current.num_lines = len(code_lines)

    return duplications


@annotated(
    meta={
        "tool_type": "inserter",
        "output_type": "duplication",
    }
)
def find_duplicates(
    path: str = "src/",
    min_lines: int = 4,
) -> list[Duplication]:
    """Find code duplications using pylint.

    Returns flat list of Duplication items. Each duplication contains
    ASTChunk locations with code read from source files.
    Use extend_dup_locations to add locations as children.

    Args:
        path: Directory or file to scan for duplications.
        min_lines: Minimum similar lines to report (default: 4).

    Example:
        >>> find_duplicates src/udan/, extend_dup_locations, :org
    """
    dir_path = Path(path).resolve()
    dir_mtime = _get_dir_mtime(dir_path) if dir_path.is_dir() else 0.0
    cache_key = f"{dir_path}:{min_lines}"

    if cache_key in _duplicates_cache:
        cached_mtime, cached_dups = _duplicates_cache[cache_key]
        if dir_mtime == cached_mtime:
            return cached_dups

    result = subprocess.run(
        ["pylint", "--disable=all", "--enable=duplicate-code", f"--min-similarity-lines={min_lines}", path],
        capture_output=True,
        text=True,
    )

    duplications = [dup for dup in _parse_pylint_duplicates(result.stdout) if len(dup.locations) >= _MIN_LOCATIONS]
    _duplicates_cache[cache_key] = (dir_mtime, duplications)
    return duplications


@annotated(
    meta={
        "tool_type": "extender",
        "item_type": "duplication",
        "output_type": "ASTChunk",
    }
)
def extend_dup_locations(item: object) -> list[ASTChunk]:
    """Return ASTChunk locations from a Duplication as children.

    Takes a Duplication item and returns its ASTChunk locations.
    """
    if not isinstance(item, Duplication):
        return []
    return item.locations
