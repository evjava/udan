#!/usr/bin/env python3
"""Pre-commit hook to detect @property usage in API classes.

API classes (ending in 'API') in api_*.py files should be pure abstract interfaces.
Properties hide implementation details and break the clean contract.

This hook scans all src/udan/core/api_*.py files, finds *API classes
with @property decorators, and reports any that are not in the exclusion list.

The exclusion list exists so that existing properties can be incrementally refactored.
New properties should NOT be added to the exclusion list.
"""

import ast
import sys
from pathlib import Path

# Properties currently allowed (to be refactored later).
# Format: ('module.ClassName', 'property_name')
EXCLUSIONS_ADHOC: set[tuple[str, str]] = {
    ("udan.core.api_exec_context.ExecContextAPI", "symbols_env"),
    ("udan.core.api_udan_context.UdanContextAPI", "registry"),
}


def find_api_properties(src_dir: Path) -> list[tuple[str, str, str, int]]:
    """Find all @property decorators in API classes.

    Returns:
        List of (fqn, property_name, file_path, line_number) tuples.
    """
    results = []
    api_files = sorted(src_dir.glob("api*.py")) + sorted(src_dir.glob("api_*.py"))

    for fpath in api_files:
        module = f"udan.core.{fpath.stem}"
        source = fpath.read_text()
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef) or not node.name.endswith("API"):
                continue
            fqn = f"{module}.{node.name}"
            for item in node.body:
                if not isinstance(item, ast.FunctionDef):
                    continue
                for dec in item.decorator_list:
                    if isinstance(dec, ast.Name) and dec.id == "property":
                        results.append((fqn, item.name, str(fpath), item.lineno))

    return results


def main() -> int:
    src_dir = Path("src/udan/core")
    if not src_dir.exists():
        print(f"Error: {src_dir} not found", file=sys.stderr)
        return 1

    properties = find_api_properties(src_dir)
    violations = []

    for fqn, prop_name, fpath, lineno in properties:
        if (fqn, prop_name) not in EXCLUSIONS_ADHOC:
            violations.append((fqn, prop_name, fpath, lineno))

    if violations:
        for fqn, prop_name, fpath, lineno in violations:
            print(f"{fpath}:{lineno}: {fqn}.{prop_name} uses @property in API class")
            print("  Add to EXCLUSIONS_ADHOC if this is pre-existing, otherwise refactor to a method.")
        print(f"\n{len(violations)} violation(s) found.")
        return 1

    # Show exclusion list status
    exclusion_found = {(fqn, prop) for fqn, prop, _, _ in properties} & EXCLUSIONS_ADHOC
    unused = EXCLUSIONS_ADHOC - exclusion_found
    if unused:
        print("Warning: stale exclusions (no matching property found):")
        for fqn, prop in sorted(unused):
            print(f"  ('{fqn}', '{prop}')")
        return 1

    print(f"OK: {len(properties)} @property in API classes, all in exclusion list.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
