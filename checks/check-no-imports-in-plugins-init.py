#!/usr/bin/env python3
"""Pre-commit hook to forbid any imports in plugin package __init__.py files.

The rule: src/udan_plugins_*/__init__.py must contain ONLY the plugin
description (the module docstring) - no imports, no re-exports, no __all__.

Why:
1. The plugin package root is documentation, not an API surface: plugins are
   discovered by scanning udan_plugins_*/plugins_*.py (see udan.plugins_system),
   and CONFIG is declared in the plugin module itself
2. Re-exports here make the package root look like a second API and invite
   imports of plugin symbols from impl_ modules (see forbid-plugins-in-impl)
3. No imports means importing the package is free - the plugin loader can
   scan/inspect packages without pulling in their implementations

Example violation:
    from udan.plugins_tools_demo.plugins_demo import DOMAIN  # import in __init__.py

This is similar to check-no-imports-in-try-except.py and check-no-lazy-imports-in-tests.py.
"""

import ast
import sys
from pathlib import Path


def find_imports(tree: ast.Module) -> list[int]:
    """Collect line numbers of all import statements in the module.

    Args:
        tree: Parsed module AST

    Returns:
        List of 1-based line numbers of imports (anywhere, including lazy ones)
    """
    return [node.lineno for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom))]


def check_file(file_path: str) -> list[tuple[int, str]]:
    """Check a Python file for imports.

    Args:
        file_path: Path to the file to check

    Returns:
        List of (line_number, source_line) tuples for each violation
    """
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
    return [(line_no, lines[line_no - 1].strip()) for line_no in find_imports(tree)]


def main() -> int:
    """Main entry point."""
    args = sys.argv[1:]
    if not args:
        print("Usage: check-no-imports-in-plugins-init.py <file1.py> [file2.py] ...")
        return 2

    exit_code = 0
    for file_path in args:
        violations = check_file(file_path)
        if violations:
            exit_code = 1
            for line_no, source_line in violations:
                print(
                    f"{file_path}:{line_no}: import in plugin __init__.py: '{source_line}'\n"
                    f"  → src/udan_plugins_*/__init__.py must contain ONLY the plugin description\n"
                    f"  → Remove this import (and any __all__ re-exports); import the submodule directly instead"
                )

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
