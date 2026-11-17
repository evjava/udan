#!/usr/bin/env python3
"""Pre-commit hook to check encapsulation violations.

This hook detects:
1. Direct access to protected attributes: `something._field` (except when `something` is `self`)
2. getattr with protected attributes: `getattr(something, '_private')`

Usage:
    check-encapsulation-violations.py <file> [<file> ...]
"""

import argparse
import ast
import sys
from pathlib import Path

# Attributes that are allowed to be accessed in specific files
# Maps filename to set of allowed attributes
EXCLUSIONS_ADHOC: dict[str, set[str]] = {
    "api_annotated.py": {
        "_annotated",
        "_annotated_kwargs",
        "_dependency",
        "_dependency_plugins_only",
    },
    "impl_function_injector.py": {
        "_annotated_kwargs",  # For copying metadata to wrapped functions
        "_injector_wrapped",  # wrapping marker: set here, probed via _INJECTOR_WRAPPED
    },
}


class EncapsulationViolationChecker(ast.NodeVisitor):
    """AST visitor that checks for encapsulation violations."""

    def __init__(self, filename: str):
        self.filename = filename
        self.violations: list[tuple[int, int, str]] = []
        self.in_class_def = False
        self.current_class: str | None = None

    def _is_allowed(self, attr: str) -> bool:
        """Check if an attribute access is allowed based on file-specific rules.

        Args:
            attr: The attribute name being accessed

        Returns:
            True if access is allowed, False otherwise
        """
        # Check file-specific allowed attributes
        for fname, allowed_attrs in EXCLUSIONS_ADHOC.items():
            if fname in self.filename and attr in allowed_attrs:
                return True

        return False

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Track when we're inside a class definition."""
        outer_class = self.current_class
        self.in_class_def = True
        self.current_class = node.name
        self.generic_visit(node)
        self.current_class = outer_class
        if self.current_class is None:
            self.in_class_def = False

    def visit_Attribute(self, node: ast.Attribute) -> None:
        """Check for direct access to protected attributes.

        Flags `something._field` except when `something` is `self` or `cls`.
        Excludes dunder attributes (like __name__, __init__, etc.) which are
        special Python attributes commonly accessed publicly.
        """
        # Skip dunder attributes (start and end with __)
        if node.attr.startswith("__") and node.attr.endswith("__"):
            self.generic_visit(node)
            return

        if node.attr.startswith("_"):
            # Check if this is self._field or cls._field (allowed)
            value_is_self_or_cls = isinstance(node.value, ast.Name) and node.value.id in ("self", "cls")

            # Method calls like self.get_other()._private are ALWAYS violations
            # because the protected attribute is accessed on the returned object,
            # not on self/cls themselves.

            # Check if this access is allowed (file-specific)
            if self._is_allowed(node.attr):
                self.generic_visit(node)
                return

            # Flag violation if not accessing via self or cls directly
            if not value_is_self_or_cls:
                line_msg = f"Protected attribute '{node.attr}' accessed through object reference"
                self.violations.append((node.lineno, node.col_offset, line_msg))

        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        """Check for getattr with protected attributes.

        Flags `getattr(something, '_private')` patterns.
        Excludes dunder attributes (like __name__, __init__, etc.) which are
        special Python attributes commonly accessed publicly.
        """
        if isinstance(node.func, ast.Name) and node.func.id == "getattr":
            # getattr(obj, 'attr', default) or getattr(obj, 'attr')
            if len(node.args) >= 2:
                second_arg = node.args[1]

                # Check if the attribute name is protected/internal
                attr_name = None
                if isinstance(second_arg, ast.Constant):
                    attr_name = second_arg.value

                if attr_name and isinstance(attr_name, str):
                    # Check if this is allowed (file-specific)
                    if self._is_allowed(attr_name):
                        self.generic_visit(node)
                        return

                    # Check if this is a known internal/protected attribute
                    is_protected = False

                    # Attributes starting with underscore (except dunder)
                    if attr_name.startswith("_") and not (attr_name.startswith("__") and attr_name.endswith("__")):
                        is_protected = True

                    # Known internal attributes that don't follow underscore convention
                    # but are still implementation details
                    known_internal_attrs = {
                        "attribute_storage",  # Should use _get_storage() or public API instead
                        "_storage",  # Private attribute
                    }
                    if attr_name in known_internal_attrs:
                        is_protected = True

                    if is_protected:
                        line_msg = f"Protected/internal attribute '{attr_name}' accessed via getattr"
                        self.violations.append((node.lineno, node.col_offset, line_msg))

        self.generic_visit(node)


def check_file(filepath: Path) -> list[tuple[int, int, str]]:
    """Check a single file for encapsulation violations.

    Returns:
        List of (line, column, message) tuples for violations found
    """
    try:
        content = filepath.read_text(encoding="utf-8")
    except OSError, UnicodeDecodeError:
        return []

    try:
        tree = ast.parse(content, filename=str(filepath))
    except SyntaxError:
        # Skip files with syntax errors (will be caught by other hooks)
        return []

    checker = EncapsulationViolationChecker(str(filepath))
    checker.visit(tree)

    return checker.violations


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Check for encapsulation violations")
    parser.add_argument("files", nargs="+", type=Path, help="Files to check")
    args = parser.parse_args()

    exit_code = 0

    for filepath in args.files:
        if not filepath.is_file():
            continue

        # Skip test files (they often need to access protected attributes)
        # But don't skip files in /tmp which are used for testing the hook itself
        abs_path = str(filepath.resolve())
        if ("tests" in filepath.parts or filepath.name.startswith("test_")) and not abs_path.startswith("/tmp/"):
            continue

        violations = check_file(filepath)

        if violations:
            exit_code = 1
            for line, col, msg in violations:
                print(f"{filepath}:{line}:{col}: {msg}")

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
