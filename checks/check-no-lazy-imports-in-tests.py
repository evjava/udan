#!/usr/bin/env python3
"""Pre-commit hook to forbid lazy imports (imports outside top level) in test files.

The rule: all imports in test files must be at module top level.

Why:
1. Lazy imports hide the real dependency set of a test module from the reader
2. Lazy imports duplicate the same import across many test functions
3. Module-level imports are collected once and make import errors visible at collection time
4. Ruff's PLC0415 is intentionally relaxed for tests, so this hook provides the enforcement

Allowed:
- Imports at module top level
- Imports directly inside a module-level try/except ImportError (optional dependency guard)

Example violation:
    def test_fruits(make_ctx):
        from udan import plugins_tools_demo  # lazy import - hoist to module top level

This is similar to check-no-test-classes.py and check-no-tempfile-in-tests.py.
"""

import ast
import sys
from pathlib import Path

# Module-level try/except is allowed: it guards optional dependencies.
# Imports nested deeper (inside functions, methods, class bodies, module-level if/for/with)
# are all lazy imports.
_ALLOWED_MODULE_LEVEL_PARENTS: tuple[type[ast.stmt], ...] = (ast.Try, ast.TryStar)


def find_lazy_imports(tree: ast.Module) -> list[int]:
    """Collect line numbers of imports that are not at module top level.

    Args:
        tree: Parsed module AST

    Returns:
        List of 1-based line numbers of lazy imports
    """
    line_numbers: list[int] = []

    def visit(node: ast.AST, at_module_level: bool) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.Import, ast.ImportFrom)):
                if not at_module_level:
                    line_numbers.append(child.lineno)
                continue

            still_module_level = at_module_level and isinstance(child, _ALLOWED_MODULE_LEVEL_PARENTS)
            visit(child, still_module_level)

    visit(tree, True)
    return line_numbers


def check_file(file_path: str) -> list[tuple[int, str]]:
    """Check a Python file for lazy imports.

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
    return [(line_no, lines[line_no - 1].strip()) for line_no in find_lazy_imports(tree)]


def main() -> int:
    """Main entry point."""
    args = sys.argv[1:]
    if not args:
        print("Usage: check-no-lazy-imports-in-tests.py <file1.py> [file2.py] ...")
        return 2

    exit_code = 0
    for file_path in args:
        violations = check_file(file_path)
        if violations:
            exit_code = 1
            for line_no, source_line in violations:
                print(
                    f"{file_path}:{line_no}: lazy import: '{source_line}'\n"
                    f"  → imports in test files must be at module top level\n"
                    f"  → Hoist this import to the module import block and merge it with existing imports"
                )

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
