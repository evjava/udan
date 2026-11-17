#!/usr/bin/env/python3
"""Pre-commit hook to check ARG (unused argument) violations only in protected methods.

This hook runs ruff with --select=ARG and filters the results to only show
violations in methods that start with underscore (protected methods like _method).

Public methods (without underscore prefix) are ignored - only protected methods
are checked for unused arguments.
"""

import json
import re
import subprocess
import sys
from pathlib import Path


def get_function_name_at_line(file_path: Path, line_no: int) -> str | None:
    """Get the function/method name at a given line number.

    Args:
        file_path: Path to the Python file
        line_no: 1-based line number

    Returns:
        Function/method name if found, None otherwise
    """
    try:
        with open(file_path, encoding="utf-8") as f:
            lines = f.readlines()
    except OSError, UnicodeDecodeError:
        return None

    if line_no < 1 or line_no > len(lines):
        return None

    line = lines[line_no - 1]

    # Look for 'def function_name(' pattern in the line
    # Handle cases like:
    # - def _method(self, ...
    # -   def _method(...
    # - async def _method(self, ...
    match = re.search(r"\bdef\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(", line)
    if match:
        return match.group(1)

    return None


def run_ruff_arg(files: list[Path]) -> list[dict]:
    """Run ruff with --select=ARG and return parsed violations.

    Args:
        files: List of files to check

    Returns:
        List of violation dictionaries
    """
    cmd = [
        "uv",
        "run",
        "ruff",
        "check",
        "--select=ARG",
        "--output-format=json",
        *[str(f) for f in files],
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode == 0:
        return []

    try:
        # With --output-format=json ruff reports violations on stdout; stderr only
        # carries noise (e.g. uv warnings), so parse stdout first and fall back
        output = result.stdout if result.stdout else result.stderr
        data = json.loads(output)
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []


def is_protected_method_violation(violation: dict) -> bool:
    """Check if a violation is in a protected method (starts with underscore).

    Args:
        violation: Ruff violation dictionary

    Returns:
        True if violation is in a protected method
    """
    filepath = violation.get("filename")
    if not filepath:
        return False

    location = violation.get("location", {})
    if not location:
        return False

    row = location.get("row")
    if not row:
        return False

    function_name = get_function_name_at_line(Path(filepath), row)
    if function_name and function_name.startswith("_"):
        return True

    return False


def format_violation(violation: dict) -> str:
    """Format a violation for display.

    Args:
        violation: Ruff violation dictionary

    Returns:
        Formatted string
    """
    filepath = violation.get("filename", "")
    location = violation.get("location", {})
    row = location.get("row", "?")
    column = location.get("column", "?")
    message = violation.get("message", "")
    code = violation.get("code", "")

    return f"{filepath}:{row}:{column}: {code} {message}"


def main() -> int:
    """Main entry point for the pre-commit hook."""
    if len(sys.argv) < 2:
        print("Usage: check-arg-in-protected-methods.py <file1.py> [file2.py] ...")
        return 1

    files = [Path(f) for f in sys.argv[1:]]
    violations = run_ruff_arg(files)

    if not violations:
        return 0

    # Filter to only protected methods (methods starting with _)
    protected_violations = [v for v in violations if is_protected_method_violation(v)]

    if protected_violations:
        # Sort by file and line number for consistent output
        protected_violations.sort(
            key=lambda v: (
                v.get("filename", ""),
                v.get("location", {}).get("row", 0),
            )
        )

        for v in protected_violations:
            print(format_violation(v))

        print()
        print(f"Found {len(protected_violations)} ARG violation(s) in protected methods")

        # Also show summary of skipped violations
        skipped = len(violations) - len(protected_violations)
        if skipped > 0:
            print(f"(Skipped {skipped} violation(s) in public methods)")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
