#!/usr/bin/env python3
"""Pre-commit hook to forbid @staticmethod.

A staticmethod uses neither self nor the class, so the class adds nothing
but an indirection: callers must write Cls.method(...) or self.method(...)
for what is a plain function.

Extract the method to a module-level function with an underscore prefix
instead, and update the call sites.
"""

import ast
import sys
from pathlib import Path


def check_file(file_path: Path) -> list[tuple[int, str]]:
    """Check a file for functions decorated with @staticmethod.

    Args:
        file_path: Path to the file to check

    Returns:
        List of (line_number, line) tuples where @staticmethod is found
    """
    try:
        source = file_path.read_text(encoding="utf-8")
    except OSError, UnicodeDecodeError:
        return []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    lines = source.splitlines()
    violations = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            name = decorator.attr if isinstance(decorator, ast.Attribute) else getattr(decorator, "id", None)
            if name == "staticmethod":
                violations.append((decorator.lineno, lines[decorator.lineno - 1]))
                break  # one report per function is enough
    return violations


def main() -> int:
    """Run the pre-commit hook."""
    if len(sys.argv) < 2:
        print("Usage: check-no-staticmethod.py <file1.py> [file2.py] ...")
        return 1

    all_violations = []

    for file_path_str in sys.argv[1:]:
        file_path = Path(file_path_str)
        for line_no, line in check_file(file_path):
            all_violations.append((file_path, line_no, line))

    if all_violations:
        print("@staticmethod is forbidden.", file=sys.stderr)
        print("Extract it to a module-level function with an underscore prefix", file=sys.stderr)
        print("(e.g. `_my_helper`) and update the call sites.", file=sys.stderr)
        print("", file=sys.stderr)
        for file_path, line_no, line in all_violations:
            print(f"{file_path}:{line_no}: {line}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
