"""Tests for the sugar plugin: the attach/detach verbs wrap the resolver and unwrap it."""

import pytest

from tests.conftest import load_enabled_plugins
from udan.core.api_exceptions import ExceptionWithAdvice
from udan.core.api_plugins import PluginsAPI
from udan.core.api_query_processor import QueryProcessorAPI
from udan.core.config import UdanConfig
from udan.core.impl_ioc import create_udan_container
from udan.core.impl_udan_context import UdanContext
from udan.parsing.impl_utils_parsing import parse_tree
from udan.plugins_help_sugar.impl_miss_answers import QuestionMissAnswerer
from udan.plugins_help_sugar.impl_query_sugar import QuerySugar
from udan.plugins_help_sugar.plugins_help_sugar import DOMAIN, PLUGIN, HelpSugarPlugin


@pytest.fixture
def ctx_with_tools():
    """The boot's container with its tools loaded: both halves attach at container build."""
    container = create_udan_container(UdanConfig())
    ctx_obj = container.get(UdanContext)
    ctx_obj.container = container
    load_enabled_plugins(ctx_obj)
    return ctx_obj


@pytest.fixture
def query_processor(ctx_with_tools):
    """The resolver the boot wrapped the sugar and the miss answerer around."""
    return ctx_with_tools.container.get(QueryProcessorAPI)


@pytest.fixture
def plugin(ctx_with_tools):
    """The plugin instance the scan built from the package's PLUGIN declaration."""
    plugins = ctx_with_tools.container.get(PluginsAPI)
    return next(package.plugin for package in plugins.packages() if isinstance(package.plugin, HelpSugarPlugin))


@pytest.fixture
def exec_ctx(ctx_with_tools):
    """Execution context for direct resolve_query calls."""
    return ctx_with_tools.create_exec_context()


def test_plugin_declaration():
    """The package declares the PLUGIN the scan builds and the domain the snapshot reports."""
    assert DOMAIN == "help_sugar"
    assert PLUGIN is HelpSugarPlugin


def test_attach_registers_the_sugar(query_processor, exec_ctx):
    """A boot with the package wraps the sugar in: an incomplete name resolves to the question."""
    forest, _, _ = query_processor.resolve_query(parse_tree("git.", unwrap_single_roots=False), exec_ctx)

    assert forest.items[0].name == "?"


def test_attach_registers_the_miss_answerer(query_processor, exec_ctx):
    """A boot with the package patches the answer in: a miss continues with the question."""
    forest, _, _ = query_processor.resolve_query(parse_tree("sort_", unwrap_single_roots=False), exec_ctx)

    assert forest.items[0].name == "?"
    # The question was narrowed to the typed fragment: no kind filter written
    assert forest.items[0].args[:2] == (("pattern", "sort_"), ("tool_type", ""))


def test_detach_unwraps_both(plugin, ctx_with_tools, query_processor, exec_ctx):
    """After detach both decorations are off: no question rewriting, no miss answering."""
    plugin.detach()

    forest, _, _ = query_processor.resolve_query(parse_tree("git.", unwrap_single_roots=False), exec_ctx)
    assert forest.items == ["git."]

    # With no answer decorated in, the miss becomes the query error
    with pytest.raises(ExceptionWithAdvice, match="nothing answers it"):
        query_processor.resolve_query(parse_tree("sort_", unwrap_single_roots=False), exec_ctx)


def test_reattach_wraps_the_meaning_back(plugin, ctx_with_tools, query_processor, exec_ctx):
    """Decorate/undecorate is reversible: after detach and attach again, both halves answer."""
    plugin.detach()
    plugin.attach(
        query_processor,
        ctx_with_tools.container.get(QuerySugar),
        ctx_with_tools.container.get(QuestionMissAnswerer),
    )

    forest, _, _ = query_processor.resolve_query(parse_tree("git.", unwrap_single_roots=False), exec_ctx)
    assert forest.items[0].name == "?"

    forest, _, _ = query_processor.resolve_query(parse_tree("sort_", unwrap_single_roots=False), exec_ctx)
    assert forest.items[0].name == "?"
