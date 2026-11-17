#!/usr/bin/env python3
"""Pre-commit hook to forbid plugins_ imports inside impl_ files.

The rule: impl_ modules should NOT import from plugins_ modules because:
1. Plugins are meant to be dynamically loaded via the tool registry
2. Static imports from plugins create tight coupling and break the plugin architecture
3. impl_ modules should work independently of any specific plugin

Both import forms are caught: 'from udan.plugins_X import ...' and
'import udan.plugins_X'. (This hook inherits the plugins_ imports ban from
the retired forbid-plugins-in-core, which policed the core_ modules that
have since been renamed to impl_.)

NO exceptions: Not even in TYPE_CHECKING blocks or functions.
TYPE_CHECKING is banned in this project (indicates circular imports).

This is similar to check-no-impl-in-impl.py but for plugins_ imports.
"""

import re
import sys
from pathlib import Path

# Valid exceptions: impl_ modules that are allowed to import plugins_ modules
# These should be rare and well-justified
EXCLUSIONS_OK = [
    # Add orchestrator modules here if they truly need to import plugins
    # Format: "impl_module_name.py"
]


def check_file(file_path: str) -> int:
    """Check a file for forbidden plugins_ imports.

    Args:
        file_path: Path to the file to check

    Returns:
        1 if violations found, 0 otherwise
    """
    path = Path(file_path)

    # Only check impl_ files
    if not path.name.startswith("impl_"):
        return 0

    # Skip exception modules
    if path.name in EXCLUSIONS_OK:
        return 0

    content = path.read_text()

    # Find all import statements from plugins_
    # Pattern: from udan.plugins_X import ... or import udan.plugins_X...
    pattern = r"\b(?:from|import)\s+udan\.(plugins_[a-zA-Z0-9_]+(?:\.[a-zA-Z0-9_]+)?)"

    violations = []
    for match in re.finditer(pattern, content):
        statement = match.group(0)

        # Get the line number
        line_num = content[: match.start()].count("\n") + 1

        violations.append((file_path, line_num, statement))

    # Print violations
    if violations:
        for violated_path, line_num, statement in violations:
            print(
                f"{violated_path}:{line_num}: impl_ module imports from plugins_: '{statement}'\n"
                f"  → impl_ modules should not import from plugins_ (breaks plugin architecture)\n"
                f"  → Plugins should be dynamically loaded via the tool registry\n"
                f"  → Consider: 1) Moving types to api_ module, 2) Using dynamic lookup, or 3) Protocol checking"
            )
        return 1

    return 0


def main() -> int:
    """Main entry point."""
    args = sys.argv[1:]
    if not args:
        return 2

    exit_code = 0
    for file_path in args:
        result = check_file(file_path)
        if result != 0:
            exit_code = result

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
