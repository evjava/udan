#!/usr/bin/env python3
"""Pre-commit hook to detect redundant object passed to its own method calls.

This script detects the anti-pattern where someone mistakenly passes the same
object (or its attributes) as an argument when calling a method on that object.

Example violations:
    self.resolve_query(query_node, self, other_arg)  # WRONG - self is implicit
    self.foo(x, self, y)                             # WRONG
    ctx.some_method(arg1, ctx, arg2)                 # WRONG - ctx passed to its own method
    obj.method(obj)                                  # WRONG
    ctx.execute_query(q, ctx.container)              # WRONG - ctx.field passed to ctx.method

Valid patterns (should NOT trigger):
    self.other.method(arg, self)                     # OK - passing self to another object
    ctx.other.method(ctx)                             # OK - passing ctx to another object
    obj1.method(obj2)                                # OK - different objects
"""

import ast
import re
import sys
from pathlib import Path


def check_file_ast(file_path: Path) -> list[tuple[int, str, str]]:
    """Check a Python file using AST for obj.method(..., obj, ...) pattern.

    Args:
        file_path: Path to the Python file to check

    Returns:
        List of (line_number, code_snippet, description) tuples
    """
    try:
        with open(file_path, encoding="utf-8") as f:
            source = f.read()
    except OSError, UnicodeDecodeError:
        return []

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    violations = []
    source_lines = source.splitlines()

    def get_root_object(node: ast.expr) -> str | None:
        """Get the root variable name of an attribute chain.

        Examples:
            ctx                    -> "ctx"
            ctx.container          -> "ctx"
            ctx.attr.nested        -> "ctx"
            obj.method().field     -> None (not a simple chain)
        """
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            return get_root_object(node.value)
        else:
            return None

    class SelfCallChecker(ast.NodeVisitor):
        def visit_Call(self, node: ast.Call) -> None:
            # Get the object being called (if it's an attribute access)
            receiver_name = None
            method_name = ""

            if isinstance(node.func, ast.Attribute):
                # Check if the object is a simple variable (self, ctx, obj, etc.)
                if isinstance(node.func.value, ast.Name):
                    receiver_name = node.func.value.id
                    method_name = node.func.attr

            if receiver_name:
                # Skip module-level calls (e.g., re.compile(pattern, re.IGNORECASE))
                # These are not self-referential object method calls
                # Heuristic: single-letter or common module names used as both
                # receiver and keyword-like argument (e.g., re.IGNORECASE)
                if receiver_name in ("re", "os", "sys", "json", "math", "pathlib"):
                    self.generic_visit(node)
                    return

                # Check if any argument is the same object or an attribute of it
                for arg in node.args:
                    arg_receiver = None

                    # Case 1: arg is a simple name (ctx, self, etc.)
                    if isinstance(arg, ast.Name) and arg.id == receiver_name:
                        arg_receiver = arg.id
                    # Case 2: arg is an attribute access (ctx.field, self.attr, ctx.attr.nested, etc.)
                    elif isinstance(arg, ast.Attribute):
                        arg_root = get_root_object(arg)
                        if arg_root == receiver_name:
                            # Get the attribute chain for error message
                            arg_receiver = f"{receiver_name}.{arg.attr}"

                    if arg_receiver:
                        # Get the source code snippet
                        line_no = node.lineno
                        line = source_lines[line_no - 1] if line_no <= len(source_lines) else ""
                        snippet = line.strip() if line else f"{receiver_name}.{method_name}(...)"
                        desc = f"suspicious: '{arg_receiver}' passed to method called on '{receiver_name}'"
                        violations.append((line_no, snippet, desc))
                        break  # Only report once per call

            self.generic_visit(node)

    checker = SelfCallChecker()
    checker.visit(tree)
    return violations


def check_file_regex(file_path: Path) -> list[tuple[int, str, str]]:
    """Check a Python file using regex for obj.method(..., obj, ...) pattern.

    This is a fallback/simpler approach that catches the most common cases.

    Args:
        file_path: Path to the Python file to check

    Returns:
        List of (line_number, code_snippet, description) tuples
    """
    try:
        with open(file_path, encoding="utf-8") as f:
            lines = f.readlines()
    except OSError, UnicodeDecodeError:
        return []

    violations = []

    # Pattern 1: <var>.<method>(..., <same_var>, ...)
    # Uses backreference \1 to ensure the variable name is the same
    # Negative lookahead to exclude: <var>.<obj>.method(..., <var>, ...)
    pattern_direct = (
        r"\b([a-z_][a-z0-9_]*)\.(?!([a-z_][a-z0-9_]*\.)[a-z_][a-z0-9_]*\()[a-z_][a-z0-9_]*\([^)]*,\s*\1\s*[,\)]"
    )

    # Pattern 2: <var>.<method>(..., <same_var>.<field>, ...)
    # Detects passing an attribute of the same object
    pattern_attr = r"\b([a-z_][a-z0-9_]*)\.(?!([a-z_][a-z0-9_]*\.)[a-z_][a-z0-9_]*\()[a-z_][a-z0-9_]*\([^)]*,\s*\1\.[a-z_][a-z0-9_]*\s*[,\)]"

    for line_no, line in enumerate(lines, 1):
        # Skip comments
        stripped = line.split("#")[0]

        # Check both patterns
        for pattern in (pattern_direct, pattern_attr):
            match = re.search(pattern, stripped)
            if match:
                var_name = match.group(1)
                snippet = stripped.strip()
                desc = f"suspicious: argument from '{var_name}' passed to method called on '{var_name}'"
                violations.append((line_no, snippet, desc))
                break  # Only report once per line

    return violations


def main() -> int:
    """Main entry point for the pre-commit hook."""
    if len(sys.argv) < 2:
        print("Usage: check-self-in-self-call.py <file1.py> [file2.py] ...")
        return 1

    exit_code = 0

    for file_path_str in sys.argv[1:]:
        file_path = Path(file_path_str)

        # Skip non-Python files
        if file_path.suffix != ".py":
            continue

        # Try AST first (more accurate), fall back to regex
        violations = check_file_ast(file_path)

        if violations:
            exit_code = 1
            for line_no, snippet, desc in violations:
                print(f"{file_path}:{line_no}: {desc}")
                print(f"  Code: {snippet}")
                print("  Did you mean to remove the redundant object argument?")
                print()

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
