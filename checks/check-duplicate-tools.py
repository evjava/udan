#!/usr/bin/env python3
"""Pre-commit hook to check for duplicate tool definitions across files.

If the same tool name (function decorated with @annotated) is defined
in multiple files, it should be deduplicated to avoid shadowing.

This catches cases where:
- Same operator/attribute is defined in multiple modules
- Same render function is defined in multiple modules
- The later registration shadows the earlier one (silent bug)
"""

import ast
import sys
from collections import defaultdict
from pathlib import Path


def get_annotated_functions(file_path: Path) -> list[str]:
    """Extract names of functions decorated with @annotated.

    Args:
        file_path: Path to the Python file

    Returns:
        List of function names decorated with @annotated
    """
    try:
        with open(file_path, encoding="utf-8") as f:
            source = f.read()
    except Exception:
        return []

    try:
        tree = ast.parse(source)
    except Exception:
        return []

    functions = []

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            # Check if this function has @annotated decorator
            for decorator in node.decorator_list:
                # Check if decorator is @annotated or @annotated(...)
                if isinstance(decorator, ast.Name) and decorator.id == "annotated":
                    functions.append(node.name)
                    break
                elif (
                    isinstance(decorator, ast.Call)
                    and isinstance(decorator.func, ast.Name)
                    and decorator.func.id == "annotated"
                ):
                    functions.append(node.name)
                    break

    return functions


def main():
    """Main entry point for the pre-commit hook."""
    # Scan all src/udan Python files
    files = list(Path("src/udan").glob("**/*.py"))

    # Track functions and their locations
    function_locations = defaultdict(set)

    for file_path in files:
        functions = get_annotated_functions(file_path)
        for func in functions:
            # Only track if file name contains the expected module pattern
            # (plugins_*.py, impl_*.py, etc.)
            if any(pattern in file_path.name for pattern in ["plugins_", "impl_"]):
                function_locations[func].add(file_path)

    # Find duplicates (functions defined in 2+ DIFFERENT files)
    duplicates = {func: locations for func, locations in function_locations.items() if len(locations) > 1}

    if duplicates:
        print("error: duplicate tool definitions found across files", file=sys.stderr)
        print("Functions decorated with @annotated should have unique names.", file=sys.stderr)
        print("Duplicate registrations will be shadowed (last one wins).", file=sys.stderr)
        print("", file=sys.stderr)
        print("Duplicates:", file=sys.stderr)
        for func, locations in sorted(duplicates.items()):
            print(f"  {func}:", file=sys.stderr)
            for loc in sorted(locations):
                print(f"    - {loc}", file=sys.stderr)
        print("", file=sys.stderr)
        print("Fix: Remove duplicate definition or rename to avoid shadowing.", file=sys.stderr)
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
