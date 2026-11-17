#!/usr/bin/env python3
"""Check modularity of udan_plugins_* packages and of tests by running udan queries.

Both rules are udan pipelines: modules are inserted (ls_files), their imported module names are
extracted from the import lines (extend_rg --o=True), taken from depth 1 (sgrep depth=1) and
filtered by module name (grep/grepv). Run from the repository root in the project venv:
    uv run python checks/check-modular-tests.py [--fail-on-tests] [--report-only]

The imports are read line-based from the sources (extend_rg, a core tool) rather than
with the AST-based extend_imports: extend_imports lives in a plugin package, which
does not load here at all - and a gate must not depend on a plugin that can be absent.

Rule A: udan_plugins_* packages (src/udan_plugins_*) must use only direct calls into the udan
public API, and must not use udan components. One query per package:

    ls_files src/<package> **/*.py, extend_rg "..." --o=True,
    sgrep depth=1, grep udan., grepv udan.api, unique

- allowed (grepv-ed out): udan.api, udan.core.api_*, udan.attributes.api_*,
  udan.renders.api_* and udan.plugins_tools_examples.api_* (the attribute, render and AST-chunk
  contracts moved into udan/attributes, udan/renders and udan/plugins_tools_examples beside their
  implementations), udan.core_tools_loading
- exempted (EXEMPTED_RULE_A_IMPORTS): the udan-component imports that already existed when the
  check joined the gate. Debt: shrink, never grow; an exemption whose import is gone fails
- (udan.plugins_tools_demo moved inside udan — not scanned by this rule)

Rule B: tests should not load plugins:

    ls_files tests **/test*py, extend_rg "..." --o=True,
    sgrep depth=1, grep plugins_, grepv tests.plugins_, grepv udan.plugins_tools_demo, unique

- a test importing a conftest shows the "tests.*.conftest" module among its imports
- excluded: plugins defined in tests/ (tests.plugins_*) and the demo plugin
- report only by default, pass --fail-on-tests to make it failing
"""

import argparse
import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

# Auto-limit would silently truncate the report
DEFAULT_LIMIT_ENV = "UDAN_DEFAULT_LIMIT"

# Comment documenting every query of this script in the udan history
QUERY_COMMENT = "check-modular-tests"

BULLET = "- "

# Rule A: no excluded packages left — udan_plugins_demo moved inside udan, and the
# glob never reached inside it
EXCLUDED_PLUGIN_PACKAGES: tuple[str, ...] = ()
PLUGIN_PACKAGE_GLOB = "src/udan_plugins_*"

# Rule B: globs selecting the test modules, and the name terms excluded from the report
TESTS_DIRECTORY = "tests"
TEST_GLOBS = "**/test*py"
TEST_PLUGIN_EXCLUDED = ("tests.plugins_", "udan.plugins_tools_demo")

# Import-line regexes for extend_rg --o=True: the captured group is the imported module.
# Anchored to the line start so a module named in a comment or docstring is not reported.
UDAN_MODULE_IMPORT_PATTERN = r"^\s*(?:from|import) (udan[a-zA-Z_0-9.]*)"
ANY_MODULE_IMPORT_PATTERN = r"^\s*(?:from|import) ([a-zA-Z_][a-zA-Z_0-9.]*)"

# Rule A: the udan components the plugin packages imported when this check joined the gate
# (the same debt class as the cross-plugin imports: the formats a package reverses, and the
# shared utils it formats with). Debt: shrink, never grow - a new udan-component import fails.
# A package a check does not know here has no exemptions at all.
EXEMPTED_RULE_A_IMPORTS: dict[str, set[str]] = {
    # (udan.attributes moved inside udan: its udan.core.config and udan.core.utils_collections
    # imports are core-internal now, like udan.operator* — no exemptions here)
    # (udan.plugins_builtins: the greps helper went with plugins_builtins to
    # udan.plugins_tools_examples, a cross-plugin import now, not a udan component.
    # The same went for udan.core.utils_str: cut_if_needed moved with the tool
    # machinery to udan.core_tools_loading - not a udan component, for history, python
    # and renders alike)
    # (udan.plugins_history and udan.parsing moved inside udan like udan.attributes:
    # history's udan.core.impl_constants, udan.core.utils_pydantic and udan.plugins_tools_examples.plugins_builtins,
    # parsing's parser beside them; the resolver's udan.core.config, udan.core.impl_ioc and
    # udan.core.utils_binding are core-internal now,
    # out of this rule's scan entirely)
    # (udan.plugins_tools_examples and udan.plugins_tools_demo moved inside udan like udan.attributes:
    # their udan imports — the builtins' udan.core.utils_binding and udan.core.utils_tables,
    # the demo's anything — are core-internal now, and the demo is out of this
    # rule's scan entirely)
    # (udan.renders moved inside udan like udan.attributes: its udan.core.utils_binding
    # import — the convert_boolean_string the tables plugin aligns by — is
    # core-internal now, no exemptions here)
}


def find_repo_root() -> Path:
    """Return repository root: current directory when it looks like the repo, else script parent."""
    cwd = Path.cwd()
    if (cwd / "src").is_dir() and (cwd / "tests").is_dir():
        return cwd
    return Path(__file__).resolve().parent.parent


