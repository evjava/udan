#!/usr/bin/env python3
"""Pre-commit hook to forbid services passed as function arguments.

The rule: a service is received through constructor injection, never threaded
through method arguments.

The IoC container (impl_ioc.py) wires every service into its consumer once, at
construction time. A method that asks for a service as a parameter forces every
caller to fetch and forward it, hiding the real dependency chain and coupling
the call graph to the wiring.

What is flagged:

    def build_catalog(registry: ToolsRegistryAPI):

What is not flagged:

    def __init__(self, registry: ToolsRegistryAPI):   # constructor injection
    def run(self, ctx: ExecContextAPI):                        # ctx is not a container service
    def render_items(self, storage: AttributeStorageAPI):      # in ALLOWED_APIS

A service is any *API interface the composed container wires - read off
impl_ioc.py and off every plugin module that declares PLUGIN (imported from
udan.api* or from a plugin package's api_*). The set is derived from the
container, so a new provider is picked up without touching this hook. Non-API
names registered there (UdanContext, UdanConfig) are deliberately out of scope.

ALLOWED_APIS, EXCLUDED_FILES and EXCLUSIONS hold the violations that already
exist. They are architectural debt to be resolved, not permissions: shrink them,
never grow them.
"""

import ast
import subprocess
import sys
from pathlib import Path

IOC_MODULE = Path(__file__).parent.parent / "src" / "udan" / "core" / "impl_ioc.py"

PLUGIN_ATTRIBUTE = "PLUGIN"
"""The module attribute a plugin package's container contribution is read through (impl_plugins)."""

PLUGIN_PACKAGE_GLOB = "src/udan_plugins_*"
CORE_SUBPACKAGE_GLOB = "src/udan/*"

# APIs that may be passed as arguments
ALLOWED_APIS = {
    "AttributeStorageAPI",
    "FunctionInjectorAPI",
    # the per-query context: created by the context per query and handed to the
    # walk's callees, never wired by the container
    "ExecContextAPI",
    # the per-query chain context: the same story - created per query, handed
    # to the appliers and the engine's recursion, never wired by the container
    "ChainContextAPI",
    # the operators engine: handed to the context by the operators plugin's
    # container decoration (with_operator_engine) - the composition handing a
    # service in, not a call threading it
    "OperatorsEngineAPI",
    # the attribute runtime, the same story: handed to the context by the
    # attributes plugin's container decoration (with_attribute_runtime)
    "AttributeRuntimeAPI",
}

# Files that must be able to name services
EXCLUDED_FILES = {
    "impl_ioc.py",  # the container itself - it is what wires services in
    "plugins_operator.py",  # the operators engine package's composition root (its PLUGIN)
    "plugins_attributes.py",  # the attributes package's composition root (its PLUGIN)
    "plugins_operator_extender.py",  # the extender kind's composition root (its PLUGIN)
    "plugins_operator_filter.py",  # the filter kind's composition root (its PLUGIN)
    "plugins_operator_grouper.py",  # the grouper kind's composition root (its PLUGIN)
    "plugins_operator_inserter.py",  # the inserter kind's composition root (its PLUGIN)
    "plugins_operator_mapper.py",  # the mapper kind's composition root (its PLUGIN)
    "plugins_parsing.py",  # the query parser's piece of the composition root (its PLUGIN)
    "plugins_help_sugar.py",  # the question sugar's composition root (its PLUGIN: the
    #                          provide and the attach/detach verbs whose parameters the
    #                          container resolves)
    "plugins_renders.py",  # the renders package's composition root (its PLUGIN)
    "plugins_history.py",  # the history package's composition root (its PLUGIN: the two storages
    #                        and the verbs whose parameters the container resolves)
    "plugins_operator_replacer.py",  # the replacer kind's composition root (its PLUGIN)
    "plugins_operator_sorter.py",  # the sorter kind's composition root (its PLUGIN)
}

# Pre-existing violations, keyed "path:function:param:Service".
# The reason each one exists is not yet written down: fill it in as they are
# removed or explicitly allowed. Do not add new entries.
EXCLUSIONS = {
    # plugins_core/plugins_help.py
    "src/udan/plugins_tools_core/plugins_help.py:_get_tool_location:registry:ToolsRegistryAPI": "",
    "src/udan/plugins_tools_core/plugins_help.py:_find_exactly_named_tool:registry:ToolsRegistryAPI": (
        "pre-existing: introspection helper, registry is its data source"
    ),
    # chain_routing: the builder takes the overriding handler the variant wraps -
    # composing a routing object, not threading a service through a call
    "src/udan/core/api_chain_routing.py:with_override_handler:service:ChainStepServiceAPI": (
        "pre-existing: routing builder takes the handler its variant wraps"
    ),
    "src/udan/core/impl_chain_routing.py:with_override_handler:service:ChainStepServiceAPI": (
        "pre-existing: routing builder takes the handler its variant wraps"
    ),
}


def collect_services(ioc_path: Path) -> set[str]:
    """Collect the *API service names the composed IoC container wires.

    Args:
        ioc_path: Path to the core container module (impl_ioc.py)

    Returns:
        Set of *API interface names
    """
    services = _services_from_module(ioc_path)
    for module_path in provider_modules():
        services |= _services_from_module(module_path)
    return {name for name in services if name.endswith("API")}


