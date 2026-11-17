#!/usr/bin/env python3
"""Pre-commit hook to forbid imports inside try/except.

The rule: import statements must not appear anywhere inside a try statement
(body, handlers, else and finally included, at any nesting depth).

Why:
1. try/except around an import silently disables code when the dependency is
   missing or broken - the failure surfaces far from its cause (or never)
2. An ImportError is not the only thing a bare/broad except swallows there
3. Imports belong at module top level, where missing dependencies fail loudly

Instead of try/except, state availability explicitly:
- src: importlib.util.find_spec("dep") is not None + a top-level conditional import
- tests: pytest.importorskip("module")

Example violation:
    try:
        from intentgraph import RepositoryAnalyzer  # forbidden: import inside try
    except ImportError:
        RepositoryAnalyzer = None

Exclusions (EXCLUSIONS_ADHOC below) exist for the rare import that must sit inside
try/except because the module has to load without the dependency - a plugin family
other plugins import from, whose tools degrade to a call-time error instead of
taking three plugin families down with them. Entries are
'src/path/file.py:<num>:<stripped content>' (matched by content, so a line that
moves keeps its exclusion) or 'src/path/file.py:*' for a whole file. Violation
output uses the same format - copy-paste it directly into EXCLUSIONS_ADHOC.

This is similar to check-no-lazy-imports-in-tests.py and forbid-type-checking.
"""

import ast
import sys
from pathlib import Path

# Once inside a try statement, the whole subtree is forbidden: body, handlers,
# else and finally branches, and anything nested deeper.
_TRY_PARENTS: tuple[type[ast.stmt], ...] = (ast.Try, ast.TryStar)

# fmt: off
EXCLUSIONS_ADHOC: set[str] = {
    # plugins_dev.py: tree-sitter lives in the dev dependency group, not
    # [project.dependencies], and the module still has to import without it -
    # plugins_org and plugins_markdown take Duplication from it, so a plain
    # top-level import turns one missing package into three unloaded plugin
    # families ("Failed to load module ...: No module named tree_sitter" on a
    # fresh system). The import degrades to the _TREE_SITTER_AVAILABLE flag and
    # ssearch reports the missing dependency when it is called.
    "src/udan/plugins_tools_examples/plugins_dev.py:11:from tree_sitter import Query, QueryCursor",
    "src/udan/plugins_tools_examples/plugins_dev.py:12:from tree_sitter_language_pack import SupportedLanguage, get_language, get_parser",
}
# fmt: on

# entry -> 'file.py:content' matching key (line number dropped, content kept)
_ENTRY_KEYS: dict[str, str] = {}
# files with a ':*' whole-file exclusion
_FILE_WILDCARDS: set[str] = set()
for _entry in EXCLUSIONS_ADHOC:
    if _entry.endswith(":*"):
        _FILE_WILDCARDS.add(_entry.rsplit(":*", 1)[0])
        continue
    _parts = _entry.split(":", 2)  # src/path/file.py : 11 : content
    if len(_parts) == 3:  # noqa: PLR2004
        _ENTRY_KEYS[_entry] = f"{_parts[0]}:{_parts[2]}"
_CONTENT_EXCLUSIONS: set[str] = set(_ENTRY_KEYS.values())

# Matching state, consumed by find_stale_exclusions at the end of the run
_EXCLUSIONS_MATCHED: set[str] = set()
_FILES_CHECKED: set[str] = set()


def find_imports_in_try(tree: ast.Module) -> list[int]:
    """Collect line numbers of imports located inside a try statement.

    Args:
        tree: Parsed module AST

    Returns:
        List of 1-based line numbers of imports inside try/except
    """
    line_numbers: list[int] = []

    def visit(node: ast.AST, in_try: bool) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.Import, ast.ImportFrom)):
                if in_try:
                    line_numbers.append(child.lineno)
                continue

            visit(child, in_try or isinstance(child, _TRY_PARENTS))

    visit(tree, False)
    return line_numbers


def check_file(file_path: str) -> list[tuple[int, str]]:
    """Check a Python file for imports inside try/except.

    Args:
        file_path: Path to the file to check

    Returns:
        List of (line_number, source_line) tuples for each violation not excluded
    """
    _FILES_CHECKED.add(file_path)
    if file_path in _FILE_WILDCARDS:
        return []

    path = Path(file_path)
    try:
        source = path.read_text(encoding="utf-8")
    except OSError, UnicodeDecodeError:
        return []

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    lines = source.splitlines()
    violations = []
    for line_no in find_imports_in_try(tree):
        source_line = lines[line_no - 1].strip()
        key = f"{file_path}:{source_line}"
        if key in _CONTENT_EXCLUSIONS:
            _EXCLUSIONS_MATCHED.add(key)
            continue
        violations.append((line_no, source_line))
    return violations


def find_stale_exclusions() -> list[str]:
    """Find exclusions whose import no longer sits inside try/except.

    Only files this run checked count - the hook passes a file before its stale
    exclusion is reported, so an exclusion for an untouched file never fires.

    Returns:
        EXCLUSIONS_ADHOC entries to remove
    """
    stale = []
    for entry, key in _ENTRY_KEYS.items():
        file_path = entry.rsplit(":", 2)[0]
        if file_path in _FILES_CHECKED and key not in _EXCLUSIONS_MATCHED:
            stale.append(entry)
    return sorted(stale)


def main() -> int:
    """Main entry point."""
    args = sys.argv[1:]
    if not args:
        print("Usage: check-no-imports-in-try-except.py <file1.py> [file2.py] ...")
        return 2

    exit_code = 0
    for file_path in args:
        violations = check_file(file_path)
        if violations:
            exit_code = 1
            for line_no, source_line in violations:
                print(
                    f"{file_path}:{line_no}: import inside try/except: '{source_line}'\n"
                    f"  → imports must live at module top level, outside try/except\n"
                    f"  → For optional dependencies use importlib.util.find_spec (src) or pytest.importorskip (tests)\n"
                    f"  → If the module has to load without the dependency, add the line above to EXCLUSIONS_ADHOC in checks/check-no-imports-in-try-except.py"
                )

    stale = find_stale_exclusions()
    if stale:
        exit_code = 1
        print("\nStale exclusions (the import no longer sits inside try/except):")
        for entry in stale:
            print(f"  '{entry}' - remove it from EXCLUSIONS_ADHOC in checks/check-no-imports-in-try-except.py")

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
