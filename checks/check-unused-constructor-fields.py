#!/usr/bin/env python3
"""Pre-commit hook to report private instance fields assigned but never read.

A private field that is written and never read is dead weight plus a lie about
the class's collaborators:

    self._registry = registry        # BAD  - written by DescriptorFactory, never read
    self._symbols_env = symbols_env  # GOOD - read by the class's own methods

Why not pylint's `unused-private-member` (W0238)? That check defines "private"
as name-mangled (`__name`, at least two leading underscores - see
`pylint.checkers.utils.is_attr_private`). The codebase convention is the
single-underscore `_name` form, which pylint classifies as *protected* and
excludes from the check entirely, so W0238 is silent on exactly the fields this
hook targets.

Why match on (class, attribute) rather than the bare attribute name? Common
names recur across the codebase - `self._registry` is read in RenderEngine,
OperatorsEngine and UdanContext, all unrelated to DescriptorFactory's dead
`self._registry`. Comparing the bare name would let those unrelated reads mask
the dead field, so usage is resolved per class instead.

Only `self._x` reads inside the field's own class count as a use. A field
read only from outside the class is still reported; given that
check-encapsulation-violations already bans protected access across class
boundaries, that case should be rare and can be listed in EXCLUSIONS_ADHOC.

Violations print in the same `file:lineno:content` format used by
EXCLUSIONS_ADHOC in the other hooks, so a legitimate exception can be copied
straight into the set below.
"""

import ast
import subprocess
import sys
from pathlib import Path

# fmt: off
# ruff: noqa: E501
EXCLUSIONS_ADHOC: set[str] = {
    # <copy a reported `file:lineno:content` line here to suppress it>
    # UdanContext holds the container's TypesRegistry for external readers (tests reach
    # into ctx._types_registry); it has no in-class read, so this hook cannot see that use.
    "src/udan/core/impl_udan_context.py:98:        self._types_registry = types_registry",
    # DummyChainContext keeps the query ctx so the store-only context carries the
    # ChainContextAPI.ctx member its contract declares (the computing context reads
    # its own); the store-only one never reads it in-class.
    "src/udan/core/impl_chain_context.py:45:        self._ctx = ctx",
}
# fmt: on


def _iter_self_assignments(init: ast.FunctionDef) -> list[tuple[str, ast.Attribute]]:
    """Collect every `self.<name> = ...` / `self.<name>: T = ...` inside __init__.

    Args:
        init: The __init__ FunctionDef to scan.

    Returns:
        List of (attribute_name, attribute_node) pairs, in source order.
    """
    found: list[tuple[str, ast.Attribute]] = []
    for node in ast.walk(init):
        targets: list[ast.expr] = []
        if isinstance(node, ast.Assign):
            targets = list(node.targets)
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
        for target in targets:
            if not isinstance(target, ast.Attribute):
                continue
            receiver = target.value
            if isinstance(receiver, ast.Name) and receiver.id == "self":
                found.append((target.attr, target))
    return found


def _collect_self_reads(class_def: ast.ClassDef) -> set[str]:
    """Collect attribute names read as `self.<name>` anywhere inside a class.

    Args:
        class_def: The ClassDef whose methods to scan.

    Returns:
        Set of attribute names accessed through `self` in a non-Store context.
    """
    read: set[str] = set()
    for node in ast.walk(class_def):
        if not isinstance(node, ast.Attribute) or isinstance(node.ctx, ast.Store):
            continue
        receiver = node.value
        if isinstance(receiver, ast.Name) and receiver.id == "self":
            read.add(node.attr)
    return read


def check_file(file_path: str) -> list[tuple[int, str, str]]:
    """Check a Python file for private fields written in __init__ but never read.

    Args:
        file_path: Path to the Python file to inspect.

    Returns:
        List of (line_number, attribute_name, stripped_line) tuples.
    """
    try:
        source = Path(file_path).read_text(encoding="utf-8")
    except OSError, UnicodeDecodeError:
        return []

    try:
        tree = ast.parse(source, filename=file_path)
    except SyntaxError:
        return []

    lines = source.splitlines()
    violations: list[tuple[int, str, str]] = []

    for class_def in ast.walk(tree):
        if not isinstance(class_def, ast.ClassDef):
            continue
        inits = [n for n in class_def.body if isinstance(n, ast.FunctionDef) and n.name == "__init__"]
        if not inits:
            continue

        written: dict[str, ast.Attribute] = {}
        for init in inits:
            for name, node in _iter_self_assignments(init):
                written.setdefault(name, node)

        read = _collect_self_reads(class_def)

        for name, node in sorted(written.items(), key=lambda item: item[1].lineno):
            if not name.startswith("_"):
                continue  # public fields are fair game for external readers
            if name in read:
                continue
            line = lines[node.lineno - 1].rstrip() if node.lineno <= len(lines) else ""
            violations.append((node.lineno, name, line))

    return sorted(set(violations))


def discover_files() -> list[str]:
    """List git-tracked Python files under src/."""
    result = subprocess.run(["git", "ls-files", "src/"], capture_output=True, text=True, check=False)
    return [f for f in result.stdout.strip().splitlines() if f.endswith(".py")]


def main() -> int:
    """Main entry point for the pre-commit hook."""
    files = sys.argv[1:] or discover_files()

    violations = []
    for file_path in files:
        for line_no, attr_name, line in check_file(file_path):
            key = f"{file_path}:{line_no}:{line}"
            if key in EXCLUSIONS_ADHOC:
                continue
            violations.append((file_path, line_no, attr_name, line))

    if violations:
        print("Private instance fields are assigned in __init__ but never read.", file=sys.stderr)
        print("Drop the assignment (and the constructor parameter feeding it):\n", file=sys.stderr)
        for file_path, line_no, attr_name, line in violations:
            print(f"  {file_path}:{line_no}: {line}", file=sys.stderr)
            print(f"      self.{attr_name} is never read\n", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
