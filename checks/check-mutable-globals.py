#!/usr/bin/env python3
"""Pre-commit hook to detect module-level mutable global variables.

This script checks for module-level assignments where:
1. Variable name is lowercase (not UPPER_CASE constants)
2. Value is a mutable literal (dict, list, set)

Example violations:
    x = {1: 2}           # lowercase name + mutable dict
    my_list = [1, 2, 3]  # lowercase name + mutable list
    items = {1, 2, 3}    # lowercase name + mutable set
"""

import ast
import sys
from pathlib import Path


def is_upper_case(name: str) -> bool:
    """Check if a name is UPPER_CASE (constant naming convention)."""
    return name.isupper() and "_" in name or name.isupper()


def check_file(file_path: str) -> list[tuple[int, str, str]]:
    """Check a Python file for module-level mutable globals.

    Returns:
        List of (line_number, variable_name, violation_type) tuples
    """
    path = Path(file_path)

    try:
        with open(path, encoding="utf-8") as f:
            source = f.read()
    except OSError, UnicodeDecodeError:
        return []

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    violations = []

    for node in tree.body:
        # Only check module-level assignments
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    var_name = target.id

                    # Skip UPPER_CASE constants (allowed)
                    if is_upper_case(var_name):
                        continue

                    # Skip dunder variables (allowed)
                    if var_name.startswith("__") and var_name.endswith("__"):
                        continue

                    # Check for mutable literal values
                    value_type = None
                    if isinstance(node.value, ast.Dict):
                        value_type = "dict"
                    elif isinstance(node.value, ast.List):
                        value_type = "list"
                    elif isinstance(node.value, ast.Set):
                        value_type = "set"

                    if value_type:
                        violations.append((node.lineno, var_name, value_type))

    return violations


def main() -> int:
    """Main entry point for the pre-commit hook."""
    if len(sys.argv) < 2:
        print("Usage: check-mutable-globals.py <file1.py> [file2.py] ...")
        return 1

    exit_code = 0

    for file_path in sys.argv[1:]:
        violations = check_file(file_path)

        if violations:
            exit_code = 1
            for line_no, var_name, value_type in violations:
                print(
                    f"{file_path}:{line_no}: "
                    f"module-level mutable {value_type} '{var_name}' "
                    f"should be UPPER_CASE constant or avoided"
                )

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
