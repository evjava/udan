#!/usr/bin/env python3
"""Pre-commit hook to forbid impl_ imports inside impl_ files.

The rule: impl_ modules should only import from:
- udan.api - public APIs
- udan.core.api_* - API modules
- udan.core.impl_constants - constants
- udan.io_* - IO utilities
- udan.core.impl_utils* - utility modules

They should NOT import from other impl_ modules.

Exceptions:
1. Orchestrator modules (impl_ioc.py, impl_udan_context.py) can import impl_ modules
2. Imports inside TYPE_CHECKING blocks are allowed (type hints only)
3. Local imports inside functions are allowed (lazy loading to avoid circular deps)
4. Self-imports (module importing itself) are allowed
"""

import re
import sys
from pathlib import Path

# Ad-hoc impl-to-impl imports: temporary architectural debt
# These represent violations that should eventually be resolved
# Each entry should have a comment explaining WHY the exception exists
EXCLUSIONS_ADHOC = {
    "impl_attribute_storage",  # Needed for attribute storage instantiation
    "impl_constants",  # Shared internal constants (NODE_* prefixes, DEBUG, INF) - implementation protocol
    "impl_dependency_registry",  # Needed by ToolsLoader for temporary injector creation
    "impl_exec_context",  # Needed for ExecContext instantiation
    "impl_io_modules",  # Utility functions for loading modules from filesystem
    "impl_udan_context",  # Main UdanContext - coordinates all components (TODO: refactor to reduce coupling)
    # udan.plugins_history: the tag codec the two saved-queries storages share - split_tags/join_tags
    # are the one serialization both the JSONL and the SQLite backend need to agree on
    # (scanned since the package joined udan)
    "impl_saved_tags",
}

# Valid impl-to-impl imports: allowed by architectural design
# These are patterns (supports .* wildcards) for module names that are allowed to be imported
EXCLUSIONS_OK = [
    "impl_ioc.py",  # Inversion of Control container - orchestrates all components and their dependencies
    "impl_ioc_request.py",  # Request-scoped IOC provider - provides per-request components like logger and exec_context
    "impl_utils_.*.py",  # Utility modules - shared helper functions that can be imported by anyone
]


def matches_pattern(filename: str, pattern: str) -> bool:
    """Check if a filename matches a pattern with wildcards.

    Args:
        filename: The filename to check (e.g., "impl_utils_parsing.py")
        pattern: The pattern with wildcards (e.g., "impl_utils_.*.py")

    Returns:
        True if filename matches the pattern, False otherwise
    """
    # If pattern contains .*, use it as-is as a regexp
    # Otherwise, treat as exact match
    if ".*" in pattern:
        return re.fullmatch(pattern, filename) is not None
    return filename == pattern


def is_in_type_checking_block(content: str, pos: int) -> bool:
    """Check if a position is inside a TYPE_CHECKING block.

    Args:
        content: File content
        pos: Position to check

    Returns:
        True if inside TYPE_CHECKING block, False otherwise
    """
    # Find the last "if TYPE_CHECKING:" before this position
    before = content[:pos]
    type_checking_starts = list(re.finditer(r"if TYPE_CHECKING:", before))
    if not type_checking_starts:
        return False

    # Check if we're still inside the TYPE_CHECKING block
    # Need to find the dedent that ends the TYPE_CHECKING block
    last_type_checking = type_checking_starts[-1].start()
    after_type_checking = content[last_type_checking:pos]

    # Count the indentation level change after TYPE_CHECKING
    # The TYPE_CHECKING block ends when we see a line with less or equal indentation
    # to the "if TYPE_CHECKING:" line
    type_checking_line_start = content.rfind("\n", 0, last_type_checking) + 1
    type_checking_indent = len(content[type_checking_line_start:last_type_checking]) - len(
        content[type_checking_line_start:last_type_checking].lstrip()
    )

    lines = after_type_checking.split("\n")
    for line in lines[1:]:  # Skip the TYPE_CHECKING line itself
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        # Check if this line has dedented back to or below TYPE_CHECKING level
        line_indent = len(line) - len(line.lstrip())
        if (
            line_indent <= type_checking_indent
            and stripped
            and not stripped.startswith("from")
            and not stripped.startswith("import")
        ):
            return False

    return True


def is_inside_function(content: str, pos: int) -> bool:
    """Check if a position is inside a function definition.

    Uses a simple heuristic: if the line is indented (4+ spaces), it's likely
    inside a function. This works because:
    - Top-level imports are never indented
    - Local imports inside functions are indented
    - Class method imports would also be indented but are less common

    Args:
        content: File content
        pos: Position to check

    Returns:
        True if inside a function, False otherwise
    """
    before = content[:pos]
    lines = before.split("\n")
    import_line = lines[-1]

    # Check if import line is indented (4+ spaces = inside function/class)
    # We use >= 4 spaces to match standard Python indentation
    if import_line.startswith("    ") or import_line.startswith("\t\t"):
        return True

    return False


