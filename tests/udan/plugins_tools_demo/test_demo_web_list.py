"""Demo test for web_list plugin.

This test verifies that the web_list inserter can extract lists from HTML files
and uses date-based caching using the cache attributes mechanism.
"""

from pathlib import Path

import pytest

import udan.plugins_tools_demo.plugins_demo
import udan.plugins_tools_demo.plugins_fruits
from tests.conftest import make_qp
from udan.attributes import plugins_operators_attribute
from udan.attributes.api_attribute_cache import AttributeCacheAPI
from udan.core.config import UdanConfig

# Use conftest's monkey-patched create_udan_container
from udan.core.impl_ioc import create_udan_container
from udan.core.impl_udan_context import UdanContext
from udan.plugins_tools_examples import plugins_builtins, plugins_web
from udan.renders import plugins_renders


@pytest.fixture
def ctx_with_web():
    """Provide an UdanContext with demo, builtins, web, and renders plugins."""

    container = create_udan_container(UdanConfig())
    ctx = container.get(UdanContext)._with_plugins(
        udan.plugins_tools_demo.plugins_demo,
        plugins_builtins,
        plugins_operators_attribute,
        plugins_web,
        plugins_renders,
    )
    ctx.container = container
    return ctx


def test_web_list_basic(ctx_with_web):
    """Test that web_list can extract content from a web page."""
    # Create UdanContext with web plugin
    ctx = ctx_with_web

    # Check that web_list is in available tools
    specs = ctx.registry.get_tools()
    assert "web_list" in specs, "web_list should be registered"


def test_web_list_local_file(ctx_with_web):
    """Test that web_list can extract list items from a local HTML file."""
    ctx = ctx_with_web
    qp = make_qp(ctx)

    # Get path to test HTML file (resources are in tests/resources/)
    test_file = Path(__file__).parent.parent.parent / "resources" / "page-with-table-example.html"
    file_url = f"file://{test_file}"

    # URL must be quoted as a string since it contains special characters (:)
    query = f'web_list "{file_url}", :list'
    forest, attrs, render_specs, out = qp.execute_query(query)

    # The page should have list elements that get extracted
    assert out != "", "Should extract items from HTML file"
    assert out.startswith("["), "Output should start with a list bracket"
    assert out.endswith("]"), "Output should end with a list bracket"

    # Verify the output contains expected content (list items)
    # The output should contain some text content (not just empty brackets)
    assert len(out) > 2, "Output should have some content beyond the brackets"

    # Check that we extracted actual list items (content between brackets)
    inner_content = out[1:-1]  # Remove the outer brackets
    assert inner_content.strip() != "", "Should have items inside the list"

    # Verify specific items from the test file are present
    assert "Apple" in out, "Should extract 'Apple' from the fruit list"
    assert "Banana" in out, "Should extract 'Banana' from the fruit list"
    assert "First step" in out, "Should extract 'First step' from numbered list"


def test_web_list_with_timeout(ctx_with_web):
    """Test that web_list works with custom timeout parameter (for HTTP URLs)."""
    ctx = ctx_with_web
    qp = make_qp(ctx)

    # Test with custom timeout using a local file (timeout parameter should be accepted)
    test_file = Path(__file__).parent.parent.parent / "resources" / "page-with-table-example.html"
    file_url = f"file://{test_file}"

    # URL must be quoted as a string since it contains special characters (:)
    query = f'web_list "{file_url}" --timeout=30, :list'
    forest, attrs, render_specs, out = qp.execute_query(query)

    # Should successfully fetch and return items
    assert out != "", "Should extract items with custom timeout"
    assert out.startswith("["), "Output should be a list"