def _services_from_module(module_path: Path) -> set[str]:
    """Collect the *API names one container module references.

    Args:
        module_path: Path to a module that wires services (impl_ioc.py, a PLUGIN module)

    Returns:
        Set of *API interface names
    """
    try:
        source = module_path.read_text(encoding="utf-8-sig")
    except OSError as e:
        print(f"cannot derive services from {module_path}: {e}", file=sys.stderr)
        sys.exit(2)

    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        print(f"cannot derive services from {module_path}: {e}", file=sys.stderr)
        sys.exit(2)

    services = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            services.update(alias.name for alias in node.names if alias.name.endswith("API"))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name != "__init__":
            if _annotation_name(node.returns):
                services.add(_annotation_name(node.returns))
        elif isinstance(node, ast.Call) and getattr(node.func, "id", None) == "provide":
            for keyword in node.keywords:
                if keyword.arg == "provides" and _annotation_name(keyword.value):
                    services.add(_annotation_name(keyword.value))
    return services


def provider_modules() -> list[Path]:
    """The plugin modules that declare a container provider.

    Discovery is by the same convention the container factory reads at runtime
    (impl_plugins.PLUGIN_ATTRIBUTE), so the hook names no package. Both homes
    a provider module has are scanned: a top-level plugin package
    (src/udan_plugins_*) and the core's own plugin subpackages (src/udan/operator*
    among them).

    Returns:
        Paths of the plugins_*.py modules declaring PLUGIN
    """
    project = Path(__file__).parent.parent
    modules = []
    for package in sorted([*project.glob(PLUGIN_PACKAGE_GLOB), *project.glob(CORE_SUBPACKAGE_GLOB)]):
        if not package.is_dir():
            continue
        for module_path in sorted(package.glob("plugins_*.py")):
            if declares_provider(module_path):
                modules.append(module_path)
    return modules


def declares_provider(module_path: Path) -> bool:
    """Whether a module declares a container contribution at its top level.

    Args:
        module_path: Path to a plugins_*.py module

    Returns:
        True when the module declares PLUGIN - the name a package's container
        contribution is read through (impl_plugins)
    """
    try:
        tree = ast.parse(module_path.read_text(encoding="utf-8-sig"))
    except OSError, SyntaxError:
        return False
    return any(
        isinstance(node, ast.Assign) and any(getattr(target, "id", None) == PLUGIN_ATTRIBUTE for target in node.targets)
        for node in tree.body
    )


def _annotation_name(annotation: ast.AST) -> str | None:
    """Return the simple name behind an annotation (X, module.X, X[...]).

    Args:
        annotation: Annotation node

    Returns:
        Name as written, or None when it cannot be resolved
    """
    if isinstance(annotation, ast.Name):
        return annotation.id
    if isinstance(annotation, ast.Attribute) and isinstance(annotation.value, ast.Name):
        return annotation.attr
    if isinstance(annotation, ast.Subscript):
        return _annotation_name(annotation.value)
    return None


def check_file(file_path: Path, services: set[str]) -> list[tuple[int, str, str, str]]:
    """Check a file for services received as arguments.

    Args:
        file_path: File to check
        services: Service names to look for

    Returns:
        List of (line_number, function_name, parameter_name, service_name)
    """
    if file_path.name in EXCLUDED_FILES:
        return []

    try:
        source = file_path.read_text(encoding="utf-8-sig")
    except OSError:
        return []

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []  # left to the syntax checkers

    violations = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name == "__init__":
            continue  # constructor injection is how the container hands services over
        if node.name == "attach":
            continue  # decompof plugin attachment: annotation is how the framework hands services over
        if node.name.startswith(("register_", "unregister_")):
            continue  # a registration verb is the same hand-over: the plugin's contribution
            # joins a component that is already running (a processor extra, a miss
            # answerer), and the annotation is how its parameter is resolved
        args = node.args
        params = [*args.args, *args.posonlyargs, *args.kwonlyargs, args.vararg, args.kwarg]
        for param in params:
            if param is None:
                continue
            name = _annotation_name(param.annotation)
            if name in services and name not in ALLOWED_APIS:
                violations.append((node.lineno, node.name, param.arg, name))
    return violations


def staged_files() -> list[Path]:
    """Return the staged Python files.

    Returns:
        Paths of added/copied/modified staged files
    """
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
        capture_output=True,
        text=True,
        check=False,
    )
    return [Path(f) for f in result.stdout.splitlines() if f.endswith(".py")]


def main() -> None:
    """Run the pre-commit hook."""
    services = collect_services(IOC_MODULE)
    files = [Path(f) for f in sys.argv[1:]] or staged_files()

    violations = []
    for file_path in files:
        if not file_path.is_file():
            continue
        for line_no, func, param, service in check_file(file_path, services):
            key = f"{file_path.as_posix()}:{func}:{param}:{service}"
            if key not in EXCLUSIONS:
                violations.append((file_path, line_no, func, param, service))

    if violations:
        print("Services must not be passed as arguments - inject them via the constructor.", file=sys.stderr)
        print("A service is any *API interface the composed container wires.", file=sys.stderr)
        print("", file=sys.stderr)
        for file_path, line_no, func, param, service in violations:
            print(f"{file_path}:{line_no}: {func}(... {param}: {service} ...)", file=sys.stderr)
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