# Global to collect all violations for grouped reporting
_all_violations: dict[str, list[tuple[str, int, str]]] = {}
_no_adhocs_mode = False


def check_file(file_path: str, no_adhocs: bool = False) -> int:
    """Check a file for forbidden impl_ imports.

    Args:
        file_path: Path to the file to check
        no_adhocs: If True, treat EXCLUSIONS_ADHOC as empty (but EXCLUSIONS_OK still apply)

    Returns:
        1 if violations found, 0 otherwise
    """
    global _all_violations, _no_adhocs_mode
    _no_adhocs_mode = no_adhocs

    path = Path(file_path)

    # Only check impl_ files
    if not path.name.startswith("impl_"):
        return 0

    # Skip orchestrator modules - they're allowed to import impl_ modules
    if any(matches_pattern(path.name, pattern) for pattern in EXCLUSIONS_OK):
        return 0

    # Skip ad-hoc modules - they're allowed to import impl_ modules (unless --no-adhocs)
    if not no_adhocs:
        # Convert module names in ADHOCS to file patterns for matching
        for adhoc in EXCLUSIONS_ADHOC:
            if matches_pattern(path.name, f"{adhoc}.py"):
                return 0

    content = path.read_text()

    # Use the original file_path for output to preserve src/udan/ prefix
    display_path = file_path

    # Find all import statements
    # Pattern: from udan.core.impl_X import ... or from udan.core.impl_X.Y import ...
    pattern = r"from udan(?:\.[a-z_]\w+)*\.(impl_[a-zA-Z0-9_]+(?:\.[a-zA-Z0-9_]+)?)\s+import"

    file_violations = []
    for match in re.finditer(pattern, content):
        full_import = match.group(1)
        impl_module = full_import.split(".")[0]

        # Check if it's an allowed exception (valid by design, always allowed)
        if any(matches_pattern(impl_module, pattern.replace(".py", "")) for pattern in EXCLUSIONS_OK):
            continue

        # Check if it's an allowed ad-hoc impl_ import (unless --no-adhocs)
        allowed_adhocs = set() if no_adhocs else EXCLUSIONS_ADHOC
        if impl_module in allowed_adhocs:
            continue

        # Check if it's a self-import (module importing itself)
        stem = path.stem  # e.g., "impl_udan_context" from "impl_udan_context.py"
        if impl_module == stem:
            continue

        # Check if inside TYPE_CHECKING block
        if is_in_type_checking_block(content, match.start()):
            continue

        # Check if inside a function (local import)
        if is_inside_function(content, match.start()):
            continue

        # Get the line number
        line_num = content[: match.start()].count("\n") + 1

        # Collect violation for grouped reporting
        if impl_module not in _all_violations:
            _all_violations[impl_module] = []
        _all_violations[impl_module].append((display_path, line_num, full_import))

        # Also add to file-specific violations
        file_violations.append((display_path, line_num, full_import))

    # Print violations for this file
    if file_violations:
        for display_path, line_num, full_import in file_violations:
            print(
                f"{display_path}:{line_num}: impl_ module depends on other impl_ module: 'from udan.{full_import}'\n"
                f"  → impl_ modules should not depend on other impl_ modules (creates tight coupling)\n"
                f"  → Consider introducing an api_ module with the interface for the imported impl_ class"
            )
        return 1

    return 0


def main() -> int:
    """Main entry point."""
    global _all_violations
    args = sys.argv[1:]
    if not args:
        return 2

    # Check for --no-adhocs flag
    no_adhocs = "--no-adhocs" in args

    # Remove flag from args if present
    file_args = [arg for arg in args if arg != "--no-adhocs"]

    # Track if any file had violations
    exit_code = 0

    # Check each file
    for file_path in file_args:
        result = check_file(file_path, no_adhocs=no_adhocs)
        if result != 0:
            exit_code = result

    # Print grouped summary if there were violations
    if _all_violations:
        print("\n" + "=" * 80)
        print("SUMMARY: impl_ module dependencies (grouped by imported module)")
        print("=" * 80)
        for impl_module in sorted(_all_violations.keys()):
            violations = _all_violations[impl_module]
            importers = set()
            for display_path, line_num, full_import in violations:
                # Extract just the module name from display_path
                importer_module = Path(display_path).stem
                importers.add(importer_module)

            # Convert importer stems to full file paths
            importer_paths = sorted([f"src/udan/core/{imp}.py" for imp in importers])
            print(f"\n### {impl_module} <- {', '.join(importer_paths)}")

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
