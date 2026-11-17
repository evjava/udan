#!/usr/bin/env python3
"""Pre-commit hook to forbid ': Any' type annotations in src/udan/.

Any is a code smell — it disables type checking. Use concrete types instead.

Exclusions are stored as 'src/udan/file.py:*' for whole-file exclusions,
or 'src/udan/file.py:<num>:<stripped_content>' for per-line exclusions.
Violation output uses the same format — copy-paste directly into EXCLUSIONS_ADHOC.
"""

import re
import sys
from pathlib import Path

# fmt: off
# ruff: noqa: E501
EXCLUSIONS_ADHOC: set[str] = {
    # core_tools_loading/api_annotated.py: decorator protocol — accepts/returns arbitrary callables
    "src/udan/core_tools_loading/api_annotated.py:*",
    # api.py: circular-import boundary
    "src/udan/api.py:178:        operator_engine: Any = None,",
    # api_symbols_env.py: value can be any query result type
    "src/udan/core/api_symbols_env.py:19:    def set_variable(self, name: str, value: Any, type: str = \"query\", ctx: ExecContextAPI | None = None) -> None:",
    # api_chain_context.py: a tool may store any computed value
    "src/udan/core/api_chain_context.py:40:    def set_value(self, desc: ToolDescriptor, item: Item, value: Any) -> None:",
    # core_tools_loading/api_types.py: grouping key is dynamic
    "src/udan/core_tools_loading/api_types.py:37:    key: Any  # The grouping key (result of the grouper function)",
    # core_tools_loading/api_types.py: grouping order is dynamic (any sortable value)
    "src/udan/core_tools_loading/api_types.py:39:    order: Any = None  # Optional ordering key used to sort groups relative to each other",
    # (api_udan_injector.py was eliminated: its contract is
    # udan/core_tools_loading/api_function_injector.py, which holds its own wildcard entry below)
    # udan/attributes/impl_attribute_runtime.py: circular-import boundary
    "src/udan/attributes/impl_attribute_runtime.py:489:        operator_engine: Any = None,  # OperatorsEngineAPI | None - Any to avoid circular import",
    # impl_tools_loader.py: fixed — _memory now typed as Memory | None
    # impl_chain_context.py: mirrors api_chain_context.py
    "src/udan/core/impl_chain_context.py:51:    def set_value(self, desc: ToolDescriptor, item: Item, value: Any) -> None:",
    # impl_symbols_env.py: mirrors api_symbols_env.py
    "src/udan/core/impl_symbols_env.py:75:    def set_variable(self, name: str, value: Any, type: str = \"query\", ctx: ExecContextAPI | None = None) -> None:",
    # core_tools_loading/api_function_injector.py, impl_function_injector.py: injector contract and
    # core — stores/resolves arbitrary instances
    "src/udan/core_tools_loading/api_function_injector.py:*",
    "src/udan/core_tools_loading/impl_function_injector.py:*",
    # impl_udan_injector.py: the sources over what udan holds — the instances the
    # sources answer with are arbitrary services
    "src/udan/core/impl_udan_injector.py:*",
    # decompof/injector.py: vendored plugin framework — the injector stores and resolves
    # arbitrary instances by type (same reason as api_function_injector.py above)
    "src/udan/decompof/injector.py:*",
    # decompof/plugin.py: vendored plugin framework — a plugin's configuration is arbitrary
    # data handed to it by the loader
    "src/udan/decompof/plugin.py:*",
    # (plugins_builtins.py moved into udan/plugins_tools_examples, inside this check's src/udan
    # scope — its Any entries are below; plugins_demo too)
    # (plugins_system.py moved to udan/plugins_tools_core/plugins_system.py with its package)
    # plugins_system.py: moved from plugins_builtins — display formatting of dynamic annotations
    "src/udan/plugins_tools_core/plugins_system.py:895:def _format_type_annotation(annotation: Any) -> str:",
    # plugins_builtins.py: the sort/numeric-compare helpers take arbitrary field values
    # — an item's fields are whatever the inserter produced
    "src/udan/plugins_tools_examples/plugins_builtins.py:540:    def to_number(x: Any) -> int | float:",
    "src/udan/plugins_tools_examples/plugins_builtins.py:571:def _convert_string_to_numeric(value: str, field_value: Any) -> Any:",
    "src/udan/plugins_tools_examples/plugins_builtins.py:607:def _check_identity_operator(field_value: Any, operator: str, value: Any) -> bool | None:",
    "src/udan/plugins_tools_examples/plugins_builtins.py:663:    value: Any,",
    # plugins_demo: the demo inserters compute over arbitrary demo items by design
    "src/udan/plugins_tools_demo/plugins_demo.py:198:def double(item: Any, value: str | None = None) -> Any:",
    "src/udan/plugins_tools_demo/plugins_fruits.py:118:def _fruit_name(item: Any) -> str | None:",
    "src/udan/plugins_tools_demo/plugins_vegetables.py:99:def _vegetable_name(item: Any) -> str | None:",
    # api_attribute_cache.py: moved into udan.attributes (was udan_plugins_attributes) — a cached attribute
    # value is the attribute domain's arbitrary result type (AttributeValue = Any)
    "src/udan/attributes/api_attribute_cache.py:40:        self, attr_identity: str, attr_key: str, cache_key_value: str, value: Any, ctx: ExecContextAPI",
    # api_attributes.py: moved beside the attribute kind from the old package — the predicate only reads
    # metadata off the registry, and the registry contract lives in the loading layer
    "src/udan/core/api_attributes.py:215:def is_aggregate_attribute(registry: Any, key: str) -> bool:",
    # plugins_operators_attribute.py: the origin attribute's node is the system's
    # internal parse node, passed by the engine when the attribute is requested -
    # the body only answers [], so nothing here can name its type
    "src/udan/attributes/plugins_operators_attribute.py:63:def origin(item: Item, node: Any = None) -> list[Any]:",
    # api_renders.py: moved from udan_plugins_renders — the predicate only reads
    # metadata off the registry, like is_aggregate_attribute above
    "src/udan/renders/api_renders.py:62:def is_aggregate_render(registry: Any, key: str) -> bool:",
    # plugins_renders.py: _resolve_dict_path walks a dot path through a dict whose
    # values are arbitrary render payloads; the intermediate is genuinely untyped
    "src/udan/renders/plugins_renders.py:1192:    current: Any = d",
}
# fmt: on

