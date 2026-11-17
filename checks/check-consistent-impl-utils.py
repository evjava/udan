#!/usr/bin/env python3
"""Pre-commit hook to check consistent impl-utils module usage.

The rule: impl_utils_<name> modules should only be imported by their corresponding
impl_<name> module (with exceptions for widely-used utilities).

Generic rule:
- impl_utils_render_engine should only be imported by impl_render_engine
- impl_utils_tools_loader should only be imported by impl_tools_loader

Exceptions (temporary - these should be refactored to follow the generic rule):
- impl_query_parser imports impl_utils_parsing (udan.parsing, scanned since the
  package joined udan): the parse tree the grammar module defines is the query
  parser's own output format - the parser lowers query text into it, so the
  import is the pair the generic rule's name matching cannot predict
"""

import re
import sys
from pathlib import Path

# (importing module stem, imported impl_utils module stem) pairs that are
# allowed despite not matching the generic rule; each entry needs a reason,
# documented in the module docstring above
EXCEPTIONS_ADHOC: set[tuple[str, str]] = {
    ("impl_query_parser", "impl_utils_parsing"),
}


def get_expected_module_for_utils(utils_module: str) -> str | None:
    """Get the expected impl module for a given utils module.

    Generic rule: impl_utils_<name> -> impl_<name>
    Example: impl_utils_render_engine -> impl_render_engine

    Args:
        utils_module: Name of the utils module (e.g., "impl_utils_render_engine")

    Returns:
        Expected impl module name (e.g., "impl_render_engine"), or None if no mapping
    """
    match = re.match(r"^impl_utils_(.+)$", utils_module)
    if match:
        return f"impl_{match.group(1)}"
    return None


def check_file(file_path: str) -> int:
    """Check a file for consistent impl-utils imports.

    Args:
        file_path: Path to the file to check

    Returns:
        1 if violations found, 0 otherwise
    """
    path = Path(file_path)
    stem = path.stem  # e.g., "impl_render_engine" from "impl_render_engine.py"

    # Only check impl_ files
    if not stem.startswith("impl_"):
        return 0

    # Skip impl_utils_* files from being checked
    if stem.startswith("impl_utils_"):
        return 0

    content = path.read_text()
    violations = []

    # Use the original file_path for output to preserve src/udan/ prefix
    display_path = file_path

    # Find all impl_utils_* imports (any udan package segment: udan.core_tools_loading.impl_utils_X included)
    pattern = r"from udan(?:\.[a-z_]\w+)*\.(impl_utils_[a-zA-Z0-9_]+(?:\.[a-zA-Z0-9_]+)?)\s+import"

    for match in re.finditer(pattern, content):
        utils_module = match.group(1).split(".")[0]  # Get base module name

        # Get the expected module for this utils module
        expected_module = get_expected_module_for_utils(utils_module)

        if expected_module is None:
            # Unknown utils module format - flag it
            line_num = content[: match.start()].count("\n") + 1
            violations.append(
                f"{display_path}:{line_num}: Unknown impl_utils module: 'from udan.{utils_module}'\n"
                f"  → Module '{utils_module}' doesn't match the pattern 'impl_utils_<name>'\n"
                f"  → Either rename it to follow the pattern or add it to WIDELY_USED_UTILS"
            )
            continue

        # Check if current module is the expected one
        if stem != expected_module and (stem, utils_module) not in EXCEPTIONS_ADHOC:
            line_num = content[: match.start()].count("\n") + 1
            violations.append(
                f"{display_path}:{line_num}: Inconsistent impl_utils import: '{stem}' imports '{utils_module}'\n"
                f"  → '{utils_module}' should only be imported by '{expected_module}'\n"
                f"  → Move the import from {stem} to {expected_module}"
            )

    if violations:
        for violation in violations:
            print(violation)
        return 1

    return 0


def main() -> int:
    """Main entry point for the pre-commit hook.

    Args:
        File paths to check (passed via sys.argv)

    Returns:
        1 if any violations found, 0 otherwise
    """
    # If called incorrectly, print usage
    if len(sys.argv) < 2:
        print("Usage: check-consistent-impl-utils.py file1.py file2.py ...")
        return 1

    exit_code = 0
    for file_path in sys.argv[1:]:
        exit_code |= check_file(file_path)

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
