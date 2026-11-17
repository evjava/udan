#!/usr/bin/env python3
"""Check for unused code and dead exports.

This tool finds:
1. Symbols exported in __all__ but never actually used
2. Module-level assignments that are never referenced

Duplicate module-level assignments are checked by a separate hook:
check-duplicate-module-assignments.py
"""

import ast
import re
import sys
from collections import defaultdict
from pathlib import Path


def find_usage_roots(project_dir: Path) -> list[Path]:
    """Find all first-party source roots whose files may use an exported symbol.

    Args:
        project_dir: Project root directory

    Returns:
        src/udan plus every sibling src/udan_plugins_* package: plugins were
        extracted out of src/udan, so a symbol's consumers no longer all live
        in the package that exports it
    """
    src_dir = project_dir / "src"
    roots = [src_dir / "udan"]
    roots.extend(sorted(src_dir.glob("udan_plugins_*")))
    return roots


def find_all_exports_with_locations(src_dir: Path) -> dict[str, tuple[Path, int]]:
    """Find all __all__ exports in the codebase with their locations.

    Args:
        src_dir: Source directory to search

    Returns:
        Dict mapping export name to (filepath, line_number)
    """
    exports_by_name = {}

    for py_file in src_dir.rglob("*.py"):
        # Skip __pycache__ and test directories
        if "__pycache__" in str(py_file) or "test" in str(py_file):
            continue

        try:
            content = py_file.read_text()
            tree = ast.parse(content, filename=str(py_file))
        except Exception:
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "__all__":
                        if isinstance(node.value, (ast.List, ast.Tuple)):
                            for elt in node.value.elts:
                                if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                                    exports_by_name[elt.value] = (py_file, node.lineno)

    return exports_by_name


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
                # Skip assignments that are part of type annotations
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        name = target.id
                        # Skip private variables, dunder methods, and common constants
                        if name.startswith("_") and not name.startswith("__"):
                            continue  # Skip "private" variables
                        if name in ("__all__", "__version__", "__author__"):
                            continue
                        assignments[name].append((py_file, node.lineno, ast.unparse(node)))
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                name = node.target.id
                if name.startswith("_") and not name.startswith("__"):
                    continue
                assignments[name].append((py_file, node.lineno, ast.unparse(node)))

    return assignments


def find_symbol_usage(symbol: str, src_dirs: list[Path], defining_file: Path, check_module_attr: bool = False) -> bool:
    """Check if a symbol is meaningfully used anywhere outside its defining file.

    Args:
        symbol: Symbol name to search for
        src_dirs: Source directories to search
        defining_file: File where the symbol is defined (excluded from search)
        check_module_attr: If True, also check for module.attribute access patterns

    Returns:
        True if symbol is meaningfully used, False otherwise
    """
    for src_dir in src_dirs:
        if find_symbol_usage_in_dir(symbol, src_dir, defining_file, check_module_attr):
            return True

    return False


def find_symbol_usage_in_dir(symbol: str, src_dir: Path, defining_file: Path, check_module_attr: bool) -> bool:
    """Check a single source directory for meaningful usage of a symbol.

    Args:
        symbol: Symbol name to search for
        src_dir: Source directory to search
        defining_file: File where the symbol is defined (excluded from search)
        check_module_attr: If True, also check for module.attribute access patterns

    Returns:
        True if symbol is meaningfully used, False otherwise
    """
    for py_file in src_dir.rglob("*.py"):
        # Skip the defining file and test files
        if py_file == defining_file or "test" in str(py_file) or "__pycache__" in str(py_file):
            continue

        try:
            content = py_file.read_text()
        except Exception:
            continue

        # Check for module-level attribute access patterns
        if check_module_attr:
            # Pattern: from module import symbol, or module.symbol
            if re.search(rf"from .* import .*{symbol}\b", content):
                return True
            # Pattern: module.symbol or module["symbol"]
            module_name = defining_file.stem
            if re.search(rf"\b{module_name}\.{symbol}\b", content):
                return True
            # Pattern: getattr(module, "symbol")
            if re.search(rf'getattr\(.*,\s*["\']{symbol}["\']\)', content):
                return True

        # Check for meaningful usage patterns:
        # 1. Instantiation: symbol()
        # 2. Attribute access: obj.symbol or x = symbol.attr
        # 3. Type annotation: func(...) -> symbol or x: symbol
        # 4. Inheritance: class MyClass(symbol):
        # 5. Function calls: func(symbol, ...)
        # 6. Isinstance checks: isinstance(x, symbol)

        # Skip if only in import statements or __all__
        lines = content.split("\n")

        # Check if symbol is imported only to be re-exported
        import_lines = []
        all_line = None
        for i, line in enumerate(lines):
            if f"import {symbol}" in line or f"as {symbol}" in line:
                import_lines.append(i)
            if "__all__" in line and symbol in line:
                all_line = i

        # If symbol is only in imports and __all__, it's just being re-exported
        if import_lines and all_line is not None:
            # Check if there's any actual usage outside of imports/__all__
            has_real_usage = False
            for i, line in enumerate(lines):
                if i in import_lines or i == all_line:
                    continue
                if symbol in line:
                    # Found usage outside imports/__all__
                    # Verify it's not a comment
                    stripped = line.strip()
                    if not stripped.startswith("#"):
                        # Check for actual usage patterns
                        if re.search(rf"\b{symbol}\s*\(", line):  # Instantiation
                            has_real_usage = True
                        elif re.search(rf":\s*{symbol}\b", line):  # Type annotation
                            has_real_usage = True
                        elif re.search(rf"\bclass\s+\w+\s*\(\s*{symbol}\s*\)", line):  # Inheritance
                            has_real_usage = True
                        elif re.search(rf"isinstance\s*\([^,]+,\s*{symbol}\s*\)", line):  # Isinstance
                            has_real_usage = True
                        elif re.search(rf"\b{symbol}\s*\.", line):  # Attribute access
                            has_real_usage = True

            if not has_real_usage:
                continue  # Only re-exported, not actually used

        # More thorough check using AST
        try:
            tree = ast.parse(content, filename=str(py_file))
        except Exception:
            # Fallback to regex search
            if re.search(rf"\b{symbol}\s*\(", content):  # instantiation
                return True
            if re.search(rf":\s*{symbol}\b", content):  # type annotation
                return True
            if re.search(rf"class\s+\w+\s*\(\s*{symbol}\s*\)", content):  # inheritance
                return True
            if re.search(rf"isinstance\s*\([^,]+,\s*{symbol}\s*\)", content):  # isinstance
                return True
            continue

        # Check AST for meaningful usage
        for node in ast.walk(tree):
            # Type annotations
            if isinstance(node, ast.AnnAssign):
                if isinstance(node.annotation, ast.Name) and node.annotation.id == symbol:
                    return True
            # Function return type
            elif isinstance(node, ast.FunctionDef):
                if isinstance(node.returns, ast.Name) and node.returns.id == symbol:
                    return True
            # Base classes
            elif isinstance(node, ast.ClassDef):
                for base in node.bases:
                    if isinstance(base, ast.Name) and base.id == symbol:
                        return True
            # Attribute access (symbol.method or obj.symbol)
            elif isinstance(node, ast.Attribute):
                if node.attr == symbol:
                    return True
            # Isinstance/issubclass calls and function calls (symbol())
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    if node.func.id in ("isinstance", "issubclass"):
                        if len(node.args) > 1 and isinstance(node.args[1], ast.Name):
                            if node.args[1].id == symbol:
                                return True
                    elif node.func.id == symbol:
                        # Direct function call: symbol()
                        return True

    return False


