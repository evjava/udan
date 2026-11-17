#!/usr/bin/env python3
"""Pre-commit hook: forbid getattr/setattr/hasattr and __dict__ in src/udan/core/impl_* files."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

# Exemptions for existing legitimate usages: "path:line" -> exact line content.
# An entry holds only while the line at that position still equals the recorded
# content; a moved, edited or stale entry is reported as a violation.
EXCLUSIONS: dict[str, str] = {
    # (the attribute runtime moved back inside the scan scope with its package
    # - udan.attributes since the package joined udan; the one getattr left is
    # exempted below. The
    # loader's getattr and __dict__ reads moved to src/udan/core_tools_loading, whose
    # api_/io_ modules this check does not scan)
    # (the injector moved to src/udan/core_tools_loading/impl_function_injector.py with the
    # generic half: the two ExecContext attribute scans went with the sources, the
    # metadata copy and the wrap-once probe are re-lined there)
    "src/udan/core_tools_loading/impl_function_injector.py:161": "setattr(wrapped, attr_name, getattr(fn, attr_name))",
    "src/udan/core_tools_loading/impl_function_injector.py:222": "if getattr(fn, _INJECTOR_WRAPPED, False):",
    # (pre-existing, unrelated to the injector: field comparison over a model's
    # __dict__, the loader's by-name module attribute read, and a module's __file__)
    "src/udan/core_tools_loading/impl_tool_kinds.py:81": "new_value = extra.__dict__[field_name]",
    "src/udan/core_tools_loading/impl_tool_kinds.py:82": "old_value = base.__dict__[field_name]",
    "src/udan/core_tools_loading/impl_tools_loader.py:143": "result = [(metadata, getattr(module, metadata.name)) for metadata in metadatas]",
    "src/udan/core_tools_loading/impl_utils_tools_loader.py:327": 'module_file = module.__dict__.get("__file__") if module is not None else None',
    # impl_plugins: the DOMAIN-bound readers of a plugin module's declarations
    # (PLUGIN, SUBSCRIBE, CONFIG) - reading a module dict is the
    # declaration surface itself, not attribute reach-around; one shared read
    # answers them all
    "src/udan/core/impl_plugins.py:43": "return module.__dict__.get(attribute)",
    # impl_attribute_runtime: the composite attribute's nested field walk - a
    # dotted field path over a value that may be a dict (taken above) or an
    # object, and which object is the attribute domain's business, unknown here
    "src/udan/attributes/impl_attribute_runtime.py:353": "value = getattr(value, field, None)",
    # udan.plugins_history's sqlite storages: the thread-local connection probe - the
    # per-thread attribute is set only after the first use in that thread (and
    # cleared again by close), so the read has to ask whether it is there
    # (scanned since the package joined udan)
    "src/udan/plugins_history/impl_history_sqlite.py:106": 'conn = getattr(self._local, "conn", None)',
    "src/udan/plugins_history/impl_history_sqlite.py:141": 'conn = getattr(self._local, "conn", None)',
    "src/udan/plugins_history/impl_saved_sqlite.py:128": 'conn = getattr(self._local, "conn", None)',
    "src/udan/plugins_history/impl_saved_sqlite.py:147": 'conn = getattr(self._local, "conn", None)',
}

PATTERN = re.compile(r"\b(getattr|setattr|hasattr)\s*\(|\b__dict__\b")


def _tracked_impl_files() -> list[str]:
    """The impl_ files the check scans: git's list, plus whatever else is on disk.

    The gate runs in gitless checkouts too (worktrees, exported trees - the reason
    tools/run_checks.py exists), where `git ls-files` fails; an empty list there
    would report every exemption as stale. Falling back to the filesystem walk keeps
    the check working anywhere. The walk is unioned in even with a working git, so a
    new impl_ file is scanned before its first commit instead of escaping the gate.
    """
    result = subprocess.run(
        ["git", "ls-files", "src/udan/"],
        capture_output=True,
        text=True,
    )
    files = {f for f in result.stdout.strip().splitlines() if f.endswith(".py") and "/impl_" in f}
    files |= {str(path) for path in Path("src/udan").rglob("*.py") if "/impl_" in str(path)}
    return sorted(files)


def _read_lines(filepath: str) -> list[str]:
    try:
        return Path(filepath).read_text().splitlines()
    except FileNotFoundError:
        return []


def _matched_lines(files: list[str]) -> dict[str, str]:
    """Collect stripped line content by "path:line" for every forbidden pattern match."""
    return {
        f"{filepath}:{lineno}": line.strip()
        for filepath in files
        for lineno, line in enumerate(_read_lines(filepath), start=1)
        if PATTERN.search(line)
    }


def _problems(matched: dict[str, str]) -> list[str]:
    """Report non-exempt matches, plus stale and drifted exemptions."""
    problems = [f"{key}: {line}" for key, line in matched.items() if key not in EXCLUSIONS]
    problems += [
        f"{key}: exemption is stale, the line no longer matches the forbidden pattern"
        for key, _expected in EXCLUSIONS.items()
        if key not in matched
    ]
    problems += [
        f"{key}: exemption drifted, expected {expected!r}, got {matched[key]!r}"
        for key, expected in EXCLUSIONS.items()
        if key in matched and matched[key] != expected
    ]
    return problems


def main() -> None:
    problems = _problems(_matched_lines(_tracked_impl_files()))

    if problems:
        print(
            "\n".join(
                [
                    "Found getattr/setattr/hasattr/__dict__ in impl_ files (non-exempt):",
                    *problems,
                    "",
                    "Exemptions live in checks/check-no-hasattr-getattr-setattr.py as",
                    '"path:line" -> exact line content; update or drop them when the code moves.',
                ]
            )
        )
        sys.exit(1)

    print("No getattr/setattr/hasattr/__dict__ violations in impl_ files")


if __name__ == "__main__":
    main()