def test_web_list_cache_mechanism(ctx_with_web):
    """Test that web_list uses the cache attributes mechanism correctly."""
    ctx = ctx_with_web

    # Check that the attribute cache is resolvable from the container
    assert ctx.container.get(AttributeCacheAPI) is not None, "attribute cache should be available"

    # Check that refresh_on_date attribute is registered
    assert "refresh_on_date" in ctx.registry.get_tools(), "refresh_on_date should be registered"

    # Check that web_html attribute is registered
    assert "web_html" in ctx.registry.get_tools(), "web_html should be registered"

    # Verify that web_html uses cache_attribute
    web_html_metadata = ctx.registry.get_metadata("web_html")
    assert web_html_metadata is not None, "web_html metadata should exist"
    assert web_html_metadata.meta.get("cache_attribute") == "refresh_on_date", (
        "web_html should use refresh_on_date as cache_attribute"
    )


def test_web_list_cache_hit(ctx_with_web):
    """Test that web_list uses cache on second call with same URL."""
    ctx = ctx_with_web
    qp = make_qp(ctx)

    test_file = Path(__file__).parent.parent.parent / "resources" / "page-with-table-example.html"
    file_url = f"file://{test_file}"

    # First call should fetch
    # URL must be quoted as a string since it contains special characters (:)
    forest1, attrs1, render_specs1, out1 = qp.execute_query(f'web_list "{file_url}", :list')
    assert out1 != "", "First call should fetch and return items"

    # Second call with same URL should use cache (same day)
    forest2, attrs2, render_specs2, out2 = qp.execute_query(f'web_list "{file_url}", :list')
    assert out2 == out1, "Cached result should be identical"


def test_web_list_alias(ctx_with_web):
    """Test that web_list alias (weblist) works."""
    ctx = ctx_with_web
    qp = make_qp(ctx)

    # Test alias with local file
    test_file = Path(__file__).parent.parent.parent / "resources" / "page-with-table-example.html"
    file_url = f"file://{test_file}"

    # URL must be quoted as a string since it contains special characters (:)
    query = f'weblist "{file_url}", :list'
    forest, attrs, render_specs, out = qp.execute_query(query)

    assert out != "", "Alias weblist should work the same as web_list"
    assert out.startswith("["), "Output should be a list"


def test_web_list_cache_different_urls(ctx_with_web):
    """Test that different URLs create different cache entries."""
    ctx = ctx_with_web
    qp = make_qp(ctx)

    # Get two different test HTML files
    test_file1 = Path(__file__).parent.parent.parent / "resources" / "page-with-table-example.html"
    test_file2 = Path(__file__).parent.parent.parent / "resources" / "test_org_render.html"

    file_url1 = f"file://{test_file1}"
    file_url2 = f"file://{test_file2}"

    # Fetch from both URLs
    forest1, attrs1, render_specs1, out1 = qp.execute_query(f'web_list "{file_url1}", :list')
    forest2, attrs2, render_specs2, out2 = qp.execute_query(f'web_list "{file_url2}", :list')

    # Results should be different (different content in different files)
    assert out1 != out2, "Different URLs should return different results"


def test_web_list_cache_stores_data(ctx_with_web):
    """Test that cache actually stores data and retrieves it on subsequent calls."""
    ctx = ctx_with_web
    qp = make_qp(ctx)

    test_file = Path(__file__).parent.parent.parent / "resources" / "page-with-table-example.html"
    file_url = f"file://{test_file}"

    # Clear any existing cache to start fresh
    ctx.container.get(AttributeCacheAPI).clear_cache()

    # First call - should fetch and cache
    forest1, attrs1, render_specs1, out1 = qp.execute_query(f'web_list "{file_url}", :list')
    assert out1 != "", "First call should return items"

    # Verify cache has the data by checking cache size
    # The cache should have stored the HTML content
    cache_size_after_first = ctx.container.get(AttributeCacheAPI)._size()
    assert cache_size_after_first > 0, "Cache should have entries after first call"

    # Second call - should use cache
    forest2, attrs2, render_specs2, out2 = qp.execute_query(f'web_list "{file_url}", :list')
    assert out2 == out1, "Second call should return same result from cache"

    # Cache size should not have increased (no new entries)
    cache_size_after_second = ctx.container.get(AttributeCacheAPI)._size()
    assert cache_size_after_second == cache_size_after_first, "Cache size should not increase on cache hit"
