#!/usr/bin/env python3
"""Pre-commit hook to forbid suppressing ARG (unused argument) violations.

This hook enforces that unused arguments should be removed rather than
suppressed with:
1. # noqa: ARG comments
2. Underscore-prefixed parameter names (e.g., def foo(_x))
"""

import ast
import re
import subprocess
import sys
from pathlib import Path


def check_file_for_arg_noqa(file_path: Path) -> list[tuple[int, str]]:
    """Check a file for ARG suppression comments.

    Args:
        file_path: Path to the file to check

    Returns:
        List of (line_number, line) tuples where ARG suppression is found
    """
    violations = []

    try:
        with open(file_path, encoding="utf-8") as f:
            lines = f.readlines()
    except OSError, UnicodeDecodeError:
        return violations

    # Pattern to match noqa for ARG rules
    # Matches: # noqa: ARG, # noqa: ARG001, # noqa: ARG001, ARG002, etc.
    arg_noqa_pattern = re.compile(r"# noqa:? .*ARG\d*")

    for line_no, line in enumerate(lines, start=1):
        if arg_noqa_pattern.search(line):
            violations.append((line_no, line.rstrip()))

    return violations


def check_file_for_underscore_params(file_path: Path) -> list[tuple[int, str, str]]:
    """Check a file for underscore-prefixed parameters in function signatures.

    Args:
        file_path: Path to the file to check

    Returns:
        List of (line_number, param_name, line) tuples where underscore params are found
    """
    violations = []

    try:
        source = Path(file_path).read_text(encoding="utf-8")
    except OSError, UnicodeDecodeError:
        return violations

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return violations

    class UnderscoreParamChecker(ast.NodeVisitor):
        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            self._check_params(node)
            self.generic_visit(node)

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            self._check_params(node)
            self.generic_visit(node)

        def _check_params(self, node) -> None:
            # Check all arguments except 'self' and 'cls'
            for arg in node.args.args:
                if arg.arg.startswith("_") and arg.arg not in ("_", "__class__"):
                    violations.append((node.lineno, arg.arg, f"def {node.name}("))

            # Check *args
            if node.args.vararg and node.args.vararg.arg.startswith("_"):
                violations.append((node.lineno, node.args.vararg.arg, f"def {node.name}("))

            # Check **kwargs
            if node.args.kwarg and node.args.kwarg.arg.startswith("_"):
                violations.append((node.lineno, node.args.kwarg.arg, f"def {node.name}("))

    UnderscoreParamChecker().visit(tree)
    return violations


def main() -> None:
    """Run the pre-commit hook."""
    # Get files to check from command line or use git to find staged Python files
    if len(sys.argv) > 1:
        # When files are passed as arguments, check them all
        files = [Path(f) for f in sys.argv[1:]]
    else:
        # When run from pre-commit, only check src/ files
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
            capture_output=True,
            text=True,
        )
        files = [Path(f) for f in result.stdout.splitlines() if f.endswith(".py")]
        # Only check files in src/ when running from git
        files = [f for f in files if f.is_file() and str(f).startswith("src/")]

    all_violations = []

    for file_path in files:
        # Check for ARG noqa comments
        for line_no, line in check_file_for_arg_noqa(file_path):
            all_violations.append((file_path, line_no, line, "noqa"))

        # Check for underscore-prefixed parameters
        for line_no, param_name, line in check_file_for_underscore_params(file_path):
            all_violations.append((file_path, line_no, f"Parameter '{param_name}' in {line}", "underscore"))

    if all_violations:
        print("ARG suppression is forbidden. Remove unused arguments instead.", file=sys.stderr)
        print("", file=sys.stderr)
        for file_path, line_no, message, kind in all_violations:
            print(f"{file_path}:{line_no}: {message}", file=sys.stderr)
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