def udan_items(query: str) -> list[str]:
    """Run a udan query, return the rendered items (the bullet lines without the bullet)."""
    environment = os.environ | {DEFAULT_LIMIT_ENV: "0"}
    completed = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "udan.parsing.main", query, f"--comment={QUERY_COMMENT}"],
        cwd=find_repo_root(),
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        print(completed.stderr, end="", file=sys.stderr)
        raise SystemExit(f"udan query failed: {query}")
    return [line[len(BULLET) :] for line in completed.stdout.splitlines() if line.startswith(BULLET)]


# --- Rule A: udan_plugins_* use only direct calls to udan public API, not udan components
# Not components, and so not reported: the udan.core.api_* contracts and udan.decompof -- the
# plugin framework a package imports to be hosted, its container included (the frontend
# hosts with it, and so does a package declaring a decompof plugin; the PLUGIN a package
# declares is a decompof Provider, the same declaration shape the core uses).


def rule_a_query(package: Path) -> str:
    """Query reporting the udan components imported by the modules of one plugin package."""
    return ", ".join(
        [
            f"ls_files {package} **/*.py",
            f'extend_rg "{UDAN_MODULE_IMPORT_PATTERN}" --o=True',
            "sgrep depth=1",
            "grep udan.",
            "grepv udan.api",
            # udan.attributes.api_* / udan.renders.api_* / udan.plugins_tools_examples.api_*: the
            # attribute, render and AST-chunk contracts moved beside their
            # implementations into udan/attributes, udan/renders and udan/plugins_tools_examples -
            # still public API, the same class as udan.core.api_*; the packages importing
            # them did not change
            "grepv udan.attributes.api",
            "grepv udan.renders.api",
            "grepv udan.plugins_tools_examples.api",
            "grepv udan.decompof",
            # udan.core_tools_loading: the kernel's generic loading subpackage (the declaration
            # surface, the wire format, the kind vocabulary, the cached loader). It
            # imports no udan module, so a package importing it is still
            # plugin-imports-kernel-contract, not plugin-imports-kernel-internals.
            "grepv udan.core_tools_loading",
            "unique",
        ]
    )


def rule_a_packages(root: Path) -> Iterator[Path]:
    """Plugin packages checked by rule A."""
    for package in sorted(root.glob(PLUGIN_PACKAGE_GLOB)):
        if package.is_dir() and package.name not in EXCLUDED_PLUGIN_PACKAGES:
            yield package


def find_stale_rule_a_exemptions(reports: dict[str, set[str]]) -> list[tuple[str, str]]:
    """Find exemptions whose exempted import the package no longer makes.

    Returns:
        List of (package name, imported module) pairs to drop from EXEMPTED_RULE_A_IMPORTS
    """
    stale = []
    for package_name, imports in EXEMPTED_RULE_A_IMPORTS.items():
        for module in sorted(imports - reports.get(package_name, set())):
            stale.append((package_name, module))
    return stale


# --- Rule B: tests should not load plugins


def rule_b_query() -> str:
    """Query reporting the plugin modules imported by the test modules."""
    steps = [
        f"ls_files {TESTS_DIRECTORY} {TEST_GLOBS}",
        f'extend_rg "{ANY_MODULE_IMPORT_PATTERN}" --o=True',
        "sgrep depth=1",
        "grep plugins_",
        *(f"grepv {term}" for term in TEST_PLUGIN_EXCLUDED),
        "unique",
    ]
    return ", ".join(steps)


# --- Entry point


def main(argv: list[str] | None = None) -> int:
    """Run both rule queries, print the reports, return exit code."""
    parser = argparse.ArgumentParser(description="Check modularity of udan_plugins_* packages and of tests")
    parser.add_argument(
        "--fail-on-tests", action="store_true", help="fail when tests load plugins (report only by default)"
    )
    parser.add_argument("--report-only", action="store_true", help="never fail, only print")
    args = parser.parse_args(argv)

    root = find_repo_root()
    rule_a_failed = False

    print("Rule A: udan_plugins_* must use only direct calls to the udan public API, not udan components")
    reports = {package.name: set(udan_items(rule_a_query(package))) for package in rule_a_packages(root)}
    for package_name, modules in reports.items():
        if not modules:
            continue
        unknown = sorted(modules - EXEMPTED_RULE_A_IMPORTS.get(package_name, set()))
        known = sorted(modules & EXEMPTED_RULE_A_IMPORTS.get(package_name, set()))
        if unknown:
            rule_a_failed = True
            print(f"{package_name}:")
            print("\n".join(f"  {module}" for module in unknown))
        if known:
            print(f"{package_name} (exempted debt, shrink it):")
            print("\n".join(f"  {module}" for module in known))
    for package_name, module in find_stale_rule_a_exemptions(reports):
        rule_a_failed = True
        print(f"Stale Rule A exemption: {package_name}: '{module}' is gone - drop it from EXEMPTED_RULE_A_IMPORTS")
    print(f"Rule A: {'violations found' if rule_a_failed else 'no violations'}\n")

    print("Rule B: tests should not load plugins (excluded: demo, plugins defined in tests/)")
    plugins = udan_items(rule_b_query())
    print("\n".join(f"  {module}" for module in plugins) if plugins else "  none")
    print(f"Rule B: {len(plugins)} plugin module(s) loaded by tests")
    if not args.fail_on_tests:
        print("Rule B: report only, pass --fail-on-tests to fail on these")
    print()

    if args.report_only:
        return 0
    if rule_a_failed or (args.fail_on_tests and plugins):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