# Pre-compute set of files with wildcard exclusions
_FILE_WILDCARDS: set[str] = {e.rsplit(":*", 1)[0] for e in EXCLUSIONS_ADHOC if e.endswith(":*")}

# Build content-only set for matching (file:content without line number)
_CONTENT_EXCLUSIONS: set[str] = set()
for e in EXCLUSIONS_ADHOC:
    if e.endswith(":*"):
        continue
    parts = e.split(":", 2)  # src/udan/file.py : 42 : content
    if len(parts) == 3:  # noqa: PLR2004
        _CONTENT_EXCLUSIONS.add(f"{parts[0]}:{parts[2]}")


def check_file(file_path: str) -> int:
    """Check a single file for : Any annotations.

    Returns 1 if new violations found, 0 otherwise.
    """
    path = Path(file_path)
    rel = str(path)

    if not rel.startswith("src/udan/") or not rel.endswith(".py"):
        return 0

    # Entire file excluded
    if rel in _FILE_WILDCARDS:
        return 0

    content = path.read_text()
    lines = content.split("\n")

    pattern = re.compile(r":\s*Any\b")
    violations = []

    for i, line in enumerate(lines, 1):
        if pattern.search(line):
            key = f"{rel}:{line.rstrip()}"
            if key not in _CONTENT_EXCLUSIONS:
                violations.append(f"{rel}:{i}:{line.rstrip()}")

    if violations:
        for v in violations:
            print(v)
        print("\n  → Fix by using a concrete type, or add above line to EXCLUSIONS_ADHOC in")
        print("    checks/check-no-any-annotation.py")
        return 1

    return 0


def main() -> int:
    """Entry point."""
    args = sys.argv[1:]
    if not args:
        args = [str(p) for p in sorted(Path("src").glob("udan*/**/*.py"))]

    exit_code = 0
    for file_path in args:
        if check_file(file_path):
            exit_code = 1
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
