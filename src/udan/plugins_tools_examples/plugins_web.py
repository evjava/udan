"""Web plugin for fetching and extracting lists from web pages.

This plugin provides the web_list inserter that can fetch content from URLs
and extract list items, with date-based caching using the cache attributes mechanism.
"""

from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote
from urllib.request import Request, urlopen

from udan.core_tools_loading.api_annotated import annotated

DOMAIN = "web"

# Constants
DEFAULT_HTTP_TIMEOUT = 10
_FILE_URL_PREFIX = "file://"
_FILE_URL_PREFIX_LENGTH = len(_FILE_URL_PREFIX)
DEFAULT_USER_AGENT = "Mozilla/5.0 (Udan/1.0)"
_LIST_CONTAINER_TAGS = ("ul", "ol", "dl", "menu")
_LIST_ITEM_TAGS = ("li", "dt", "dd")
_TEXT_ENCODING = "utf-8"


class ListExtractorParser(HTMLParser):
    """HTML parser that extracts text from list elements (<li>, <dt>, <dd>)."""

    def __init__(self):
        super().__init__()
        self.in_list = False
        self.in_list_item = False
        self.items = []
        self.current_item = []

    def handle_starttag(self, tag, attrs):
        if tag in _LIST_CONTAINER_TAGS:
            self.in_list = True
        elif tag in _LIST_ITEM_TAGS and self.in_list:
            self.in_list_item = True
            self.current_item = []

    def handle_endtag(self, tag):
        if tag in _LIST_CONTAINER_TAGS:
            self.in_list = False
        elif tag in _LIST_ITEM_TAGS and self.in_list_item:
            self.in_list_item = False
            if self.current_item:
                item_text = "".join(self.current_item).strip()
                if item_text:
                    self.items.append(item_text)
            self.current_item = []

    def handle_data(self, data):
        if self.in_list_item:
            self.current_item.append(data)


def _fetch_url(url: str, timeout: int = DEFAULT_HTTP_TIMEOUT) -> str:
    """Fetch content from URL.

    Supports both HTTP/HTTPS URLs and file:// URLs for local files.
    Auto-detects local file paths (absolute and relative) and converts them to file:// URLs.

    Args:
        url: The URL to fetch
        timeout: Request timeout in seconds (only used for HTTP/HTTPS)

    Returns:
        HTML content as string

    Raises:
        URLError: If URL cannot be fetched
        HTTPError: If HTTP request fails
        FileNotFoundError: If file:// URL points to non-existent file
    """
    # Auto-detect local file paths and convert to file:// URL format
    # Detect: absolute paths (/path), relative paths (./path, ../path), or Windows paths (C:/path)
    # Exclude URLs that already have a scheme (file://, http://, https://, etc.)
    has_scheme = "://" in url
    is_local_path = not has_scheme and (
        url.startswith("/")  # Absolute path
        or url.startswith("./")  # Relative path (./)
        or url.startswith("../")  # Relative path (../)
        or (len(url) > 1 and url[1] == ":")  # Windows path (C:/path)
        or ("." in url and "/" in url)  # Relative path like tests/file.html
    )

    if is_local_path:
        url = f"file://{url}"

    # Handle file:// URLs for local files
    if url.startswith(_FILE_URL_PREFIX):
        # Remove file:// prefix and URL-decode the path
        file_path = unquote(url[_FILE_URL_PREFIX_LENGTH:])
        # Handle both file:///absolute/path and file://relative/path formats
        if file_path.startswith("/") and len(file_path) > 1 and file_path[2] == ":":
            # Windows path like file:///C:/path -> C:/path
            file_path = file_path[1:]
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        return path.read_text(encoding=_TEXT_ENCODING, errors="ignore")

    # Handle HTTP/HTTPS URLs
    headers = {"User-Agent": DEFAULT_USER_AGENT}
    req = Request(url, headers=headers)

    with urlopen(req, timeout=timeout) as response:
        return response.read().decode(_TEXT_ENCODING, errors="ignore")


def _extract_lists_from_html(html: str) -> list[str]:
    """Extract list items from HTML content.

    Args:
        html: HTML content as string

    Returns:
        List of extracted items
    """
    parser = ListExtractorParser()
    parser.feed(html)
    return parser.items


@annotated(meta={"attribute_type": "simple", "cache_attribute": "refresh_on_date"})
def web_html(item: str, timeout: int = DEFAULT_HTTP_TIMEOUT) -> str:
    """Fetch HTML content from URL.

    This attribute fetches HTML content from the given URL (or file path).
    Results are cached daily using the refresh_on_date cache attribute.

    Args:
        item: The URL to fetch (https://..., http://..., file://..., or local file path)
        timeout: Request timeout in seconds (default: 10, only used for HTTP/HTTPS)

    Returns:
        HTML content as string

    Raises:
        URLError: If URL cannot be fetched
        FileNotFoundError: If file:// URL points to non-existent file
    """
    return _fetch_url(item, timeout)


@annotated(meta={"tool_type": "inserter", "output_type": "dict", "aliases": ["weblist"], "dependencies": ["web_html"]})
def web_list(url: str, timeout: int = DEFAULT_HTTP_TIMEOUT, web_html: str | None = None) -> list[str]:
    """Fetch and extract list items from a web page or local HTML file.

    This inserter fetches content and extracts items from HTML lists
    (<ul>, <ol>, <dl>). Supports both HTTP/HTTPS URLs and file:// URLs
    for local files. Results are cached per day using the cache attributes mechanism.

    Args:
        url: The URL to fetch (https://..., http://..., file://..., or local file path)
        timeout: Request timeout in seconds (default: 10, only used for HTTP/HTTPS)
        web_html: HTML content (injected by framework via dependencies)

    Returns:
        List of extracted items from HTML lists

    Examples:
        Fetch list from a web page::

            web_list https://example.com

        Fetch from local file (auto-detects file paths)::

            web_list /path/to/local.html

        With custom timeout::

            web_list https://example.com --timeout=30

    Note:
        Results are cached daily. The cache key includes the current date,
        so content is refreshed once per day. The cache is stored in the
        udan cache directory (./.udan_cache/attrs/web_html/).

        If no list items are found in the HTML, this function returns an empty list.
        Use a text viewer or cat command to see the raw HTML content.
    """
    # Extract lists from HTML (web_html is resolved via dependencies)
    if web_html is None:
        return []
    items = _extract_lists_from_html(web_html)
    return items
