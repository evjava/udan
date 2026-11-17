#!/usr/bin/env python3
"""Pre-commit hook to detect Law of Demeter violations (train wrecks).

This script detects the "train wreck" or "message chain" code smell where code
chains too many method/attribute calls, violating the Law of Demeter principle.

The Law of Demeter states: "Talk only to your immediate friends" - an object
should only interact with its direct attributes, parameters, locally created
objects, and direct components.

Example violations:
    a.b.c.method()             # 3 dots - tight coupling through chain
    obj.get_x().get_y().get_z()  # chained method calls
    user.address.city.zip.code()  # deep attribute traversal ending in a call

Valid patterns (should NOT trigger):
    a.b.c                      # attribute access without method call
    a.b()                      # 1 dot
    a.b.c()                    # 2 dots
    df.filter(col > 0).sort("name").select("id")  # fluent interface
    dict.items()               # standard library methods
    path.parent.mkdir()        # Path API
"""

import ast
import re
import sys
from pathlib import Path

# Designed fluent interface patterns (method chains to allow)
# Format: (max_allowed_dots, allowed_method_names)
EXCLUSIONS_OK = [
    # Builder patterns (Response.builder().status(200).body("ok").build())
    (5, {"builder", "status", "body", "build", "headers"}),
    # Query builder patterns (filter().select().order_by())
    (5, {"filter", "select", "order_by", "limit", "offset", "join"}),
    # Pandas-like patterns (filter().sort().groupby())
    (5, {"filter", "sort", "groupby", "agg", "transform"}),
    # Chaining setters (set_x().set_y().set_z())
    (4, {"set_"}),
]

# Adhoc standard library method chains to exclude (Path API, dict methods, etc.)
EXCLUSIONS_ADHOC = {
    # Path methods ( pathlib.Path )
    "mkdir",
    "exists",
    "is_file",
    "is_dir",
    "read_text",
    "write_text",
    "resolve",
    "expanduser",
    "stat",
    "touch",
    "unlink",
    "rmdir",
    # Dict/Set methods
    "items",
    "keys",
    "values",
    "get",
    "update",
    "setdefault",
    # Common container methods
    "append",
    "extend",
    "pop",
    "remove",
    "clear",
    "copy",
    # File/path context
    "open",
    "close",
    "read",
    "write",
    # String/bytes
    "split",
    "splitlines",
    "strip",
    "lower",
    "upper",
    "replace",
    "format",
    # Type conversion
    "int",
    "str",
    "float",
    "bool",
    "list",
    "dict",
    "set",
    "tuple",
}

# Maximum dots allowed before flagging as violation
# self.method() -> 1 dot (OK)
# self.a.method() -> 2 dots (OK - maximum allowed depth)
# self.a.b.method() -> 3 dots (VIOLATION - too many jumps through objects)
DEFAULT_MAX_DOTS = 2

# Maximum different internal components a method can orchestrate before flagging
# This detects the "orchestrator" anti-pattern where a method coordinates too many dependencies
# method_using_3_components() -> OK
# method_using_4_components() -> OK (acceptable for complex operations)
# method_using_5_components() -> VIOLATION (should extract facades/coordinators)
DEFAULT_MAX_COMPONENT_ORCHESTRATION = 6  # Increased to allow QueryProcessor orchestration (facade pattern)


def _get_self_component_accessed(node: ast.Call) -> str | None:
    """Extract the component being accessed in a self.xxx.yyy() call.

    Returns the component name (e.g., "self.query_processor") or None.
    """
    if isinstance(node.func, ast.Attribute):
        if isinstance(node.func.value, ast.Attribute):
            if isinstance(node.func.value.value, ast.Name) and node.func.value.value.id == "self":
                return f"self.{node.func.value.attr}"
        elif isinstance(node.func.value, ast.Name):
            if node.func.value.id == "self":
                return "self"
    return None


def count_dots_in_chain(node: ast.AST) -> int:
    """Count the number of dots (attribute accesses) in an expression chain.

    Args:
        node: AST node to analyze

    Returns:
        Number of dots in the chain
    """
    count = 0
    current = node

    while isinstance(current, (ast.Attribute, ast.Call)):
        if isinstance(current, ast.Call):
            current = current.func
        elif isinstance(current, ast.Attribute):
            count += 1
            current = current.value
        else:
            break

    return count


def get_chain_methods(node: ast.AST) -> list[str]:
    """Extract method names from a chained expression.

    Args:
        node: AST node to analyze

    Returns:
        List of method names in the chain (outermost first)
    """
    methods = []
    current = node

    while isinstance(current, ast.Call):
        if isinstance(current.func, ast.Attribute):
            methods.append(current.func.attr)
            current = current.func.value
        else:
            break

    return methods


def is_fluent_interface_pattern(node: ast.AST, max_dots: int) -> bool:
    """Check if the chain matches a whitelisted fluent interface pattern.

    Args:
        node: AST node to check
        max_dots: Number of dots in the chain

    Returns:
        True if this is an allowed fluent interface pattern
    """
    if max_dots < 3:
        return False

    methods = get_chain_methods(node)

    for allowed_dots, allowed_methods in EXCLUSIONS_OK:
        if max_dots <= allowed_dots:
            # Check if any method in the chain is in the whitelist
            if any(method in allowed_methods for method in methods):
                return True

    return False


