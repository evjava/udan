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

This is similar to check-no-lazy-imports-in-tests.py and forbid-type-checking.
"""

import ast
import sys
from pathlib import Path

# Once inside a try statement, the whole subtree is forbidden: body, handlers,
# else and finally branches, and anything nested deeper.
_TRY_PARENTS: tuple[type[ast.stmt], ...] = (ast.Try, ast.TryStar)


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
    return [(line_no, lines[line_no - 1].strip()) for line_no in find_imports_in_try(tree)]


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
                    f"  → For optional dependencies use importlib.util.find_spec (src) or pytest.importorskip (tests)"
                )

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
