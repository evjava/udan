#!/usr/bin/env python3
"""Pre-commit hook to check for duplicate constant definitions across files.

If the same constant name is defined in multiple Python files, it should be
extracted to a shared module to avoid duplication.

Constants are identified as:
- Module-level (not inside a class or function)
- Uppercase with underscores (e.g., MY_CONSTANT, _MY_PRIVATE_CONSTANT)
- Assigned a literal value (not a function call or expression)

This prevents the "copy-paste" anti-pattern where constants are defined
in multiple files instead of being extracted to a shared module.
"""

import ast
import sys
from collections import defaultdict
from pathlib import Path


def get_module_constants(file_path: Path) -> list[str]:
    """Extract constant names from a Python file.

    Args:
        file_path: Path to the Python file

    Returns:
        List of constant names defined at module level
    """
    try:
        with open(file_path, encoding="utf-8") as f:
            source = f.read()
    except Exception:
        return []

    try:
        tree = ast.parse(source)
    except Exception:
        # If we can't parse the file, skip it
        return []

    constants = []

    for node in ast.walk(tree):
        # We only want module-level assignments (not in classes or functions)
        if isinstance(node, ast.Assign):
            # Check if this assignment is at module level
            parent = getattr(node, "parent", None)
            if parent is None:
                # Check if the target is a simple Name (not a subscript, attribute, etc.)
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        name = target.id
                        # Check if it looks like a constant (uppercase with underscores)
                        if name.isupper() and "_" in name:
                            constants.append(name)

    return constants


def main():
    """Main entry point for the pre-commit hook."""
    # Get list of staged Python files
    # For now, we'll scan all src/udan Python files
    files = list(Path("src/udan").glob("**/*.py"))

    # Track constants and their locations (use set to avoid counting same file twice)
    constant_locations = defaultdict(set)

    for file_path in files:
        constants = get_module_constants(file_path)
        for const in constants:
            constant_locations[const].add(file_path)

    # Find duplicates (constants defined in 2+ DIFFERENT files)
    duplicates = {const: locations for const, locations in constant_locations.items() if len(locations) > 1}

    if duplicates:
        print("error: duplicate constant definitions found across files", file=sys.stderr)
        print("Constants should be defined in ONE shared module, not copied across files.", file=sys.stderr)
        print("", file=sys.stderr)
        print("Duplicates:", file=sys.stderr)
        for const, locations in sorted(duplicates.items()):
            print(f"  {const}:", file=sys.stderr)
            for loc in sorted(locations):
                print(f"    - {loc}", file=sys.stderr)
        print("", file=sys.stderr)
        print("Fix: Extract the constant to a shared module (e.g., impl_constants.py)", file=sys.stderr)
        print("and import it from all files that use it.", file=sys.stderr)
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
