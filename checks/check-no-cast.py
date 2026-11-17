#!/usr/bin/env python3
"""Pre-commit hook to forbid cast() usage in non-plugin modules.

This hook enforces that typing.cast() should not be used in core modules.
Proper type fixes should be used instead:
- Better type annotations (TypeVar, explicit types)
- isinstance() checks for type narrowing
- Runtime assertions
- Proper return type annotations

cast() is allowed in:
- plugins_* modules (external plugins may need it)
- test files

Rationale:
- cast() is often a crutch for poor type design
- It bypasses type checking without runtime validation
- Better alternatives provide both type safety and runtime checks
"""

import re
import subprocess
import sys
from pathlib import Path


def check_file_for_cast(file_path: Path) -> list[tuple[int, str]]:
    """Check a file for cast() usage.

    Args:
        file_path: Path to the file to check

    Returns:
        List of (line_number, line) tuples where cast() is found
    """
    violations = []

    try:
        with open(file_path, encoding="utf-8") as f:
            lines = f.readlines()
    except OSError, UnicodeDecodeError:
        return violations

    # Pattern to match cast( usage
    # Matches: cast(, cast( "Type", cast("Type", cast(Type,
    cast_pattern = re.compile(r"\bcast\(")

    for line_no, line in enumerate(lines, start=1):
        if cast_pattern.search(line):
            violations.append((line_no, line.rstrip()))

    return violations


def is_plugin_file(file_path: Path) -> bool:
    """Check if a file is in a plugins_* module.

    Args:
        file_path: Path to the file

    Returns:
        True if the file is in a plugins_* module
    """
    path_str = str(file_path)
    # Check if the file path contains plugins_ (e.g., src/udan/plugins_*/ or src/udan_plugins_*/)
    return "/plugins_" in path_str or "\\plugins_" in path_str


def main() -> None:
    """Run the pre-commit hook."""
    # Get files to check from command line or use git to find staged Python files
    if len(sys.argv) > 1:
        # When files are passed as arguments, check them all
        files = [Path(f) for f in sys.argv[1:]]
    else:
        # When run from pre-commit, only check src/ files
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
            capture_output=True,
            text=True,
        )
        files = [Path(f) for f in result.stdout.splitlines() if f.endswith(".py")]
        # Only check files in src/ when running from git
        files = [f for f in files if f.is_file() and str(f).startswith("src/")]

    all_violations = []

    for file_path in files:
        # Skip plugin files and test files
        if is_plugin_file(file_path) or str(file_path).startswith("tests/"):
            continue

        # Check for cast() usage
        for line_no, line in check_file_for_cast(file_path):
            all_violations.append((file_path, line_no, line))

    if all_violations:
        print("cast() usage is forbidden in non-plugin modules.", file=sys.stderr)
        print("Use proper type fixes instead:", file=sys.stderr)
        print("  - Better type annotations (TypeVar, explicit types)", file=sys.stderr)
        print("  - isinstance() checks for type narrowing", file=sys.stderr)
        print("  - Runtime assertions", file=sys.stderr)
        print("  - Proper return type annotations", file=sys.stderr)
        print("", file=sys.stderr)
        for file_path, line_no, line in all_violations:
            print(f"{file_path}:{line_no}: {line}", file=sys.stderr)
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