def main() -> int:
    """Check for unused exports and module-level assignments."""
    project_dir = Path.cwd()
    src_dir = project_dir / "src/udan"

    if not src_dir.exists():
        print(f"Source directory not found: {src_dir}")
        return 1

    src_dirs = find_usage_roots(project_dir)

    found_issues = False

    # Check 1: Unused exports in __all__
    print("=" * 70)
    print("CHECK 1: Unused exports in __all__ lists")
    print("=" * 70)

    exports = find_all_exports_with_locations(src_dir)
    unused_exports = []

    for symbol, (filepath, lineno) in exports.items():
        # Skip private symbols
        if symbol.startswith("_"):
            continue

        if not find_symbol_usage(symbol, src_dirs, filepath):
            unused_exports.append((symbol, filepath, lineno))

    if unused_exports:
        found_issues = True
        print("Unused exports found in __all__:")
        for symbol, filepath, lineno in sorted(unused_exports, key=lambda x: (str(x[1]), x[2])):
            try:
                rel_path = filepath.relative_to(project_dir)
            except ValueError:
                rel_path = filepath
            print(f"  {rel_path}:{lineno}: {symbol}")
    else:
        print("✓ No unused exports found.")

    # Check 2: Unused module-level assignments (only specific aliases, not type aliases)
    print("\n" + "=" * 70)
    print("CHECK 2: Unused module-level assignments (backward compatibility aliases)")
    print("=" * 70)

    assignments = find_module_level_assignments(src_dir)

    unused_assignments = []

    for name, locations in assignments.items():
        # Skip if already marked as duplicate
        if len(locations) > 1:
            continue

        filepath, lineno, assignment = locations[0]

        # Skip type aliases (names ending in 'Fn', 'Type', or all-caps constants)
        if name.endswith("Fn") or name.endswith("Type") or name.isupper() or name.isupper():
            continue
        # Skip common API types
        if name in ("AttributeValue", "Operator", "OperatorDescriptor"):
            continue

        # Only check for backward compatibility aliases (pattern: name = _name_impl)
        if not name.startswith("_") and "_impl" in assignment:
            # Check if this assignment is used anywhere
            if not find_symbol_usage(name, src_dirs, filepath, check_module_attr=True):
                unused_assignments.append((name, filepath, lineno, assignment))

    if unused_assignments:
        found_issues = True
        print("Unused backward compatibility aliases found:")
        for name, filepath, lineno, assignment in sorted(unused_assignments, key=lambda x: x[0]):
            try:
                rel_path = filepath.relative_to(project_dir)
            except ValueError:
                rel_path = filepath
            print(f"  {rel_path}:{lineno}: {assignment}")
    else:
        print("✓ No unused backward compatibility aliases found.")

    # Summary
    print("\n" + "=" * 70)
    if found_issues:
        print("✗ Found dead code issues!")
        return 1
    else:
        print("✓ All checks passed!")
        return 0


if __name__ == "__main__":
    sys.exit(main())