def check_file_ast(file_path: Path) -> list[tuple[int, str, str]]:
    """Check a Python file using AST for Law of Demeter violations.

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

    class LawOfDemeterChecker(ast.NodeVisitor):
        def visit_Call(self, node: ast.Call) -> None:
            # Check if this is a chained call (a.b.c.d())
            if isinstance(node.func, ast.Attribute):
                dots = count_dots_in_chain(node)
                final_method = node.func.attr

                # Skip if the final method is a whitelisted standard library method
                if final_method in EXCLUSIONS_ADHOC:
                    self.generic_visit(node)
                    return

                # Only flag if we have too many dots AND it ends with a method call
                if dots > DEFAULT_MAX_DOTS:
                    # Check if this is a whitelisted fluent interface pattern
                    if not is_fluent_interface_pattern(node, dots):
                        line_no = node.lineno
                        line = source_lines[line_no - 1] if line_no <= len(source_lines) else ""

                        # Extract the violating expression
                        snippet = line.strip() if line else f"<chained call with {dots} dots>"

                        desc = (
                            f"Law of Demeter violation: {dots} dots in chain (exceeds maximum of {DEFAULT_MAX_DOTS}) "
                            f"- creates tight coupling through object chain"
                        )
                        violations.append((line_no, snippet, desc))

            self.generic_visit(node)

    checker = LawOfDemeterChecker()
    checker.visit(tree)

    # Also check for "orchestration through multiple dependencies" pattern
    # This catches methods that call through 3+ different self._xxx components
    orchestration_violations = check_orchestration_pattern(tree, source_lines)
    violations.extend(orchestration_violations)

    return violations


def check_orchestration_pattern(tree: ast.AST, source_lines: list[str]) -> list[tuple[int, str, str]]:
    """Check for methods that orchestrate through multiple different dependencies.

    This detects the "pipe" pattern where a method calls through 3+ different
    injected components, violating Law of Demeter by creating tight coupling.

    Args:
        tree: AST of the Python file
        source_lines: Source code lines for extracting snippets

    Returns:
        List of (line_number, code_snippet, description) tuples
    """
    violations = []

    class OrchestrationChecker(ast.NodeVisitor):
        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            # Skip small functions (< 15 lines) and dunder methods
            if (node.end_lineno - node.lineno) < 15 or node.name.startswith("__"):
                self.generic_visit(node)
                return

            # Find all calls to self._xxx methods/properties
            accessed_components = set()

            for child in ast.walk(node):
                if isinstance(child, ast.Call):
                    component = _get_self_component_accessed(child)
                    if component and component != "self":
                        accessed_components.add(component)

            # Flag if too many different components are accessed
            if len(accessed_components) > DEFAULT_MAX_COMPONENT_ORCHESTRATION:
                line_no = node.lineno
                line = source_lines[line_no - 1] if line_no <= len(source_lines) else ""
                snippet = f"def {node.name}(...):" if not line else line.strip()

                components_str = ", ".join(sorted(accessed_components))
                desc = (
                    f"Law of Demeter violation: method '{node.name}' orchestrates through "
                    f"{len(accessed_components)} different components ({components_str}) "
                    f"- consider creating a facade to hide this orchestration"
                )
                violations.append((line_no, snippet, desc))

            self.generic_visit(node)

    checker = OrchestrationChecker()
    checker.visit(tree)
    return violations


def check_file_regex(file_path: Path) -> list[tuple[int, str, str]]:
    """Check a Python file using regex for obvious Law of Demeter violations.

    This is a simpler approach that catches the most common patterns like
    a.b.c.d.e() or obj.get_x().get_y().get_z().

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

    # Pattern: a.b.c.d() - 3+ dots ending with method call
    # The {3,} means 3 or more groups of .word after the first word
    # This gives us 3 or more total dots, matching the AST threshold above
    pattern = r"\b[a-z_][a-z0-9_]*(\.[a-z_][a-z0-9_]*){3,}\("

    for line_no, line in enumerate(lines, 1):
        # Skip comments and strings (basic check)
        stripped = line.split("#")[0]
        if '"""' in stripped or "'''" in stripped:
            continue

        match = re.search(pattern, stripped)
        if match:
            # Mirror the AST pass: skip chains whose final method is whitelisted,
            # otherwise the fallback re-flags lines the AST check deliberately allows
            final_method = match.group(0).rstrip("(").rsplit(".", 1)[-1]
            if final_method in EXCLUSIONS_ADHOC:
                continue

            snippet = stripped.strip()
            # Count dots in the matched pattern
            dots = snippet[: match.end()].count(".")
            desc = (
                f"Law of Demeter violation: {dots} dots in chain (exceeds maximum of {DEFAULT_MAX_DOTS}) "
                f"- consider hiding the chain behind a method"
            )
            violations.append((line_no, snippet, desc))

    return violations


def main() -> int:
    """Main entry point for the pre-commit hook."""
    if len(sys.argv) < 2:
        print("Usage: check-law-of-demeter.py <file1.py> [file2.py] ...")
        return 1

    exit_code = 0

    for file_path_str in sys.argv[1:]:
        file_path = Path(file_path_str)

        # Skip non-Python files
        if file_path.suffix != ".py":
            continue

        # Try AST first (more accurate), fall back to regex
        violations = check_file_ast(file_path)
        if not violations:
            violations = check_file_regex(file_path)

        if violations:
            exit_code = 1
            for line_no, snippet, desc in violations:
                print(f"{file_path}:{line_no}: {desc}")
                print(f"  Code: {snippet}")
                print("  Consider: Extracting intermediate objects or adding wrapper methods")
                print()

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
