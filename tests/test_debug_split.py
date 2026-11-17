"""Tests for debug separation: execute_query_split_debug.

The split entry returns the debug text beside the output instead of
prepending it, so the two can travel separately.
"""

import re

from tests.conftest import make_qp
from udan.plugins_tools_demo import plugins_demo, plugins_fruits


def test_execute_query_debug_concatenated_unchanged(make_ctx):
    """Non-rest mode unchanged: debug is prepended to output and starts with '# '."""
    ctx = make_ctx(plugins_demo, plugins_fruits)
    qp = make_qp(ctx)
    out_clean = qp.execute_query("fruits")[3]
    assert out_clean
    assert not out_clean.startswith("# ")

    out_debug = qp.execute_query("fruits", debug=True)[3]
    assert out_debug.startswith("# ")
    assert out_clean in out_debug


def test_execute_query_error_debug_merged_unchanged(make_ctx):
    """Non-rest error path unchanged: debug log is merged into error output."""
    ctx = make_ctx(plugins_demo, plugins_fruits)
    qp = make_qp(ctx)
    out = qp.execute_query("nosuchoperator_xyz", debug=True)[3]
    assert out.startswith("# ")


def test_split_debug_disabled_returns_empty_debug(make_ctx):
    """Without debug the split method returns empty debug info and clean output."""
    ctx = make_ctx(plugins_demo, plugins_fruits)
    qp = make_qp(ctx)
    out_expected = qp.execute_query("fruits")[3]
    forest, attrs, render_specs, out, debug_info = qp.execute_query_split_debug("fruits")
    assert debug_info == ""
    assert out == out_expected
    assert forest is not None


def test_split_debug_via_param(make_ctx):
    """debug=True argument: debug info returned separately, output stays clean."""
    ctx = make_ctx(plugins_demo, plugins_fruits)
    qp = make_qp(ctx)
    out_clean = qp.execute_query("fruits")[3]
    _, _, _, out, debug_info = qp.execute_query_split_debug("fruits", debug=True)
    assert debug_info.startswith("# ")
    assert out == out_clean


def test_split_debug_via_keyword(make_ctx):
    """'debug' keyword inside query: debug info returned separately, output stays clean."""
    ctx = make_ctx(plugins_demo, plugins_fruits)
    qp = make_qp(ctx)
    out_clean = qp.execute_query("fruits")[3]
    _, _, _, out, debug_info = qp.execute_query_split_debug("fruits, debug")
    assert debug_info.startswith("# ")
    assert out == out_clean


def test_split_debug_content_matches_prepended_block(make_ctx):
    """Split debug info equals the block that execute_query prepends to output."""
    ctx = make_ctx(plugins_demo, plugins_fruits)
    qp = make_qp(ctx)
    qp.execute_query("fruits")  # consume first-query IOC log section
    out_prepended = qp.execute_query("fruits", debug=True)[3]
    out_clean = qp.execute_query("fruits")[3]
    _, _, _, _, debug_info = qp.execute_query_split_debug("fruits", debug=True)
    assert out_prepended.startswith(debug_info)
    assert out_prepended[len(debug_info) :].strip() == out_clean.strip()


def test_split_debug_time_via_keyword(make_ctx):
    """'debug-time' keyword: timestamped debug log plus time line, output stays clean."""
    ctx = make_ctx(plugins_demo, plugins_fruits)
    qp = make_qp(ctx)
    out_clean = qp.execute_query("fruits")[3]
    _, _, _, out, debug_info = qp.execute_query_split_debug("fruits, debug-time")
    assert debug_info.startswith("# ")
    assert re.search(r"^# \[\d{2}:\d{2}\.\d{3}\] \[DEBUG\]", debug_info, re.MULTILINE)
    assert " [DEBUG] Time: " in debug_info
    assert out == out_clean


def test_time_combined_with_debug(make_ctx):
    """'debug' and 'debug-time' together: timestamped debug log plus the time log line."""
    ctx = make_ctx(plugins_demo, plugins_fruits)
    qp = make_qp(ctx)
    qp.execute_query("fruits")  # consume first-query IOC log section
    _, _, _, _, debug_info = qp.execute_query_split_debug("fruits, debug, debug-time")
    assert debug_info.startswith("# ")
    # debug-time enables timestamp prefixes on log lines, like udan_log_time config
    assert re.search(r"^# \[\d{2}:\d{2}\.\d{3}\] \[DEBUG\]", debug_info, re.MULTILINE)
    assert " [DEBUG] Time: " in debug_info


def test_debug_alone_has_no_time_prefixes(make_ctx):
    """'debug' without 'debug-time': log lines stay without timestamp prefixes."""
    ctx = make_ctx(plugins_demo, plugins_fruits)
    qp = make_qp(ctx)
    qp.execute_query("fruits")  # consume first-query IOC log section
    _, _, _, _, debug_info = qp.execute_query_split_debug("fruits, debug")
    assert debug_info.startswith("# [DEBUG]")
    assert "Time: " not in debug_info


def test_debug_time_sticky_for_session(make_ctx):
    """'debug-time' in one query keeps the time line on for later queries in the session."""
    ctx = make_ctx(plugins_demo, plugins_fruits)
    qp = make_qp(ctx)
    _, _, _, _, before = qp.execute_query_split_debug("fruits")
    assert before == ""
    qp.execute_query_split_debug("fruits, debug-time")
    _, _, _, out_after, after = qp.execute_query_split_debug("fruits")
    assert " [DEBUG] Time: " in after
    # Sticky time only: later queries don't get the full debug log
    assert not after.startswith("# [DEBUG]")
    assert out_after


def test_debug_time_sticky_shows_in_errors(make_ctx):
    """Failing query in a sticky session still reports the elapsed time."""
    ctx = make_ctx(plugins_demo, plugins_fruits)
    qp = make_qp(ctx)
    qp.execute_query_split_debug("fruits, debug-time")
    _, _, _, out, debug_info = qp.execute_query_split_debug("nosuchoperator_xyz")
    assert debug_info.startswith("# [")
    assert " [DEBUG] Time: " in debug_info
    assert out


def test_debug_time_prepended_in_cli_mode(make_ctx):
    """Non-split mode: timestamped debug log plus time line prepended to output."""
    ctx = make_ctx(plugins_demo, plugins_fruits)
    qp = make_qp(ctx)
    out_clean = qp.execute_query("fruits")[3]
    out = qp.execute_query("fruits, debug-time")[3]
    assert out.startswith("# [")
    assert " [DEBUG] Time: " in out
    assert out_clean in out


def test_split_error_with_debug_param(make_ctx):
    """Failing query with debug on: error text in out, debug log returned separately."""
    ctx = make_ctx(plugins_demo, plugins_fruits)
    qp = make_qp(ctx)
    _, _, _, out, debug_info = qp.execute_query_split_debug("nosuchoperator_xyz", debug=True)
    assert debug_info.startswith("# ")
    assert not out.startswith("# ")


def test_split_error_without_debug(make_ctx):
    """Failing query without debug: empty debug info, error message present."""
    ctx = make_ctx(plugins_demo, plugins_fruits)
    qp = make_qp(ctx)
    _, _, _, out, debug_info = qp.execute_query_split_debug("nosuchoperator_xyz")
    assert debug_info == ""
    assert out
