import sys
import time
from pathlib import Path

import pytest
from joblib import Memory

from udan.core.api_plugins import PluginsAPI
from udan.core.config import UdanConfig
from udan.core.impl_ioc import create_udan_container
from udan.core.impl_plugins import Plugins
from udan.core.impl_udan_context import UdanContext
from udan.core_tools_loading.api_tool_kinds import get_kind_services
from udan.core_tools_loading.api_tools import ToolKind
from udan.core_tools_loading.impl_tool_kinds import ToolKindsRegistry as _Registry
from udan.parsing.api_query_parser import QueryParserAPI
from udan.renders import impl_render_engine

RESOURCES_DIR = Path(__file__).parent / "resources"

# Set up caching for tool loading
CACHE_DIR = Path(__file__).parent / ".pytest_cache"
memory = Memory(location=CACHE_DIR, verbose=0)


@pytest.fixture(autouse=True)
def isolate_history_path(tmp_path, monkeypatch):
    """Keep tests from writing to the real user history db.

    The history plugin's HistoryConfig defaults resolve history_path relative
    to the repo (.udan/history.db), so any test executing a query would pollute
    the real history. Point it to a per-test temp file instead.

    Tests that need a specific history path set UDAN_HISTORY_PATH themselves;
    environment variables take priority over the .env file.
    """
    monkeypatch.setenv("UDAN_HISTORY_PATH", str(tmp_path / "history.db"))
    monkeypatch.setenv("UDAN_HISTORY_SAVED_PATH", str(tmp_path / "saved.db"))


def register_tools_from_module(ctx, module_name, verbose=True):
    """Register tools from a module into the execution context.

    Also registers dependency providers (@annotated_dependency functions) from the module.

    Args:
        ctx: Execution context
        module_name: Name of the module (must already be imported)
        verbose: Whether to print debug info (default: True)
    """
    # Use the global loader from the context's registry
    loader = ctx.registry._loader
    module = sys.modules[module_name]

    # First, register dependency providers from the module
    ctx._register_dependency_providers_from_module(module_name)

    # Update loader's injectable types from the dependency registry
    # Get all providers from the registry and extract their types
    providers = ctx._dependency_registry._get_providers_for_plugins()
    injectable_types = set(providers.keys())

    # Also include the keys the container serves (the packages contributing
    # through PLUGIN hold their services there) and the injector's global
    # dependencies (AttributeRuntimeAPI, ToolsRegistryAPI, etc.), so a
    # container-provided type classifies the same way a registry one does
    injectable_types.update(ctx.container.provided_keys())

    global_deps = ctx.injector.dependencies
    injectable_types.update(global_deps.keys())

    loader._set_injectable_types(injectable_types)

    # Now load tools with injectable types set
    metadata_fns = loader.load_from_module(module)
    if not metadata_fns:
        raise ValueError(f"Expected to find tools in module {module_name}, but not found")

    if verbose:
        tools_names = [op_m.name for op_m, _ in metadata_fns]
        print(f"found tools: {tools_names}")

    ctx._register_many_metadatas(metadata_fns)


# NOTE: canonical plugin order in tests is demo, builtins, system, history, renders.
# plugins_history must be registered before plugins_renders so that render_history
# stays first in the "Available renders" list.


@pytest.fixture
def make_ctx():
    """Factory fixture: build an UdanContext with tools from given plugin modules.

    Modules must be imported by the test file and passed as objects, so the plugin
    set of each test is visible in the test file itself.

    The container is attached as a non-API `container` attribute.

    Usage:
        def test_fruits(make_ctx):
            ctx = make_ctx(
                plugins_demo, plugins_fruits,plugins_builtins,
            plugins_operators_attribute, plugins_system, plugins_history, plugins_renders
            )
    """

    def _make(*modules, config: UdanConfig | None = None) -> UdanContext:
        container = create_udan_container(config or UdanConfig())
        ctx_obj = container.get(UdanContext)
        ctx_obj.container = container
        for module in modules:
            register_tools_from_module(ctx_obj, module.__name__)
        return ctx_obj

    return _make


class QueryFacade:
    """The text facade over a make_ctx context: parse the text, hand the node to the context.

    The context runs the steps of an execution (validate, resolve, the item cap,
    apply, auto-limit, render, debug finalization, history, the error contract);
    parsing is the query language's own stage, and this facade is the composition
    the CLI makes: the container's parser turns the text into the node the
    context's execute_query takes. A parse error propagates - the tests assert
    the resolve-side contract, which stays inside the context.
    """

    def __init__(self, ctx: UdanContext) -> None:
        self._ctx = ctx
        self._parser = ctx.container.get(QueryParserAPI)

    def execute_query(self, search_state: str, comment: str | None = None, debug: bool = False) -> tuple:
        """Parse the text and execute the node: the (forest, attrs, render_tools, output) tuple."""
        exec_ctx = self._ctx.create_exec_context(debug=debug)
        started = time.perf_counter()
        query_node = self._parser.parse_text_to_tree(str(search_state), exec_ctx)
        forest, attrs, render_tools, out, _debug_info = self._ctx.execute_query(
            query_node, exec_ctx, query_text=str(search_state), started=started, comment=comment
        )
        return forest, attrs, render_tools, out

    def execute_query_split_debug(self, search_state: str, comment: str | None = None, debug: bool = False) -> tuple:
        """Parse the text and execute the node; the output stays clean, debug info comes back fifth."""
        exec_ctx = self._ctx.create_exec_context(debug=debug)
        started = time.perf_counter()
        query_node = self._parser.parse_text_to_tree(str(search_state), exec_ctx)
        return self._ctx.execute_query(
            query_node,
            exec_ctx,
            query_text=str(search_state),
            started=started,
            comment=comment,
            prepend_debug=False,
        )


def make_qp(ctx: UdanContext) -> QueryFacade:
    """The query facade over the container make_ctx built.

    The facade composes the container's parser with the context's execute_query:
    text in, executed state out - the composition the CLI makes. The context
    itself answers the tree-level calls (execute_query with a node;
    resolve_query and the interpreter's private surface through the container).

    Args:
        ctx: The engine context a make_ctx call returned (it carries .container)

    Returns:
        The text facade over that context
    """
    return QueryFacade(ctx)


def load_enabled_plugins(ctx: UdanContext) -> None:
    """Load the enabled packages' tools into the context's registry: the boot's plugin half.

    Tests that stand in for the boot (load_core) call this instead of walking the
    packages themselves: the container's plugins snapshot answers which packages
    are enabled, and the registry loads their modules' tools, in package order.

    Args:
        ctx: The engine context to load into (it carries .container)
    """
    plugins = ctx.container.get(PluginsAPI)
    ctx.registry.load_plugins(*(package.module for package in plugins.packages()), injector=ctx.injector)


def kinds_vocabulary() -> dict[str, ToolKind]:
    """The kind vocabulary the container builds: every kind the loaded packages declare.

    A loader built without it resolves every declared kind name to a bare kind, which
    carries no rules - no item contract keys, no metadata class, no level change - so
    the metadata it builds folds wrong. Test loaders take this, the way the container's
    own loader does.
    """
    registry = _Registry()
    for module in (
        impl_render_engine,
        *(package.module for package in Plugins(UdanConfig()).packages()),
    ):
        for service in get_kind_services(module):
            for kind in service.KINDS:
                registry.register(kind)
    return registry
