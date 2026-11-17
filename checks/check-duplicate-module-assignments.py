#!/usr/bin/env python3
"""Pre-commit hook to check for duplicate module-level assignments.

Duplicate assignments within a single file are always flagged. For different
files, only identical assignment values are flagged (each module may
legitimately define its own constant with the same name).

Excluded patterns (intentionally per-module, naturally repeat across files):
- logger = logging.getLogger(__name__)

Values are compared via ast.unparse, so the exclusion matches regardless
of formatting.
"""

import ast
import sys
from collections import defaultdict
from pathlib import Path

# Assignment values (in ast.unparse form) that are per-module by design
EXCLUDED_VALUES = {"logging.getLogger(__name__)"}


def find_module_level_assignments(src_dir: Path) -> dict[str, list[tuple[Path, int, str]]]:
    """Find all module-level assignments (not inside functions/classes).

    Args:
        src_dir: Source directory to search

    Returns:
        Dict mapping variable name to list of (filepath, line_number, assignment_str)
    """
    assignments = defaultdict(list)

    for py_file in src_dir.rglob("*.py"):
        # Skip __pycache__, test directories, and api_ files (API definitions)
        if "__pycache__" in str(py_file) or "test" in str(py_file):
            continue
        if "api_" in py_file.name:
            continue  # Skip API definition files

        try:
            content = py_file.read_text()
            tree = ast.parse(content, filename=str(py_file))
        except Exception:
            continue

        # Find module-level assignments (top-level, not in function/class)
        for node in tree.body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        name = target.id
                        # Skip private variables, dunder methods, and common constants
                        if name.startswith("_") and not name.startswith("__"):
                            continue  # Skip "private" variables
                        if name in ("__all__", "__version__", "__author__"):
                            continue
                        if ast.unparse(node.value) in EXCLUDED_VALUES:
                            continue  # Skip per-module patterns like loggers
                        assignments[name].append((py_file, node.lineno, ast.unparse(node)))
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                name = node.target.id
                if name.startswith("_") and not name.startswith("__"):
                    continue
                if node.value is not None and ast.unparse(node.value) in EXCLUDED_VALUES:
                    continue
                assignments[name].append((py_file, node.lineno, ast.unparse(node)))

    return assignments


def main() -> int:
    """Check for duplicate module-level assignments."""
    project_dir = Path.cwd()
    src_dir = project_dir / "src/udan"

    if not src_dir.exists():
        print(f"Source directory not found: {src_dir}")
        return 1

    assignments = find_module_level_assignments(src_dir)
    duplicates = []

    for name, locations in assignments.items():
        if len(locations) > 1:
            # Check if they're in the same file
            files = set(loc[0] for loc in locations)
            if len(files) == 1:
                # Same file, different lines - definitely duplicate
                duplicates.append((name, locations))
            else:
                # Different files - might be intentional (each module has its own)
                # Only flag if they have the same assignment value
                values = set(loc[2] for loc in locations)
                if len(values) == 1:
                    duplicates.append((name, locations))

    if duplicates:
        print("Duplicate module-level assignments found:")
        for name, locations in sorted(duplicates, key=lambda x: x[0]):
            print(f"\n  {name}:")
            for filepath, lineno, assignment in locations:
                try:
                    rel_path = filepath.relative_to(project_dir)
                except ValueError:
                    rel_path = filepath
                print(f"    {rel_path}:{lineno}: {assignment}")
        return 1

    print("No duplicate module-level assignments found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
