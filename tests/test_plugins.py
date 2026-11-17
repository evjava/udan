"""Tests to verify all plugin modules define the required DOMAIN constant."""

import importlib
import pkgutil


def _plugin_module_names() -> list[str]:
    """Collect all plugin module names across udan and external udan_plugins_* packages.

    Utility modules (plugins_*_parser.py, plugins_*_utils.py) and test fixture
    modules (plugins_*_test.py) are excluded as they are not plugins.
    """
    roots = ["udan"] + sorted(
        name for _, name, ispkg in pkgutil.iter_modules() if ispkg and name.startswith("udan_plugins_")
    )
    modnames = []
    for root in roots:
        root_module = importlib.import_module(root)
        # walk, not iter: the plugin families moved inside udan (udan/plugins_tools_examples,
        # udan/plugins_tools_demo, udan/plugins_tools_core), and a package itself is not a
        # plugin module
        for _importer, modname, ispkg in pkgutil.walk_packages(root_module.__path__, prefix=f"{root}."):
            base = modname.rsplit(".", 1)[-1]
            if ispkg or not base.startswith("plugins_"):
                continue
            if not base.endswith(("_test", "_parser", "_utils")):
                modnames.append(modname)
    return modnames


def test_all_plugins_have_domain():
    """Test that all plugin modules define a DOMAIN constant.

    Every plugin module (plugins_*.py) should have a DOMAIN constant
    that specifies the domain namespace for its tools.
    This is required for proper full-path resolution (e.g., 'fruits.fruits').

    Note: Utility modules (plugins_*_parser.py, plugins_*_utils.py) are excluded as they are not plugins.
    """
    # Get all plugin modules
    plugin_modules = _plugin_module_names()

    # Verify each has DOMAIN defined
    missing_domain = []
    for modname in plugin_modules:
        module = importlib.import_module(modname)
        if not hasattr(module, "DOMAIN"):
            missing_domain.append(modname)

    assert not missing_domain, (
        "The following plugin modules are missing DOMAIN constant:\n"
        + "\n".join(f"  - {modname}" for modname in missing_domain)
        + "\n\n"
        "Each plugin module must define DOMAIN = '<domain_name>' at module level."
    )


def test_plugin_domains_are_strings():
    """Test that all DOMAIN constants are non-empty strings."""
    plugin_modules = _plugin_module_names()

    invalid_domains = []
    for modname in plugin_modules:
        module = importlib.import_module(modname)
        domain = getattr(module, "DOMAIN", None)
        if not isinstance(domain, str) or not domain.strip():
            invalid_domains.append((modname, repr(domain)))

    assert not invalid_domains, (
        "The following plugin modules have invalid DOMAIN values:\n"
        + "\n".join(f"  - {modname}: DOMAIN = {domain_repr}" for modname, domain_repr in invalid_domains)
        + "\n\n"
        "DOMAIN must be a non-empty string."
    )


def test_plugin_domains_are_unique():
    """Test that all plugin DOMAIN values are unique.

    Two plugins should not have the same DOMAIN value to avoid
    conflicts when resolving tools by full path.
    """
    plugin_modules = _plugin_module_names()

    domain_to_modules = {}
    for modname in plugin_modules:
        module = importlib.import_module(modname)
        domain = getattr(module, "DOMAIN", None)
        if domain:
            if domain not in domain_to_modules:
                domain_to_modules[domain] = []
            domain_to_modules[domain].append(modname)

    # Find duplicates
    duplicates = {d: mods for d, mods in domain_to_modules.items() if len(mods) > 1}

    assert not duplicates, (
        "The following DOMAIN values are used by multiple plugin modules:\n"
        + "\n".join(
            f"  - DOMAIN '{domain}':\n" + "\n".join(f"      - {modname}" for modname in modnames)
            for domain, modnames in duplicates.items()
        )
        + "\n\n"
        "Each plugin should have a unique DOMAIN value."
    )


# Expected DOMAIN values for known plugins
EXPECTED_DOMAINS = {
    "udan.plugins_tools_examples.plugins_builtins": "builtins",
    "udan.plugins_tools_examples.plugins_fs": "fs",
    "udan.plugins_tools_examples.plugins_org": "org",
    "udan.renders.plugins_renders": "renders",
    "udan.plugins_tools_examples.plugins_shell": "shell",
    "udan.plugins_tools_demo.plugins_demo": "demo",
    "udan.plugins_tools_demo.plugins_fruits": "fruits",
}


def test_plugin_domains_match_expected():
    """Test that plugin DOMAIN values match expected values."""
    plugin_modules = _plugin_module_names()

    mismatches = []
    for modname in plugin_modules:
        module = importlib.import_module(modname)
        domain = getattr(module, "DOMAIN", None)

        if modname in EXPECTED_DOMAINS:
            expected = EXPECTED_DOMAINS[modname]
            if domain != expected:
                mismatches.append((modname, expected, domain))

    assert not mismatches, "The following plugin modules have unexpected DOMAIN values:\n" + "\n".join(
        f"  - {modname}:\n      expected: {expected!r}\n      actual: {actual!r}"
        for modname, expected, actual in mismatches
    )
