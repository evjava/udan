#!/usr/bin/env python3
"""Pre-commit hook to require _-prefixed names for private constructor fields.

When __init__ stores a constructor parameter on the instance, the attribute is
an implementation detail and must be private:

    self.symbols_env = symbols_env   # BAD  - leaks the collaborator as public API
    self._symbols_env = symbols_env  # GOOD - private field

Rationale:
- Injected collaborators are not part of the class contract; exposing them as
  `obj.registry` invites outside code to reach into the internals.
- A leading underscore marks the field as off-limits, which is what the
  check-encapsulation-violations hook then enforces for external access.

Only the mirrored form (attribute name == parameter name) is flagged. Fields
that are computed rather than mirrored (e.g. `self._depth = 0`) are out of
scope here.

Violations print in the same `file:lineno:content` format used by
EXCLUSIONS_ADHOC in the other hooks, so a legitimate exception can be
copied straight into the set below.
"""

import ast
import subprocess
import sys
from pathlib import Path

# fmt: off
# ruff: noqa: E501
EXCLUSIONS_ADHOC: set[str] = {
    # --- api_exceptions.py: exception payloads consumed by handlers, not private state ---
    # ExceptionWithAdvice.advice is read by the top-level handler (impl_udan_context.py:656)
    "src/udan/core/api_exceptions.py:6:        self.advice = advice",
    # OverrideForestException.forest is the documented short-circuit payload, read by
    # the top-level handler (impl_udan_context.py:642-651) and by tests
    "src/udan/core/api_exceptions.py:37:        self.forest = forest",

    # --- api_query_processor.py: QueryMiss payload, the same shape as
    # OverrideForestException.forest - read by the registered miss answerers and
    # by the chain walk's swap point
    "src/udan/core/api_query_processor.py:41:        self.pattern = pattern",
    "src/udan/core/api_query_processor.py:42:        self.tool_type = tool_type",
    "src/udan/core/api_query_processor.py:43:        self.reason = reason",

    # --- udan/attributes/impl_attribute_runtime.py: collaborators exposed
    # through api_ protocols ---
    # AttributeRuntimeAPI declares these as public interface members (api_attribute_runtime.py:30-31),
    # and plugins/tests traverse ctx.attribute_runtime.<name> on the injected instance
    "src/udan/attributes/impl_attribute_runtime.py:337:        self.registry = registry",
    "src/udan/attributes/impl_attribute_runtime.py:338:        self.attribute_storage = attribute_storage",
    # AttributesContextAPI declares attribute_runtime (api_attribute_contexts.py:29);
    # ctx is read cross-instance by the Attribute dataclasses in the same module
    "src/udan/attributes/impl_attribute_runtime.py:48:        self.attribute_runtime = attribute_runtime",
    "src/udan/attributes/impl_attribute_runtime.py:56:        self.ctx = ctx",

    # --- impl_attribute_contexts.py: AttributesContextAPI declares registry as a public
    # interface member (api_attribute_contexts.py:30); the chain handlers read
    # attr_ctx.registry to resolve the tools they apply
    "src/udan/core/impl_attribute_contexts.py:49:        self.registry = registry",

    # --- impl_chain_context.py: ChainContextAPI declares registry as a public
    # interface member (api_chain_context.py:31); the chain handlers read
    # chain_context.registry to resolve the tools they apply
    "src/udan/core/impl_chain_context.py:44:        self.registry = registry",
}
# fmt: on

# Build content-only set for matching (file:content without line number).
# Line numbers drift as files change above the exempted lines; the content is
# what identifies the line (same approach as check-no-any-annotation.py).
_CONTENT_EXCLUSIONS: set[str] = set()
for _e in EXCLUSIONS_ADHOC:
    _parts = _e.split(":", 2)  # src/udan/file.py : 42 : content
    if len(_parts) == 3:  # noqa: PLR2004
        _CONTENT_EXCLUSIONS.add(f"{_parts[0]}:{_parts[2]}")


def _assignment_target_and_value(statement: ast.stmt) -> tuple[ast.Attribute, ast.expr] | None:
    """Return (attribute, value) for a simple or annotated assignment, else None."""
    if isinstance(statement, ast.Assign) and len(statement.targets) == 1:
        target = statement.targets[0]
        if isinstance(target, ast.Attribute):
            return target, statement.value
    if isinstance(statement, ast.AnnAssign) and isinstance(statement.target, ast.Attribute):
        if statement.value is not None:
            return statement.target, statement.value
    return None


def _is_mirrored_parameter(attr: ast.Attribute, value: ast.expr, init: ast.FunctionDef) -> bool:
    """Check that the statement is `self.x = x` where x is a parameter of __init__."""
    receiver = attr.value
    if not (isinstance(receiver, ast.Name) and receiver.id == "self"):
        return False
    if not (isinstance(value, ast.Name) and value.id == attr.attr):
        return False
    return any(arg.arg == attr.attr for arg in init.args.args + init.args.kwonlyargs)


def check_file(file_path: str) -> list[tuple[int, str, str]]:
    """Check a Python file for public mirrored constructor fields.

    Returns:
        List of (line_number, attribute_name, stripped_line) tuples.
    """
    try:
        source = Path(file_path).read_text(encoding="utf-8")
    except OSError, UnicodeDecodeError:
        return []

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    lines = source.splitlines()
    violations: list[tuple[int, str, str]] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        for item in node.body:
            if not (isinstance(item, ast.FunctionDef) and item.name == "__init__"):
                continue
            for statement in item.body:
                found = _assignment_target_and_value(statement)
                if found is None:
                    continue
                attr, value = found
                if attr.attr.startswith("_"):
                    continue
                if not _is_mirrored_parameter(attr, value, item):
                    continue
                line = lines[attr.lineno - 1].rstrip() if attr.lineno <= len(lines) else ""
                violations.append((attr.lineno, attr.attr, line))

    return violations


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
            if f"{file_path}:{line}" in _CONTENT_EXCLUSIONS:
                continue
            violations.append((file_path, line_no, attr_name, line))

    if violations:
        print("Private constructor fields must start with an underscore.", file=sys.stderr)
        print("Rename the attribute (and its uses) to the _-prefixed form:\n", file=sys.stderr)
        for file_path, line_no, attr_name, line in violations:
            print(f"  {file_path}:{line_no}: {line}", file=sys.stderr)
            print(f"      self.{attr_name} -> self._{attr_name}\n", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
